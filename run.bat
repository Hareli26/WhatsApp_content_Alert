@echo off
REM Launch with pythonw.exe so no console/CMD window appears
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "%~dp0app.py"
) else (
    REM Fallback: python with hidden window flag
    start "" /B python "%~dp0app.py"
)
