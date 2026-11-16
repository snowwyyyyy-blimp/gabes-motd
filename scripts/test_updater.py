#!/usr/bin/env python3
"""Tests for scripts/update_gist.py. Standard library only.

Run from the repo root:

    python scripts/test_updater.py
    python -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import update_gist as up  # noqa: E402


def a2s_info_packet(
    name: str = "gabes little server!",
    map_name: str = "plr_highertower",
    folder: str = "tf",
    game: str = "Team Fortress",
    players: int = 5,
    maxplayers: int = 32,
    bots: int = 2,
) -> bytes:
    return (
        b"\xFF\xFF\xFF\xFF"
        + b"I"
        + bytes([17])
        + name.encode() + b"\x00"
        + map_name.encode() + b"\x00"
        + folder.encode() + b"\x00"
        + game.encode() + b"\x00"
        + struct.pack("<H", 440)
        + bytes([players, maxplayers, bots])
    )


def a2s_player_packet(entries: list[tuple[str, int, float]]) -> bytes:
    out = b"\xFF\xFF\xFF\xFF" + b"D" + bytes([len(entries)])
    for index, (name, score, duration) in enumerate(entries):
        out += bytes([index]) + name.encode() + b"\x00" + struct.pack("<if", score, duration)
    return out


class FakeIPTests(unittest.TestCase):
    def test_takes_last_match(self):
        text = (
            "FakeIP allocation succeeded: 169.254.1.1:1111\n"
            "nothing here\n"
            "FakeIP allocation succeeded: 169.254.97.94:2856\n"
        )
        self.assertEqual(up.parse_fakeip(text), ("169.254.97.94", 2856))

    def test_missing_line(self):
        self.assertEqual(up.parse_fakeip("no allocation yet"), ("", 0))
        self.assertEqual(up.parse_fakeip(""), ("", 0))

    def test_ignores_bad_ip(self):
        self.assertEqual(up.parse_fakeip("FakeIP allocation succeeded: 999.1.1.1:99"), ("", 0))


class ModeFileTests(unittest.TestCase):
    def test_reads_first_non_empty_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "motd_mode.txt"
            path.write_text("\n\nplr highertower random events\nmvm random events\n", encoding="utf-8")
            label, mtime = up.read_mode_file(str(path))
            self.assertEqual(label, "plr highertower random events")
            self.assertGreater(mtime, 0)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(up.read_mode_file(str(Path(tmp) / "nope.txt")), ("", 0))


class DetectModeTests(unittest.TestCase):
    cfg = {"workshop_maps": ["workshop/899335714"]}

    def test_from_label(self):
        self.assertEqual(up.detect_mode("mvm random events", "", self.cfg), "mvm")
        self.assertEqual(up.detect_mode("plr highertower random events", "", self.cfg), "plr")

    def test_from_map(self):
        self.assertEqual(up.detect_mode("", "mvm_powerplant_rc5", self.cfg), "mvm")
        self.assertEqual(up.detect_mode("", "workshop/899335714", self.cfg), "plr")

    def test_unknown(self):
        self.assertEqual(up.detect_mode("", "ctf_2fort", self.cfg), "")


class BotTests(unittest.TestCase):
    def test_prefixes(self):
        self.assertTrue(up.is_bot_name("BOT Gabe", ["BOT"]))
        self.assertTrue(up.is_bot_name("bot steve", ["BOT"]))
        self.assertFalse(up.is_bot_name("Gabe", ["BOT"]))
        self.assertFalse(up.is_bot_name("", ["BOT"]))


class PacketTests(unittest.TestCase):
    def test_parse_info(self):
        info = up.parse_info(a2s_info_packet(players=5, maxplayers=32, bots=2))
        self.assertIsNotNone(info)
        self.assertEqual(info["map"], "plr_highertower")
        self.assertEqual(info["players"], 5)
        self.assertEqual(info["maxplayers"], 32)
        self.assertEqual(info["bots"], 2)

    def test_parse_info_rejects_junk(self):
        self.assertIsNone(up.parse_info(b"\x00\x01\x02"))
        self.assertIsNone(up.parse_info(b"\xFF\xFF\xFF\xFF" + b"D" + b"\x00"))

    def test_parse_players(self):
        packet = a2s_player_packet([("gabe", 10, 61.5), ("BOT Steve", 3, 12.0)])
        players = up.parse_players(packet)
        self.assertIsNotNone(players)
        self.assertEqual(len(players), 2)
        self.assertEqual(players[0]["name"], "gabe")
        self.assertEqual(players[0]["score"], 10)
        self.assertEqual(players[1]["name"], "BOT Steve")


class StatusTests(unittest.TestCase):
    base_cfg = {
        "modes": {
            "mvm": {"label": "mvm random events", "pretty": "MvM Random Effects", "maxplayers": 10},
            "plr": {
                "label": "plr highertower random events",
                "pretty": "PLR Highertower Random Effects",
                "maxplayers": 32,
            },
        },
        "map_pretty": {"plr_highertower": "PLR Highertower"},
        "workshop_maps": ["workshop/899335714"],
        "bot_name_prefixes": ["BOT"],
    }

    def test_online_status(self):
        info = up.parse_info(a2s_info_packet(players=10, maxplayers=32, bots=3))
        info["player_list"] = [
            {"name": "gabe", "score": 0, "duration": 1.0},
            {"name": "medic gf", "score": 0, "duration": 1.0},
            {"name": "BOT Steve", "score": 0, "duration": 1.0},
        ]
        status = up.build_status(
            self.base_cfg,
            "plr highertower random events",
            1700000000,
            ("169.254.97.94", 2856),
            info,
            {},
            now=1700000100,
        )
        self.assertTrue(status["online"])
        self.assertEqual(status["mode"], "plr")
        self.assertEqual(status["players"], 2)
        self.assertEqual(status["bots"], 1)
        self.assertEqual(status["map_pretty"], "PLR Highertower")
        self.assertEqual(status["connect"], "steam://connect/169.254.97.94:2856?appid=440")
        self.assertEqual(status["generated_at"], 1700000100)
        self.assertEqual(status["running_since"], 1700000000)

    def test_offline_uses_cached_address(self):
        state = {
            "last_ip": "169.254.5.6",
            "last_port": 4242,
            "last_mode": "mvm",
            "last_map": "mvm_powerplant_rc5",
            "last_seen": 1600000000,
        }
        status = up.build_status(self.base_cfg, "", 0, ("", 0), None, state, now=1700000000)
        self.assertFalse(status["online"])
        self.assertEqual(status["players"], 0)
        self.assertEqual(status["ip"], "169.254.5.6")
        self.assertEqual(status["port"], 4242)
        self.assertEqual(status["connect"], "")
        self.assertEqual(status["last_seen"], 1600000000)
        self.assertEqual(status["mode"], "mvm")

    def test_online_prefers_fresh_fakeip(self):
        info = up.parse_info(a2s_info_packet())
        info["player_list"] = []
        state = {"last_ip": "1.1.1.1", "last_port": 1}
        status = up.build_status(
            self.base_cfg, "mvm random events", 0, ("169.254.9.9", 7777), info, state, now=1700000000
        )
        self.assertEqual(status["ip"], "169.254.9.9")
        self.assertEqual(status["port"], 7777)

    def test_gist_payload_is_valid_json(self):
        info = up.parse_info(a2s_info_packet())
        info["player_list"] = []
        status = up.build_status(self.base_cfg, "", 0, ("", 0), info, {}, now=1700000000)
        payload = up.gist_payload({"gist_filename": "status.json"}, status)
        content = payload["files"]["status.json"]["content"]
        self.assertEqual(json.loads(content)["schema"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
