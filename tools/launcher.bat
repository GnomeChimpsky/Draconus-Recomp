@echo off
rem Double-click wrapper for the graphical launcher.
setlocal
cd /d "%~dp0.."
python "tools\launcher.py" %*
if errorlevel 1 pause
exit /b %errorlevel%
