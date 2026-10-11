@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Building Print Presence...

if not exist .venv (
    py -3 -m venv .venv || goto :nopython
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller pytest || goto :error
.venv\Scripts\python -m pytest -q || goto :error

for /f %%v in ('.venv\Scripts\python -c "import print_presence; print(print_presence.__version__)"') do set VERSION=%%v
echo Version %VERSION%

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

rem ---- Portable: exe + portable.txt in a zip --------------------------------
echo Packing the portable version...
if exist dist\portable rmdir /s /q dist\portable
mkdir dist\portable\PrintPresence
copy /y dist\PrintPresence.exe dist\portable\PrintPresence\ >nul || goto :error
copy /y installer\portable.txt dist\portable\PrintPresence\ >nul || goto :error
copy /y LICENSE dist\portable\PrintPresence\LICENSE.txt >nul || goto :error
copy /y THIRD-PARTY-NOTICES.md dist\portable\PrintPresence\THIRD-PARTY-NOTICES.txt >nul || goto :error
powershell -NoProfile -Command "Compress-Archive -Path 'dist\portable\PrintPresence' -DestinationPath 'dist\PrintPresence-Portable.zip' -Force" || goto :error
rmdir /s /q dist\portable

rem ---- Installer: needs Inno Setup 6 ----------------------------------------
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo.
    echo Inno Setup 6 is not installed, so PrintPresence-Setup.exe was skipped.
    echo Install it once with:  winget install JRSoftware.InnoSetup
    goto :done
)
echo Building the installer...
rem Antivirus (e.g. Windows Defender) may briefly lock the new Setup.exe while Inno Setup
rem writes its icon ("EndUpdateResource failed"); a retry a few seconds later usually works.
set TRIES=0
:iscc
"%ISCC%" /Q /DAppVersion=%VERSION% installer\PrintPresence.iss && goto :iscc_ok
set /a TRIES+=1
if %TRIES% geq 3 goto :iscc_failed
echo Retrying in 5 seconds (%TRIES%/3)...
timeout /t 5 /nobreak >nul
goto :iscc
:iscc_failed
echo.
echo The installer could not be written, most likely because of the antivirus.
echo Add this folder to the Windows Security exclusions and run build.bat again:
echo   %CD%\dist
goto :error
:iscc_ok
if defined SIGN_CERT (
    signtool sign /f "%SIGN_CERT%" /p "%SIGN_PASSWORD%" /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\PrintPresence-Setup.exe || goto :error
)

:done
echo.
echo Done:
if exist dist\PrintPresence-Setup.exe echo   dist\PrintPresence-Setup.exe     - installer
echo   dist\PrintPresence-Portable.zip  - portable version
echo   dist\PrintPresence.exe           - single file
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
