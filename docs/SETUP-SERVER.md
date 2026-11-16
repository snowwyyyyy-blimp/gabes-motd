# Server-side setup

Two pieces live on the game server: the mode file written by the launch `.bat`, and the `-condebug` console log the updater scrapes.

## 1. Launch scripts (already patched)

`C:\TF2server\start_tf2_highertower.bat`:

```bat
@echo off
title gabes little server! ^| DODGEBALL!

:: Set to your TF2 server folder
cd /d "C:\TF2server"
(echo plr highertower random events)> "C:\TF2server\tf\motd_mode.txt"

:: Create logs folder
if not exist "logs" mkdir logs

start "" "C:\TF2server\srcds.exe" -game tf -console -usercon +ip 0.0.0.0 -port 27015 -tvport 27020 -enablefakeip +maxplayers 32 +map workshop/899335714 +exec server.cfg +sv_setsteamaccount <GSLT> +exec unload_dodgeball.cfg -condebug
```

`C:\TF2server\start_tf2_randomvm.bat` is identical except for:

```bat
(echo mvm random events)> "C:\TF2server\tf\motd_mode.txt"
...
+map mvm_powerplant_rc5 ...
```

What matters:

- `(echo ...)> tf\motd_mode.txt` writes the mode label. The updater publishes that string as the server "version" and uses the file's modification time for "running since".
- `-condebug` makes the server mirror its console into `tf\console.log`. The updater searches that log for `FakeIP allocation succeeded: <ip>:<port>`.
- The fake IP changes every restart, which is why the page never hardcodes it.

Backups of the original batch files are next to them as `.bat.bak`.

## 2. MOTD convars

In `C:\TF2server\tf\cfg\server.cfg`:

```
motd_enabled 1
motd_url "https://<your-pages-site>.pages.dev/"
```

Apply with `exec server.cfg` or a restart.

If a map config sets `hostname`, it may also be a good place to keep a per-mode `motd_url`. Current map config for MvM: `tf/cfg/mvm_powerplant_rc5.cfg`.

## 3. Confirm the log line exists

After a restart, open `C:\TF2server\tf\console.log` and search for:

```
FakeIP allocation succeeded: 169.254.x.x:xxxxx
```

- If the file is missing, `-condebug` did not reach `srcds.exe`.
- If the line is missing, `-enablefakeip` is not active.
- If there are several matches, the updater uses the **last** one.

The updater also tries `C:\TF2server\console.log` as a fallback path.

## 4. Confirm the query port

The updater asks `127.0.0.1:27015` for A2S_INFO / A2S_PLAYER. That is the real listening port, not the fake IP. If you change `-port`, change `query_port` in `scripts/config.json` too.

Bots are counted by name prefix (`BOT` by default) from A2S_PLAYER. Adjust `bot_name_prefixes` if your bots are renamed.

## 5. Version bumps

The "version" shown on the site is the literal content of `tf/motd_mode.txt`. Keep it human-readable:

```
plr highertower random events
mvm random events
```

Change the strings in the batch files (and the two `label` values in `scripts/config.json`) if you rename a mode.
