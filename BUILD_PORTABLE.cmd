@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Truecell's project environment is missing.
  echo Run START_TRUECELL.cmd once, then run BUILD_PORTABLE.cmd again.
  pause
  exit /b 2
)

".venv\Scripts\python.exe" scripts\build_portable.py %*
if errorlevel 1 pause
endlocal
