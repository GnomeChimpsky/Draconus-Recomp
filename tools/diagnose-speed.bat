@echo off
rem Play with the speed diagnostic on. Every call that falls back to the interpreter is counted and
rem the hottest targets are printed when the run ends. Quit with Escape, then read
rem work\speed-report.txt: its "untranslated top targets" block names the routines a slow scene is
rem still interpreting.
rem
rem   tools\diagnose-speed.bat                 # window, translated path
rem   tools\diagnose-speed.bat -Scale 2        # arguments pass through to play-draconus.ps1
setlocal
if not exist "%~dp0..\work" mkdir "%~dp0..\work"
set DREAM_TRACE_UNTRANSLATED=1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\play-draconus.ps1" %* > "%~dp0..\work\speed-report.txt" 2>&1
rem Expand the exit code before endlocal, or the variable is discarded with the setlocal scope.
endlocal & set "CODE=%ERRORLEVEL%"
echo.
if exist "%~dp0..\work\speed-report.txt" (
    echo Report written to work\speed-report.txt
    echo The block that matters starts with "untranslated top targets".
) else (
    echo The run did not write work\speed-report.txt.
)
if not "%CODE%"=="0" echo The launcher exited with %CODE%.
pause
