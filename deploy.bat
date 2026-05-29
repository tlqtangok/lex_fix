@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================================
echo  Wubi .lex Editor  --  Deploy Builder
echo ============================================================

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SCRIPT=%ROOT%\lex_editor.py"
set "DIST=%ROOT%\dist"
set "BUILD=%ROOT%\build"
set "OUT=%ROOT%\release"

:: ── 1. Check Python ──────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] %%v

:: ── 2. Ensure PyInstaller ────────────────────────────────────
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        pause & exit /b 1
    )
)
echo [OK] PyInstaller ready

:: ── 3. Clean previous build ──────────────────────────────────
if exist "%DIST%" rd /s /q "%DIST%"
if exist "%BUILD%" rd /s /q "%BUILD%"
if exist "%ROOT%lex_editor.spec" del /q "%ROOT%lex_editor.spec"

:: ── 4. Build single-file exe ─────────────────────────────────
echo [BUILD] Running PyInstaller...
python -m PyInstaller --onefile --windowed --name "lex_editor" --distpath "%DIST%" --workpath "%BUILD%" --specpath "%ROOT%" "%SCRIPT%"

if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    pause & exit /b 1
)
echo [OK] Built: %DIST%\lex_editor.exe

:: ── 5. Create release folder ─────────────────────────────────
if not exist "%OUT%" mkdir "%OUT%"

:: ── 6. Try Inno Setup installer, else zip ────────────────────

:: Locate ISCC.exe (Inno Setup compiler)
set "ISCC="
for %%p in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    "C:\Program Files\Inno Setup 5\ISCC.exe"
) do (
    if exist %%p set "ISCC=%%~p"
)

if defined ISCC (
    echo [INFO] Inno Setup found: %ISCC%
    call :build_installer
) else (
    echo [INFO] Inno Setup not found -- creating zip instead.
    call :build_zip
)

echo.
echo ============================================================
echo  Done!  Output in: %OUT%
echo ============================================================
pause
exit /b 0


:: ── SUB: build Inno Setup installer ─────────────────────────
:build_installer
set "ISS=%ROOT%installer.iss"
(
echo [Setup]
echo AppName=Wubi Lex Editor
echo AppVersion=1.0
echo DefaultDirName={autopf}\WubiLexEditor
echo DefaultGroupName=Wubi Lex Editor
echo OutputDir=%OUT%
echo OutputBaseFilename=WubiLexEditor_Setup
echo Compression=lzma2
echo SolidCompression=yes
echo WizardStyle=modern
echo.
echo [Files]
echo Source: "%DIST%\lex_editor.exe"; DestDir: "{app}"; Flags: ignoreversion
echo.
echo [Icons]
echo Name: "{group}\Wubi Lex Editor"; Filename: "{app}\lex_editor.exe"
echo Name: "{commondesktop}\Wubi Lex Editor"; Filename: "{app}\lex_editor.exe"; Tasks: desktopicon
echo.
echo [Tasks]
echo Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
echo.
echo [Run]
echo Filename: "{app}\lex_editor.exe"; Description: "Launch Wubi Lex Editor"; Flags: nowait postinstall skipifsilent
) > "%ISS%"

echo [BUILD] Compiling installer...
"%ISCC%" "%ISS%" /Q
if errorlevel 1 (
    echo [WARN] Inno Setup compile failed, falling back to zip.
    call :build_zip
) else (
    echo [OK] Installer: %OUT%\WubiLexEditor_Setup.exe
    del /q "%ISS%"
)
goto :eof


:: ── SUB: zip the exe ────────────────────────────────────────
:build_zip
set "ZIPOUT=%OUT%\WubiLexEditor.zip"
if exist "%ZIPOUT%" del /q "%ZIPOUT%"
powershell -NoProfile -Command ^
  "Compress-Archive -Path '%DIST%\lex_editor.exe' -DestinationPath '%ZIPOUT%' -Force"
if errorlevel 1 (
    echo [WARN] Zip failed. Copying exe directly.
    copy /y "%DIST%\lex_editor.exe" "%OUT%\lex_editor.exe" >nul
    echo [OK] Copied: %OUT%\lex_editor.exe
) else (
    echo [OK] Zip: %ZIPOUT%
)
goto :eof
