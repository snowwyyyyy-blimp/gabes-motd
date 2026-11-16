# Setting up the gist

The MOTD reads a tiny JSON file from a GitHub gist. `scripts/update_gist.py` writes it every 30 seconds with the mode, players, map, and current connect address.

## 1. Auth

The script accepts a token in this order:

1. Environment variable named by `token_env` in `scripts/config.json` (default `GITHUB_GIST_TOKEN`).
2. `gh auth token` — reuses the GitHub CLI login.

If `gh auth status` already shows you logged in, nothing else is needed.

If you would rather use a plain token, create a **classic** personal access token with the `gist` scope at <https://github.com/settings/tokens>, then:

```bat
setx GITHUB_GIST_TOKEN "ghp_yourtokenhere"
```

Open a new terminal afterwards so the variable is picked up.

## 2. Create the gist

From the repo root:

```bat
python scripts\update_gist.py --create
```

This:

- queries the local server (or produces an offline payload if it is not running),
- creates a **secret** gist named after `gist_filename` (`status.json`),
- saves the gist id into `scripts/config.json`,
- writes `assets/status-url.js` with the raw URL the site fetches.

Commit `assets/status-url.js`. Do **not** commit `scripts/config.json` (it is ignored).

Example output:

```
created gist https://gist.github.com/you/0123456789abcdef
status URL: https://gist.githubusercontent.com/you/0123456789abcdef/raw/status.json
wrote ...\assets\status-url.js - commit this file and push
```

## 3. Update it manually

```bat
python scripts\update_gist.py --once --write
```

- `--once` is the default.
- `--write` also refreshes `assets/status.json`, the offline fallback the page uses.
- `--dry-run` prints the JSON without publishing.
- `--mock` uses demo values and never touches the network.

Check the raw URL in a browser — you should see the JSON.

## 4. Run it automatically

Create a Task Scheduler task:

| Setting | Value |
|---|---|
| Trigger | At log on (or at startup) |
| Action | Start a program |
| Program | `C:\path\to\gabes-motd\scripts\run_updater.bat` |
| Start in | `C:\path\to\gabes-motd` |
| Run whether user is logged on or not | optional; `gh auth token` needs your user profile |

The batch file starts `pythonw` with `--loop --interval 30 --write`, so there is no console window and the fallback file stays fresh.

Logs go to `scripts/updater.log` (rotated at 1 MB).

## 5. Using an existing gist

Put its id in `scripts/config.json`:

```json
{
  "gist_id": "0123456789abcdef"
}
```

and set the raw URL by hand in `assets/status-url.js`:

```js
window.MOTD_STATUS_URL = "https://gist.githubusercontent.com/you/0123456789abcdef/raw/status.json";
```
