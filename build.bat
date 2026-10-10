@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Сборка PrintPresence.exe...

if not exist .venv (
    py -3 -m venv .venv || goto :nopython
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller pytest || goto :error
.venv\Scripts\python -m pytest -q || goto :error

.venv\Scripts\pyinstaller --noconfirm --onefile --windowed ^
    --name PrintPresence ^
    --icon assets\app.ico ^
    --add-data "assets;assets" ^
    --collect-data customtkinter ^
    --hidden-import PIL._tkinter_finder ^
    run_gui.py || goto :error

echo.
echo Готово: %CD%\dist\PrintPresence.exe
explorer dist
pause
exit /b 0

:nopython
echo Не найден Python. Установи Python 3.11+ с python.org (галочка "Add python.exe to PATH").
pause
exit /b 1

:error
echo Ошибка сборки, смотри сообщения выше.
pause
exit /b 1
