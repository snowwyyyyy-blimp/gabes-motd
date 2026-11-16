# Status format

One JSON object, published to `status.json` in the gist and written to `assets/status.json` with `--write`.

```json
{
  "schema": 1,
  "generated_at": 1763412345,
  "motd_version": "1.0.0",
  "online": true,
  "mode": "plr",
  "mode_pretty": "PLR Highertower Random Effects",
  "version": "plr highertower random events",
  "map": "workshop/899335714",
  "map_pretty": "PLR Highertower",
  "players": 7,
  "bots": 3,
  "maxplayers": 32,
  "ip": "169.254.97.94",
  "port": 2856,
  "connect": "steam://connect/169.254.97.94:2856?appid=440",
  "running_since": 1763412000,
  "last_seen": 1763412340
}
```

## Fields

| Field | Meaning |
|---|---|
| `schema` | Version of this format. Currently `1`. |
| `generated_at` | Unix seconds when the updater built the payload. Drives the staleness check. |
| `motd_version` | Version of the site/script pair. Shown in the footer. |
| `online` | `true` only if A2S_INFO answered. |
| `mode` | `mvm` or `plr`, detected from the mode file, then the map name. |
| `mode_pretty` | Display name from `modes.<mode>.pretty` in `config.json`. |
| `version` | Raw mode label written by the launch `.bat` (`mvm random events`, `plr highertower random events`). |
| `map` | Raw map name from the server (`workshop/899335714`). |
| `map_pretty` | Friendly map name from `map_pretty` in config. |
| `players` | Human players (A2S_PLAYER entries whose name does not start with a bot prefix). |
| `bots` | Players whose name starts with a `bot_name_prefixes` entry. |
| `maxplayers` | Slot count from A2S_INFO, falling back to the mode's `maxplayers`. |
| `ip` | Fake IP from the last `FakeIP allocation succeeded:` line, or the cached value. |
| `port` | Port from the same line, or the cached value. |
| `connect` | `steam://connect/<ip>:<port>?appid=440`. Empty when offline. |
| `running_since` | Modification time of `tf/motd_mode.txt` (unix seconds). Empty/0 when offline. |
| `last_seen` | Last moment A2S answered. Preserved while offline. |

## How the page uses it

- Fetches `window.MOTD_STATUS_URL` with a `?t=<now>` cache buster.
- Falls back to the last good copy in `localStorage`, then to `assets/status.json`.
- Refreshes every 30 seconds.
- Treats `generated_at` older than **180 seconds** as stale: shows the amber `STALE` badge and a warning, but keeps the last known address so the join button can still work.
- `online: false` shows the red `OFFLINE` panel and hides the join button.
- Marks the matching `.mode-card[data-mode]` with a green `Running now` tag.

## Updater flags

| Flag | Effect |
|---|---|
| `--once` | One collection pass (default). |
| `--loop` | Keep collecting every `--interval` seconds (default 30). |
| `--dry-run` | Print the payload, do not publish. |
| `--mock` | Demo values, no network, no disk writes unless `--write` is also given. |
| `--write` | Also write `assets/status.json`. |
| `--create` | Create the gist, save its id, write `assets/status-url.js`. |
| `--config PATH` | Use a different config file. |

Exit codes: `0` success, `1` runtime/network error, `2` missing gist id or token.
