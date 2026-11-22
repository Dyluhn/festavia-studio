@echo off
cd /d "%~dp0"
py -3 make_track.py %*
if errorlevel 1 pause
