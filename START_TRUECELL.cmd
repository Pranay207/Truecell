@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" set "TRUECELL_PY=.venv\Scripts\python.exe"
if not defined TRUECELL_PY for %%P in ("%LocalAppData%\Programs\Python\Python312\python.exe" "%LocalAppData%\Programs\Python\Python311\python.exe" "%LocalAppData%\Programs\Python\Python310\python.exe") do if not defined TRUECELL_PY if exist "%%~P" set "TRUECELL_PY=%%~P"
if not defined TRUECELL_PY set "TRUECELL_PY=python"
"%TRUECELL_PY%" scripts\bootstrap.py %*
if errorlevel 1 pause
endlocal
