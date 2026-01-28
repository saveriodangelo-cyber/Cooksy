@echo off
REM Build & Deploy script per Cooksy (Windows)
REM Questo script prepara l'app per il deploy su Android/iOS/Web

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  Cooksy: Build & Deploy Manager
echo ============================================================
echo.

if "%1"=="" (
    echo Usage: build-deploy.bat [command]
    echo.
    echo Commands:
    echo   setup-capacitor     - Setup Capacitor per Android/iOS
    echo   build-apk           - Build APK per Android
    echo   build-web           - Build frontend per CDN
    echo   deploy-render       - Deploy backend su Render.com
    echo   deploy-vercel       - Deploy frontend su Vercel
    echo   all                 - Esegui tutto
    echo   clean               - Pulisci build artifacts
    echo.
    exit /b 0
)

set COMMAND=%1

if "%COMMAND%"=="setup-capacitor" (
    echo [1/3] Installing Capacitor...
    call npm init -y
    call npm install -D @capacitor/core @capacitor/cli
    call npx cap init cooksy "Cooksy" --web-dir=ui/
    call npx cap add android
    echo ✅ Capacitor setup complete
    echo Next: npm run build-apk
    exit /b 0
)

if "%COMMAND%"=="build-apk" (
    echo [2/3] Building Android APK...
    call npx cap build android
    if exist "android\app\build\outputs\apk\release\app-release.apk" (
        echo ✅ APK built: android\app\build\outputs\apk\release\app-release.apk
    ) else (
        echo ❌ APK build failed
        exit /b 1
    )
    exit /b 0
)

if "%COMMAND%"=="build-web" (
    echo [3/3] Building frontend...
    mkdir dist 2>nul
    xcopy ui\* dist\ /E /I /Y
    type nul > dist\CNAME && (echo cooksy.app > dist\CNAME)
    echo ✅ Frontend ready in dist/
    echo Next: npm run deploy-vercel
    exit /b 0
)

if "%COMMAND%"=="deploy-render" (
    echo Deploying backend to Render.com...
    echo.
    echo Prerequisites:
    echo   1. Create Render account: https://render.com
    echo   2. Connect GitHub repo
    echo   3. New Web Service from render.yaml
    echo.
    echo Steps:
    echo   1. Visit https://dashboard.render.com
    echo   2. Create New → Web Service
    echo   3. Select your repo, branch main
    echo   4. Environment variables from render.yaml
    echo   5. Deploy
    echo.
    echo ✅ Deployment guide printed
    exit /b 0
)

if "%COMMAND%"=="deploy-vercel" (
    echo Deploying frontend to Vercel...
    call npm i -g vercel
    cd ui
    call vercel --prod
    cd ..
    echo ✅ Frontend deployed to Vercel
    exit /b 0
)

if "%COMMAND%"=="all" (
    call :build-apk
    call :build-web
    echo.
    echo ============================================================
    echo  ✅ Build complete!
    echo ============================================================
    echo.
    echo Next steps:
    echo   1. Test APK on Android emulator
    echo   2. Deploy backend: build-deploy.bat deploy-render
    echo   3. Deploy frontend: build-deploy.bat deploy-vercel
    echo.
    exit /b 0
)

if "%COMMAND%"=="clean" (
    echo Cleaning build artifacts...
    rmdir /s /q dist 2>nul
    rmdir /s /q android\.gradle 2>nul
    rmdir /s /q build 2>nul
    del package-lock.json 2>nul
    echo ✅ Cleaned
    exit /b 0
)

echo Unknown command: %COMMAND%
exit /b 1
