@echo off
rem Wrapper so the import script runs regardless of the PowerShell execution policy.
rem Usage: tools\import-disc.bat "D:\dumps\draconus.gdi" [--whatif]
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0import-disc.ps1" %*
exit /b %errorlevel%
