@echo off
REM Build and Package Script for Cooksy
REM Creates both PyInstaller executable and NSIS installer

setlocal enabledelayedexpansion

echo.
echo ========================================
echo Cooksy Build and Package Script
echo ========================================
echo.

REM Step 1: Check if PyInstaller build exists
if exist "dist\Cooksy\Cooksy.exe" (
    echo [OK] PyInstaller build found
) else (
    echo [ERROR] PyInstaller build not found in dist\Cooksy
    echo Please run: python -m PyInstaller Cooksy.spec --distpath dist --workpath build
    pause
    exit /b 1
)

REM Step 2: Check if NSIS is installed
echo.
echo Checking for NSIS installation...
if exist "C:\Program Files (x86)\NSIS\makensis.exe" (
    set NSIS_PATH=C:\Program Files (x86)\NSIS\makensis.exe
    echo [OK] NSIS found at !NSIS_PATH!
) else if exist "C:\Program Files\NSIS\makensis.exe" (
    set NSIS_PATH=C:\Program Files\NSIS\makensis.exe
    echo [OK] NSIS found at !NSIS_PATH!
) else (
    echo [ERROR] NSIS not found. Please install NSIS from https://nsis.sourceforge.io/
    pause
    exit /b 1
)

REM Step 3: Create output directory
if not exist "releases" mkdir releases

REM Step 4: Build NSIS installer
echo.
echo Building NSIS installer...
"!NSIS_PATH!" "Cooksy-Installer.nsi"

if !errorlevel! equ 0 (
    echo.
    echo [SUCCESS] Installer created: Cooksy-1.0.0-Setup.exe
    if exist "Cooksy-1.0.0-Setup.exe" (
        move "Cooksy-1.0.0-Setup.exe" "releases\"
        echo [OK] Installer moved to releases\ folder
    )
) else (
    echo [ERROR] NSIS compilation failed with error code !errorlevel!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Your installer is ready at:
echo   releases\Cooksy-1.0.0-Setup.exe
echo.
pause
