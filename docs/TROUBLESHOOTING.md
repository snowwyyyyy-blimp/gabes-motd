# Troubleshooting

## The MOTD does not appear in game

- `motd.txt` and `motd_text.txt` must exist in `C:\TF2server\tf\` and contain the URL, not a `motd_url` convar (TF2 has none).
- Some players set `cl_disablehtmlmotd 1`. That is client-side; nothing on the server overrides it.
- Test the URL in a normal browser first. If it loads there, it loads in TF2.
- TF2's in-game browser is old: no external fonts, no heavy libraries. This site sticks to plain HTML/CSS/JS on purpose.

## The page loads but the status says UNKNOWN

- `assets/status-url.js` still has an empty `MOTD_STATUS_URL`. Run `python scripts\update_gist.py --create` and commit the generated file.
- Gist fetches are blocked or offline. The page falls back to `localStorage`, then `assets/status.json`.
- Open the raw gist URL in a browser. If it 404s, the gist id in `scripts/config.json` is wrong.

## Status is STALE

- The updater is not running. Start `scripts\run_updater.bat` or check the Task Scheduler entry.
- Look at `scripts/updater.log` for `ERROR` lines.
- `gh auth token` fails when the task runs as another user or without your profile loaded. Either run the task as your own user or set `GITHUB_GIST_TOKEN` as a machine-level variable.

## Status says OFFLINE while the server is up

- A2S is being answered on a different port. Set `query_port` in `scripts/config.json` to the real `-port`.
- The server only just started and the updater ran before it was listening. It retries every 30 seconds.
- `sv_lan 1` can change query behaviour; this server uses `sv_lan 0`.

## The connect button has the wrong IP

- The fake IP rotates per restart. Give the updater one cycle (30 s) after a restart.
- If `tf/console.log` has no `FakeIP allocation succeeded:` line, `-condebug` or `-enablefakeip` is missing from the launch command.
- In a pinch, edit `scripts/state.json` (`last_ip`, `last_port`) and the next run will use it until the log line appears.

## Players count looks wrong

- `players` comes from A2S_PLAYER, minus names that start with `BOT`. Renamed bots are not detected — add their prefix to `bot_name_prefixes` in `scripts/config.json`.
- If A2S_PLAYER is unavailable, the script falls back to the A2S_INFO counters, which may include bots in `players`.

## GitHub errors

- `401` — token invalid or expired. Re-run `gh auth login`, or refresh `GITHUB_GIST_TOKEN`.
- `403` — rate limited or token missing the `gist` scope. The script logs the response body.
- `404` on PATCH — wrong `gist_id`, or the gist belongs to another account.
- The updater never writes the token to disk or into the repo. `scripts/config.json`, `scripts/state.json` and `scripts/updater.log` are gitignored.

## Cloudflare Pages deploys but the page is an old copy

- `_headers` marks `index.html`, `assets/status.json` and `assets/status-url.js` as `no-store`.
- The browser may cache `motd.js` for 5 minutes. Bump `?v=` on the `motd_url`, or purge cache in the dashboard.

## Tests fail

```bat
python scripts\test_updater.py
```

The tests are offline and use synthetic A2S packets. They should always pass; if they do not, something changed in `update_gist.py` that the tests were not updated for.
