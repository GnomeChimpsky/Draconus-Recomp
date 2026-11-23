@echo off
rem Capture what the game asks the pad to do, for a haptics report.
rem
rem Double-click it and choose a run. From a terminal, the modes can also be named:
rem
rem   tools\haptics-trace.bat             HD rumble, trigger feedback and resistance
rem   tools\haptics-trace.bat triggers    trigger feedback only; the pad's audio path stays closed
rem   tools\haptics-trace.bat off         A/B: RenHDrum disabled, the game's rumble plays through SDL
rem   tools\haptics-trace.bat modern      HD rumble with the Modern control layout
rem
rem Every line the engine prints goes to a log beside this file (haptics-trace.log, and one file per
rem other mode): the game's own rumble calls, what the haptics path makes of each, every trigger effect
rem it sends, the input the guest receives, and which audio device the game played through.
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."
set "MODE="
set "GAME_ARGS=%*"
set "FLAGS=--haptics --trigger-feedback --trigger-resistance"

if /i "%~1"=="off" (
    set "MODE=off"
    if "%~2"=="" (set "GAME_ARGS=") else (set "GAME_ARGS=!GAME_ARGS:*off =!")
)
if /i "%~1"=="triggers" (
    set "MODE=triggers"
    rem No --haptics: the pad's 4-channel audio endpoint is never opened, so only the triggers move.
    set "FLAGS=--trigger-feedback"
    if "%~2"=="" (set "GAME_ARGS=") else (set "GAME_ARGS=!GAME_ARGS:*triggers =!")
)
if /i "%~1"=="modern" (
    set "MODE=modern"
    if "%~2"=="" (set "GAME_ARGS=") else (set "GAME_ARGS=!GAME_ARGS:*modern =!")
)
if "%~1"=="" (
    cls
    echo Draconus haptics trace
    echo.
    echo    1   HD rumble, trigger feedback and resistance        ^(default^)
    echo    2   Trigger feedback only, no resistance ^(no audio path either^)
    echo    3   A/B: RenHDrum disabled ^(the game's rumble through SDL^)
    echo    4   Modern controls, HD rumble and triggers
    echo.
    set "PICK="
    set /p "PICK=Choose 1-4, then press Enter [1]: "
    if not defined PICK set "PICK=1"
    if "!PICK!"=="2" set "MODE=triggers"
    if "!PICK!"=="3" set "MODE=off"
    if "!PICK!"=="4" set "MODE=modern"
)
if "%MODE%"=="triggers" set "FLAGS=--trigger-feedback"
if "%MODE%"=="modern" set "GAME_ARGS=--controls modern !GAME_ARGS!"

rem Each mode keeps its own file, so the runs can be compared side by side.
set "LOG=%~dp0haptics-trace.log"
if "%MODE%"=="off" set "LOG=%~dp0haptics-trace-off.log"
if "%MODE%"=="triggers" set "LOG=%~dp0haptics-trace-triggers.log"
if "%MODE%"=="modern" set "LOG=%~dp0haptics-trace-modern.log"

rem --- the build to run: a source tree first, then the release folder -------------------------
set "EXE="
set "CFG="
if exist "%ROOT%\engine\build-render\games\draconus\draconus_boot.exe" (
    set "EXE=%ROOT%\engine\build-render\games\draconus\draconus_boot.exe"
    set "CFG=%ROOT%\engine\games\draconus\draconus.toml"
) else if exist "%ROOT%\engine\build-haptics\games\draconus\draconus_boot.exe" (
    set "EXE=%ROOT%\engine\build-haptics\games\draconus\draconus_boot.exe"
    set "CFG=%ROOT%\engine\games\draconus\draconus.toml"
) else if exist "%ROOT%\work\release\DraconusRecomp.exe" (
    set "EXE=%ROOT%\work\release\DraconusRecomp.exe"
    set "CFG=%ROOT%\work\release\draconus.toml"
)
if not defined EXE (
    echo No build found. Expected one of:
    echo   engine\build-haptics\games\draconus\draconus_boot.exe
    echo   engine\build-render\games\draconus\draconus_boot.exe
    echo   work\release\DraconusRecomp.exe
    echo Build it first with:  cmake --build engine\build-haptics --target draconus_boot
    pause
    exit /b 2
)
for %%I in ("%EXE%") do set "EXEDIR=%%~dpI"

rem The game loads both DLLs from beside its own executable.
if not exist "%EXEDIR%SDL3.dll" if exist "%ROOT%\work\sdl3\bin\SDL3.dll" (
    copy /y "%ROOT%\work\sdl3\bin\SDL3.dll" "%EXEDIR%SDL3.dll" >nul
)
if not exist "%EXEDIR%renhdrum.dll" if exist "%ROOT%\third_party\renhdrum\renhdrum.dll" (
    copy /y "%ROOT%\third_party\renhdrum\renhdrum.dll" "%EXEDIR%renhdrum.dll" >nul
)

rem --- the trace -------------------------------------------------------------------------------
set "DREAM_RUMBLE_TRACE=1"
set "DREAM_RENHDRUM_TRACE=1"
set "DREAM_INPUT_TRACE=1"
if "%MODE%"=="off" (set "DREAM_RENHDRUM=0") else (set "DREAM_RENHDRUM=")

echo === draconus haptics trace === > "%LOG%"
echo running: %EXE% >> "%LOG%"
for %%F in ("%EXE%") do echo built:   %%~tF >> "%LOG%"
if "%MODE%"=="off" echo RenHDrum disabled: the game's rumble is played by SDL, for comparison. >> "%LOG%"
if "%MODE%"=="triggers" echo Trigger feedback only: the pad's audio endpoint is not opened. >> "%LOG%"
if "%MODE%"=="modern" echo Modern controls. >> "%LOG%"

echo.
echo running: %EXE%
if "%MODE%"=="off" (
    echo mode: A/B, RenHDrum disabled
) else if "%MODE%"=="triggers" (
    echo mode: trigger feedback only, no HD rumble
) else if "%MODE%"=="modern" (
    echo mode: Modern controls, HD rumble and triggers
) else (
    echo mode: HD rumble, trigger feedback and resistance
)
echo.
echo Tap the directions that click, a few times each, then close the game window.
echo The trace is written to: %LOG%
echo.

"%EXE%" --config "%CFG%" --window %FLAGS% %GAME_ARGS% >> "%LOG%" 2>&1

echo.
echo --- trace summary ---------------------------------------------------------------
findstr /C:"running:" /C:"built:" /C:"haptics:" /C:"renhdrum:" /C:"rumble:" /C:"audio: playing" "%LOG%"
echo ---------------------------------------------------------------------------------
echo Full log: %LOG%
echo Send that file, or just the lines above.
pause
exit /b 0
