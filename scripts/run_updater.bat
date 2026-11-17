@echo off
REM Runs the MOTD status updater in the background (no console window).
REM Schedule this at logon / startup with Task Scheduler.
setlocal
cd /d "%~dp0.."

where pythonw >nul 2>&1
if errorlevel 1 (
    python "%~dp0update_gist.py" --loop --interval 60 --write
) else (
    pythonw "%~dp0update_gist.py" --loop --interval 60 --write
)
