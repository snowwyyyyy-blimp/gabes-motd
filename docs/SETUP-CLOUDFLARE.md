# Hosting the MOTD on Cloudflare Pages

The site is plain static HTML/CSS/JS — no build step.

## 1. Push the repo

The repo is already initialised locally.

```bat
git remote add origin https://github.com/<you>/gabes-motd.git
git branch -M main
git push -u origin main
```

## 2. Connect it in Cloudflare

1. Open <https://dash.cloudflare.com> → **Workers & Pages**.
2. **Create** → **Pages** → **Connect to Git**.
3. Authorise GitHub and pick the `gabes-motd` repository.
4. Build settings:

   | Setting | Value |
   |---|---|
   | Framework preset | None |
   | Build command | *(leave empty)* |
   | Build output directory | `/` |
   | Root directory | `/` |

5. **Save and Deploy**.

You get a URL like `https://gabes-motd.pages.dev`. Every push to `main` redeploys automatically.

## 3. Point the server at it

In `C:\TF2server\tf\cfg\server.cfg`:

```
motd_enabled 1
motd_url "https://gabes-motd.pages.dev/"
```

The MvM map config (`tf/cfg/mvm_powerplant_rc5.cfg`) can override it if you ever want a different page per mode. Reload with `exec server.cfg` from RCON or restart.

> TF2 clients can disable HTML MOTDs with `cl_disablehtmlmotd 1`. Nothing server-side can force it back on; the Discord link and the server browser still work for those players.

## 4. Cache behaviour

`_headers` sets:

- `index.html`, `assets/status.json`, `assets/status-url.js` → `no-store`
- CSS/JS → 5 minute cache

Cloudflare Pages applies `_headers` automatically. If a deploy ever looks stuck, purge the cache in the dashboard or append `?v=2` to the `motd_url`.

## 5. Local preview

```bat
cd /d C:\Users\Pichau\gabes-motd
python -m http.server 8080
```

Then open <http://localhost:8080/>.

To preview the live panel with mock data without publishing anything:

```bat
python scripts\update_gist.py --mock --write
python -m http.server 8080
```

`--mock` writes nothing unless `--write` is also passed. To preview a specific file, use `?status=./assets/status.json`.
