@echo off
setlocal
set "DSH_UPGRADE_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "DSH_UPGRADE_POWERSHELL=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
"%DSH_UPGRADE_POWERSHELL%" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0upgrade-win7.ps1"
set "DSH_UPGRADE_EXIT=%ERRORLEVEL%"
echo.
echo Exit code: %DSH_UPGRADE_EXIT%. See the guide and the log path above.
pause
exit /b %DSH_UPGRADE_EXIT%
