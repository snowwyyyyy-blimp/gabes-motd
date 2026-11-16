@echo off
title MOTD preview - close this window to stop
cd /d "%~dp0"
echo.
echo   gabes-motd local preview
echo   ------------------------
echo   URL:  http://127.0.0.1:8099/
echo.
echo   Leave this window open while you test.
echo   Close it (or press Ctrl+C) to stop the preview.
echo.
start "" "http://127.0.0.1:8099/"
python -m http.server 8099
