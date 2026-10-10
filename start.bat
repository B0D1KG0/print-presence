@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
if not exist config.toml (
    copy config.example.toml config.toml >nul
    echo Created config.toml - fill it in and run start.bat again.
    notepad config.toml
    exit /b 0
)
.venv\Scripts\python -m print_presence %*
pause
exit /b 0
:error
echo Install failed. Make sure Python 3.11+ is installed (python.org, tick "Add to PATH").
pause
