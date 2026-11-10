@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 "tools\bootstrap.py" %*
goto finished
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python "tools\bootstrap.py" %*
goto finished
:missing_python
echo Install Python 3.13 or newer from https://www.python.org/downloads/
if not defined CI pause
exit /b 1
:finished
set "festavia_exit=%errorlevel%"
if "%~1"=="--help" goto no_pause
if defined CI goto no_pause
pause
:no_pause
exit /b %festavia_exit%
