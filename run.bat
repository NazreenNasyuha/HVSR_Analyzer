@echo off
rem HVSR Analyzer launcher (pure Python standard library - no pip installs needed)
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0src\main.py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python "%~dp0src\main.py"
    ) else (
        echo Python was not found on this system.
        echo Install Python 3.8+ from https://www.python.org/downloads/
        pause
    )
)
