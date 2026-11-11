@echo off
rem Play with the speed diagnostic on. Every call that falls back to the interpreter is counted and
rem the hottest targets are printed when the run ends. Quit with Escape, then send work\speed-report.txt
rem (or just its "untranslated top targets" block) back for seeding.
rem
rem   tools\diagnose-speed.bat                 # window, translated path
rem   tools\diagnose-speed.bat -Scale 2        # arguments pass through to play-draconus.ps1
setlocal
set DREAM_TRACE_UNTRANSLATED=1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\play-draconus.ps1" %* > "%~dp0..\work\speed-report.txt" 2>&1
set CODE=%ERRORLEVEL%
endlocal
echo.
echo Report written to work\speed-report.txt
echo The block that matters starts with "untranslated top targets".
if not "%CODE%"=="0" echo The launcher exited with %CODE%.
pause
