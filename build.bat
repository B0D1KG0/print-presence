@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building PrintPresence.exe...

if not exist .venv (
    py -3 -m venv .venv || goto :nopython
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller pytest || goto :error
.venv\Scripts\python -m pytest -q || goto :error

rem A running PrintPresence.exe (e.g. hidden in the tray) locks the file in dist\
taskkill /im PrintPresence.exe /f >nul 2>&1

.venv\Scripts\pyinstaller --noconfirm --onefile --windowed ^
    --name PrintPresence ^
    --icon assets\app.ico ^
    --add-data "assets;assets" ^
    --collect-data customtkinter ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import pystray._win32 ^
    run_gui.py || goto :error

rem Optional code signing: set SIGN_CERT=path\to\cert.pfx and SIGN_PASSWORD=... (needs signtool from the Windows SDK)
if defined SIGN_CERT (
    signtool sign /f "%SIGN_CERT%" /p "%SIGN_PASSWORD%" /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\PrintPresence.exe || goto :error
)

echo.
echo Done: %CD%\dist\PrintPresence.exe
explorer dist
pause
exit /b 0

:nopython
echo Python not found. Install Python 3.11+ from python.org (tick "Add python.exe to PATH").
pause
exit /b 1

:error
echo Build failed, see the messages above.
pause
exit /b 1
