# gabes-motd

The MOTD page for **gabes little server!**, plus the small Python service that keeps it honest.

The page is a static site (Cloudflare Pages ready). It shows the mode that is actually running, live player counts, the map, how long the server has been up, and a one-click `steam://connect` button. It also documents both server modes, the random chaos effects, the rules, and the Discord.

```
launch .bat  ──writes──►  tf/motd_mode.txt      "plr highertower random events"
srcds -condebug ───────►  tf/console.log        "FakeIP allocation succeeded: 169.254.x.x:PORT"
                                │
                    scripts/update_gist.py  (Task Scheduler, every 30s)
                                │  A2S on 127.0.0.1:27015 → players / bots / map
                                ▼
                          gist status.json
                                │
                    MOTD on Cloudflare Pages (fetch, refresh 30s)
```

## The two servers

| | MvM Random Effects | PLR Highertower Random Effects |
|---|---|---|
| Mode | Mann vs Machine | Payload Race |
| Map | `mvm_powerplant_rc5` | `plr_highertower` (workshop `899335714`) |
| Players | up to 10 defenders, 1 needed to start | 32 slots, 10 bots fill |
| Extras | mobile upgrades anywhere, infinite ammo, ready-up, chaos every ~30s | bhop, 20 minute maps, chaos every ~30s |
| Connect | from the live panel | from the live panel |

Only one runs at a time — both share the same install and port `27015`. The page always shows whichever one is up.

## Live panel

- **LIVE** — green badge, players (`7 + 3 bots / 32`), map, "running since", join button.
- **STALE** — amber badge; the updater stopped reporting more than 180 seconds ago. The last known address is still shown, plus a warning.
- **OFFLINE** — red badge, no join button, last seen address, Discord link.

The address is never hardcoded: the updater scrapes the fake IP that the server is assigned on each boot and rebuilds `steam://connect/<ip>:<port>?appid=440`.

## Repo layout

```
index.html                  the MOTD
assets/motd.css             dark theme, tuned for TF2's ~700x500 browser
assets/motd.js              gist fetch, staleness, connect button, 30s refresh
assets/status.json          last-resort offline fallback
assets/status-url.js        generated: where the live gist lives
_headers                    Cloudflare Pages cache rules
scripts/update_gist.py      mode file + console.log + A2S -> gist
scripts/run_updater.bat     pythonw loop for Task Scheduler
scripts/test_updater.py     16 offline tests
scripts/config.example.json reference config
scripts/fixtures/console.log sample log for the parser
docs/                       setup, status format, troubleshooting
```

## Quick start

1. **Create the gist** (needs `gh auth login` or `GITHUB_GIST_TOKEN`):

   ```bat
   python scripts\update_gist.py --create
   ```

   Commit the generated `assets/status-url.js`.

2. **Run the updater once** to check the payload:

   ```bat
   python scripts\update_gist.py --once --write --dry-run
   ```

3. **Schedule it:** Task Scheduler → at logon → `scripts\run_updater.bat`.

4. **Deploy:** push to GitHub, then Cloudflare Pages → Connect to Git → framework **None**, empty build command, output `/`. See [docs/SETUP-CLOUDFLARE.md](docs/SETUP-CLOUDFLARE.md).

5. **Point TF2 at it:** `motd_url "https://<site>.pages.dev/"` in `server.cfg`.

Full details: [gist](docs/SETUP-GIST.md) · [Cloudflare Pages](docs/SETUP-CLOUDFLARE.md) · [server side](docs/SETUP-SERVER.md) · [status format](docs/STATUS-FORMAT.md) · [troubleshooting](docs/TROUBLESHOOTING.md).

## Updater

Standard library only — no `pip install`. It resolves a token from `GITHUB_GIST_TOKEN`, then from `gh auth token`.

```bat
python scripts\update_gist.py --mock              # demo payload, no network
python scripts\update_gist.py --dry-run           # real payload, no publish
python scripts\update_gist.py --once --write      # publish + refresh fallback
python scripts\update_gist.py --loop --interval 30
python scripts\update_gist.py --create            # make the gist
```

It reads:

- `C:\TF2server\tf\motd_mode.txt` — written by the launch batch file.
- `C:\TF2server\tf\console.log` — tailed for the last `FakeIP allocation succeeded:` line.
- `127.0.0.1:27015` — A2S_INFO + A2S_PLAYER for online state, map, humans and bots.

It writes `status.json` to the gist (and `assets/status.json` with `--write`), logs to `scripts/updater.log`, and keeps a cached IP in `scripts/state.json` so a half-started server does not blank the connect button.

Never committed: `scripts/config.json` (holds the gist id), `scripts/state.json`, `scripts/updater.log`.

## Tests

```bat
python scripts\test_updater.py
```

Covers fake IP parsing (last match wins, invalid octets rejected), mode detection, the mode file, A2S packet parsing, bot filtering, online/offline status building, cached addresses, and the gist payload.

## License

MIT. See [LICENSE](LICENSE).
