#!/usr/bin/env python3
"""gabes little server! - MOTD status updater.

Reads the current server mode (written by the launch .bat), scrapes the fake IP
allocation out of tf/console.log, queries the server with A2S for live player
counts, and publishes the result as JSON to a GitHub gist. The MOTD page on
Cloudflare Pages reads that gist.

No third-party dependencies: standard library only.

Typical usage
-------------
    python scripts/update_gist.py --create     # first time: create the gist
    python scripts/update_gist.py --once       # update it once
    python scripts/update_gist.py --loop --interval 30
    python scripts/update_gist.py --dry-run    # print JSON, don't publish
    python scripts/update_gist.py --mock       # offline demo data

Token resolution order:
    1. environment variable named by config["token_env"] (default GITHUB_GIST_TOKEN)
    2. `gh auth token` (reuses the GitHub CLI login)

Exit codes: 0 ok, 1 runtime error, 2 configuration/auth error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MOTD_VERSION = "1.0.0"
APPID = 440
GIST_API = "https://api.github.com/gists"
GIST_DESCRIPTION = "gabes little server! - live MOTD status (auto-updated)"
FAKEIP_RE = re.compile(r"FakeIP allocation succeeded:\s*(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DEFAULT_CONFIG_PATH = BASE / "config.json"
STATE_PATH = BASE / "state.json"
LOG_PATH = BASE / "updater.log"
SITE_URL_FILE = ROOT / "assets" / "status-url.js"
SITE_FALLBACK = ROOT / "assets" / "status.json"

DEFAULT_CONFIG: dict = {
    "gist_id": "",
    "gist_filename": "status.json",
    "token_env": "GITHUB_GIST_TOKEN",
    "allow_gh_cli": True,
    "query_host": "auto",
    "query_port": 27015,
    "query_timeout": 2.0,
    "query_retries": 2,
    "server_dir": "C:/TF2server",
    "console_log": "C:/TF2server/tf/console.log",
    "console_log_fallback": "C:/TF2server/console.log",
    "mode_file": "C:/TF2server/tf/motd_mode.txt",
    "workshop_maps": ["workshop/899335714"],
    "map_pretty": {
        "mvm_powerplant_rc5": "Powerplant",
        "plr_highertower": "PLR Highertower",
        "workshop/899335714": "PLR Highertower",
    },
    "bot_name_prefixes": ["BOT"],
    "modes": {
        "mvm": {
            "label": "mvm random events",
            "pretty": "MvM Random Effects",
            "maxplayers": 10,
        },
        "plr": {
            "label": "plr highertower random events",
            "pretty": "PLR Highertower Random Effects",
            "maxplayers": 32,
        },
    },
}

# ---------------------------------------------------------------------------
# configuration / logging
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError) as exc:
            log(f"config: could not read {path}: {exc}", error=True)
    else:
        save_json(path, cfg)
        log(f"config: created default {path}")
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    save_json(path, cfg)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    try:
        save_json(STATE_PATH, state)
    except OSError as exc:
        log(f"state: could not save: {exc}", error=True)


def log(message: str, error: bool = False) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {'ERROR ' if error else ''}{message}"
    print(line, flush=True)
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            LOG_PATH.unlink()
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# local server files
# ---------------------------------------------------------------------------


def read_mode_file(path: str) -> tuple[str, int]:
    """Return (first non-empty line, file mtime). Missing file -> ("", 0)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        mtime = int(p.stat().st_mtime)
    except OSError:
        return "", 0
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line, mtime
    return "", 0


def read_tail_text(path: str, max_bytes: int = 262144) -> str:
    p = Path(path)
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
            data = fh.read()
        return data.decode("utf-8", "replace")
    except OSError:
        return ""


def find_console_log(cfg: dict) -> str:
    for key in ("console_log", "console_log_fallback"):
        candidate = cfg.get(key)
        if candidate and Path(candidate).exists():
            return candidate
    return "" 


def parse_fakeip(text: str) -> tuple[str, int]:
    """Last `FakeIP allocation succeeded: ip:port` line wins."""
    matches = FAKEIP_RE.findall(text or "")
    for ip, port in reversed(matches):
        if _valid_ipv4(ip) and 0 < int(port) <= 65535:
            return ip, int(port)
    return "", 0


def _valid_ipv4(ip: str) -> bool:
    parts = ip.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


# ---------------------------------------------------------------------------
# A2S (Source server query) - stdlib only
# ---------------------------------------------------------------------------

A2S_INFO_PAYLOAD = b"\xFF\xFF\xFF\xFFTSource Engine Query\x00"
A2S_PLAYER_PAYLOAD = b"\xFF\xFF\xFF\xFF\x55\xFF\xFF\xFF\xFF"


def _recv_packet(sock: socket.socket) -> bytes:
    data, _ = sock.recvfrom(65535)
    return data


def _read_response(sock: socket.socket) -> bytes:
    data = _recv_packet(sock)
    # 0xFFFFFFFE = split response: 4 header, 4 id, 1 total, 1 number, 2 size
    if len(data) >= 12 and data[:4] == b"\xFE\xFF\xFF\xFF":
        total = data[8]
        chunks = {data[9]: data[12:]}
        while len(chunks) < total:
            more = _recv_packet(sock)
            if len(more) >= 12 and more[:4] == b"\xFE\xFF\xFF\xFF":
                chunks[more[9]] = more[12:]
        data = b"".join(chunks[i] for i in sorted(chunks))
    return data


def _send_recv(host: str, port: int, payload: bytes, timeout: float) -> bytes | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(payload, (host, port))
        return _read_response(sock)
    except (socket.timeout, OSError):
        return None
    finally:
        sock.close()


def _read_cstr(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\x00", pos)
    if end < 0:
        raise ValueError("unterminated string")
    return data[pos:end].decode("utf-8", "replace"), end + 1


def parse_info(data: bytes) -> dict | None:
    """Parse an A2S_INFO reply, or None if it is not one."""
    if not data or len(data) < 8 or data[:4] != b"\xFF\xFF\xFF\xFF" or data[4:5] != b"I":
        return None
    try:
        pos = 6  # 4 header + 'I' + protocol version
        name, pos = _read_cstr(data, pos)
        map_name, pos = _read_cstr(data, pos)
        folder, pos = _read_cstr(data, pos)
        game, pos = _read_cstr(data, pos)
        pos += 2  # app id
        players = data[pos]
        maxplayers = data[pos + 1]
        bots = data[pos + 2]
    except (IndexError, ValueError):
        return None
    return {
        "name": name,
        "map": map_name,
        "folder": folder,
        "game": game,
        "players": players,
        "maxplayers": maxplayers,
        "bots": bots,
    }


def parse_players(data: bytes) -> list[dict] | None:
    """Parse an A2S_PLAYER reply into [{name, score, duration}]."""
    if not data or len(data) < 6 or data[:4] != b"\xFF\xFF\xFF\xFF" or data[4:5] != b"D":
        return None
    count = data[5]
    pos = 6
    out: list[dict] = []
    for _ in range(count):
        if pos >= len(data):
            break
        pos += 1  # player index
        try:
            name, pos = _read_cstr(data, pos)
        except ValueError:
            break
        if pos + 8 > len(data):
            break
        score = struct.unpack_from("<i", data, pos)[0]
        duration = struct.unpack_from("<f", data, pos + 4)[0]
        pos += 8
        out.append({"name": name, "score": score, "duration": duration})
    return out


def query_players(host: str, port: int, timeout: float, retries: int) -> list[dict] | None:
    """A2S_PLAYER with challenge handling."""
    for _ in range(retries + 1):
        data = _send_recv(host, port, A2S_PLAYER_PAYLOAD, timeout)
        if not data:
            return None
        if len(data) >= 9 and data[4:5] == b"A":  # challenge
            data = _send_recv(host, port, b"\xFF\xFF\xFF\xFF\x55" + data[5:9], timeout)
        if data and data[4:5] == b"D":
            parsed = parse_players(data)
            if parsed is not None:
                return parsed
    return None


def query_hosts(cfg: dict) -> list[str]:
    """Hosts to try, in order. `auto` finds the machine's LAN address first."""
    configured = str(cfg.get("query_host") or "auto").strip()
    if configured and configured.lower() != "auto":
        return [configured]

    hosts: list[str] = []

    def add(ip: str) -> None:
        ip = (ip or "").strip()
        if ip and ip not in hosts:
            hosts.append(ip)

    # primary outbound interface (no packets are sent for a UDP connect)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        pass

    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(entry[4][0])
    except OSError:
        pass

    add("127.0.0.1")
    return hosts


def query_server(cfg: dict) -> dict | None:
    port = int(cfg.get("query_port", 27015))
    timeout = float(cfg.get("query_timeout", 2.0))
    retries = int(cfg.get("query_retries", 2))

    for host in query_hosts(cfg):
        info = None
        for _ in range(retries + 1):
            raw = _send_recv(host, port, A2S_INFO_PAYLOAD, timeout)
            if raw and len(raw) >= 9 and raw[4:5] == b"A":
                # newer servers answer A2S_INFO with a challenge first
                raw = _send_recv(host, port, A2S_INFO_PAYLOAD + raw[5:9], timeout)
            info = parse_info(raw) if raw else None
            if info:
                break
        if not info:
            continue

        info["query_host"] = host
        players = query_players(host, port, timeout, retries)
        if players is not None:
            info["player_list"] = players
        return info
    return None


# ---------------------------------------------------------------------------
# status building
# ---------------------------------------------------------------------------


def detect_mode(label: str, map_name: str, cfg: dict) -> str:
    text = (label or "").lower()
    if "mvm" in text:
        return "mvm"
    if "highertower" in text or "plr" in text:
        return "plr"

    m = (map_name or "").lower()
    if m.startswith("mvm") or "mvm" in m:
        return "mvm"
    if "highertower" in m or m in [w.lower() for w in cfg.get("workshop_maps", [])]:
        return "plr"
    return ""


def pretty_map(cfg: dict, map_name: str) -> str:
    if not map_name:
        return ""
    table = cfg.get("map_pretty", {})
    if map_name in table:
        return table[map_name]
    lower = {k.lower(): v for k, v in table.items()}
    return lower.get(map_name.lower(), map_name)


def connect_url(ip: str, port: int) -> str:
    if not ip or not port:
        return ""
    return f"steam://connect/{ip}:{port}?appid={APPID}"


def is_bot_name(name: str, prefixes: list[str]) -> bool:
    cleaned = (name or "").strip().upper()
    return any(cleaned.startswith(str(p).strip().upper()) for p in prefixes if str(p).strip())


def build_status(
    cfg: dict,
    mode_label: str,
    mode_mtime: int,
    fakeip: tuple[str, int],
    info: dict | None,
    state: dict,
    now: int | None = None,
) -> dict:
    now = int(time.time()) if now is None else int(now)
    online = info is not None
    map_name = (info or {}).get("map", "") or (state.get("last_map", "") if not online else "")
    mode = detect_mode(mode_label, map_name, cfg) or state.get("last_mode", "")

    ip, port = fakeip
    if not ip or not port:
        ip = state.get("last_ip", "")
        port = int(state.get("last_port", 0) or 0)

    mode_cfg = cfg.get("modes", {}).get(mode, {})

    players = 0
    bots = 0
    maxplayers = 0
    if info:
        maxplayers = int(info.get("maxplayers", 0) or 0)
        player_list = info.get("player_list")
        if isinstance(player_list, list) and player_list:
            prefixes = cfg.get("bot_name_prefixes") or ["BOT"]
            bots = sum(1 for p in player_list if is_bot_name(p.get("name", ""), prefixes))
            players = max(0, len(player_list) - bots)
        else:
            players = int(info.get("players", 0) or 0)
            bots = int(info.get("bots", 0) or 0)
    if not maxplayers:
        maxplayers = int(mode_cfg.get("maxplayers", 0) or 0)

    last_seen = now if online else int(state.get("last_seen", 0) or 0)

    return {
        "schema": 1,
        "generated_at": now,
        "motd_version": MOTD_VERSION,
        "online": online,
        "mode": mode,
        "mode_pretty": mode_cfg.get("pretty", ""),
        "version": mode_label or (mode_cfg.get("label", "") if online else ""),
        "map": map_name,
        "map_pretty": pretty_map(cfg, map_name),
        "players": players,
        "bots": bots,
        "maxplayers": maxplayers,
        "ip": ip,
        "port": port,
        "connect": connect_url(ip, port) if online else "",
        "running_since": int(mode_mtime or 0) if online else 0,
        "last_seen": last_seen,
    }


# ---------------------------------------------------------------------------
# GitHub gist
# ---------------------------------------------------------------------------


def resolve_token(cfg: dict) -> str:
    env_name = cfg.get("token_env") or "GITHUB_GIST_TOKEN"
    token = (os.environ.get(env_name) or "").strip()
    if token:
        return token
    if not cfg.get("allow_gh_cli", True):
        return ""
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def api_request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "gabes-motd-updater")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw else {}


def gist_payload(cfg: dict, status: dict) -> dict:
    return {
        "description": GIST_DESCRIPTION,
        "files": {
            cfg.get("gist_filename", "status.json"): {
                "content": json.dumps(status, indent=2) + "\n"
            }
        },
    }


def create_gist(cfg: dict, token: str, status: dict) -> dict:
    payload = gist_payload(cfg, status)
    payload["public"] = False
    return api_request("POST", GIST_API, token, payload)


def update_gist(cfg: dict, token: str, status: dict) -> dict:
    gist_id = cfg.get("gist_id") or ""
    if not gist_id:
        raise RuntimeError("no gist_id configured - run --create first")
    return api_request("PATCH", f"{GIST_API}/{gist_id}", token, gist_payload(cfg, status))


def gist_raw_url(owner: str, gist_id: str, filename: str) -> str:
    return f"https://gist.githubusercontent.com/{owner}/{gist_id}/raw/{filename}"


def write_site_url(url: str) -> None:
    content = (
        "// Generated by scripts/update_gist.py --create.\n"
        "// Commit this file so the MOTD knows where to read live status from.\n"
        f'window.MOTD_STATUS_URL = {json.dumps(url)};\n'
    )
    SITE_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SITE_URL_FILE.write_text(content, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# collection + main
# ---------------------------------------------------------------------------


def mock_info() -> dict:
    return {
        "name": "gabes little server! | highertower random events!",
        "map": "workshop/899335714",
        "folder": "tf",
        "game": "Team Fortress",
        "players": 7,
        "maxplayers": 32,
        "bots": 3,
        "player_list": (
            [{"name": n, "score": 0, "duration": 60.0} for n in
             ("gabe", "heavy main", "scout enjoyer", "spy crab", "f2p andy", "medic gf", "cart pusher")]
            + [{"name": n, "score": 0, "duration": 60.0} for n in
               ("BOT Gabe", "BOT Steve", "BOT Larry")]
        ),
    }


def collect(cfg: dict, state: dict, use_mock: bool) -> dict:
    mode_label, mode_mtime = read_mode_file(cfg.get("mode_file", ""))

    if use_mock:
        if not mode_label:
            mode_label = "plr highertower random events"
        mode_mtime = mode_mtime or int(time.time())
        fakeip = ("169.254.97.94", 2856)
        info = mock_info()
    else:
        log_path = find_console_log(cfg)
        text = read_tail_text(log_path) if log_path else ""
        fakeip = parse_fakeip(text)
        if not fakeip[0]:
            if state.get("last_ip"):
                log("console.log: no FakeIP line yet, using cached address")
            else:
                log("console.log: no FakeIP allocation line found yet")
        info = query_server(cfg)

    status = build_status(cfg, mode_label, mode_mtime, fakeip, info, state)
    return status


def remember(state: dict, status: dict) -> dict:
    state.update(
        {
            "last_ip": status.get("ip", ""),
            "last_port": status.get("port", 0),
            "last_mode": status.get("mode", ""),
            "last_map": status.get("map", ""),
            "last_seen": status.get("last_seen", 0),
            "last_published": status.get("generated_at", 0),
        }
    )
    return state


def print_status(status: dict) -> None:
    print(json.dumps(status, indent=2), flush=True)


def run_once(cfg: dict, args) -> int:
    state = load_state()
    status = collect(cfg, state, args.mock)
    if not args.mock:
        save_state(remember(state, status))

    if args.mock:
        print_status(status)
        log("mock mode: not publishing")
        return 0

    if args.write:
        try:
            save_json(SITE_FALLBACK, status)
            log(f"wrote {SITE_FALLBACK}")
        except OSError as exc:
            log(f"could not write site fallback: {exc}", error=True)

    if args.dry_run:
        print_status(status)
        log("dry run: not publishing")
        return 0

    if not cfg.get("gist_id"):
        print_status(status)
        log("no gist configured: run `python scripts/update_gist.py --create`", error=True)
        return 2

    token = resolve_token(cfg)
    if not token:
        print_status(status)
        log("no GitHub token: set GITHUB_GIST_TOKEN or run `gh auth login`", error=True)
        return 2

    update_gist(cfg, token, status)
    log(
        "published: online={online} mode={mode} players={players}+{bots} map={map}".format(
            online=status["online"],
            mode=status["mode"] or "unknown",
            players=status["players"],
            bots=status["bots"],
            map=status["map"] or "n/a",
        )
    )
    return 0


def create(cfg: dict, cfg_path: Path, args) -> int:
    state = load_state()
    status = collect(cfg, state, args.mock)
    if not args.mock:
        save_state(remember(state, status))

    if args.dry_run:
        print_status(status)
        log("dry run: would create gist")
        return 0

    token = resolve_token(cfg)
    if not token:
        log("no GitHub token: set GITHUB_GIST_TOKEN or run `gh auth login`", error=True)
        return 2

    created = create_gist(cfg, token, status)
    gist_id = created.get("id", "")
    owner = (created.get("owner") or {}).get("login", "")
    if not gist_id or not owner:
        log(f"unexpected gist response: {created}", error=True)
        return 1

    cfg["gist_id"] = gist_id
    save_config(cfg_path, cfg)
    url = gist_raw_url(owner, gist_id, cfg.get("gist_filename", "status.json"))
    write_site_url(url)

    log(f"created gist {created.get('html_url', gist_id)}")
    log(f"status URL: {url}")
    log(f"wrote {SITE_URL_FILE} - commit this file and push")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish gabes little server! status to a gist")
    parser.add_argument("--once", action="store_true", help="update once, then exit (default)")
    parser.add_argument("--loop", action="store_true", help="keep updating in a loop")
    parser.add_argument("--interval", type=int, default=30, help="seconds between updates (default 30)")
    parser.add_argument("--dry-run", action="store_true", help="print JSON without publishing")
    parser.add_argument("--create", action="store_true", help="create the gist and write assets/status-url.js")
    parser.add_argument("--write", action="store_true", help="also write assets/status.json fallback")
    parser.add_argument("--mock", action="store_true", help="use demo values, never touch the network")
    parser.add_argument("--verbose", action="store_true", help="accepted for compatibility")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="path to config.json")
    args = parser.parse_args(argv)

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)

    if args.create:
        return create(cfg, cfg_path, args)

    if args.loop:
        log(f"loop: every {args.interval}s (Ctrl+C to stop)")
        try:
            while True:
                run_once(cfg, args)
                time.sleep(max(5, args.interval))
        except KeyboardInterrupt:
            log("loop stopped")
            return 0

    return run_once(cfg, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        log(f"GitHub HTTP {exc.code}: {detail}", error=True)
        sys.exit(1)
    except urllib.error.URLError as exc:
        log(f"network error: {exc}", error=True)
        sys.exit(1)
