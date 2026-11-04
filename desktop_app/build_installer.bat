@echo off
setlocal enabledelayedexpansion

echo ========================================
echo Building ICTA Access Control Installer
echo ========================================

:: Check if we're in the right directory
if not exist "main.spec" (
    echo Error: main.spec not found!
    echo Please run this script from the desktop_app directory.
    pause
    exit /b 1
)

echo.
echo Current directory: %CD%
echo Spec file: main.spec

:: Clean previous builds with force
echo.
echo Step 1: Cleaning previous builds...

:: Kill any running instances
taskkill /f /im ICTA_Access_Control.exe 2>nul
taskkill /f /im python.exe 2>nul

:: Wait for processes
timeout /t 2 /nobreak >nul

:: Remove dist folder
if exist "dist" (
    echo Removing dist folder...
    rmdir /s /q "dist" 2>nul
    if exist "dist" (
        echo Normal removal failed, trying force removal...
        takeown /f "dist" /r /d y >nul 2>&1
        icacls "dist" /reset /t /q >nul 2>&1
        rmdir /s /q "dist" 2>nul
        if exist "dist" (
            powershell -Command "Remove-Item -Path 'dist' -Recurse -Force -ErrorAction SilentlyContinue" 2>nul
        )
        if exist "dist" (
            echo WARNING: Could not fully remove dist folder.
            echo Some files may still be in use.
        )
    )
)

:: Remove build folder
if exist "build" (
    echo Removing build folder...
    rmdir /s /q "build" 2>nul
    if exist "build" (
        echo Normal removal failed, trying force removal...
        takeown /f "build" /r /d y >nul 2>&1
        icacls "build" /reset /t /q >nul 2>&1
        rmdir /s /q "build" 2>nul
        if exist "build" (
            powershell -Command "Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue" 2>nul
        )
    )
)

:: Remove installer folder
if exist "installer" (
    echo Removing installer folder...
    rmdir /s /q "installer" 2>nul
    if exist "installer" (
        powershell -Command "Remove-Item -Path 'installer' -Recurse -Force -ErrorAction SilentlyContinue" 2>nul
    )
)

:: Check if Python is available
echo.
echo Step 2: Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found! Please install Python and add it to PATH.
    pause
    exit /b 1
)
python --version

:: Check if PyInstaller is installed
echo.
echo Step 3: Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found! Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller!
        pause
        exit /b 1
    )
)
pyinstaller --version

:: Run PyInstaller
echo.
echo Step 4: Running PyInstaller...
echo This may take a few minutes...

python -m PyInstaller main.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo PyInstaller failed! Check the error messages above.
    echo.
    echo Common issues:
    echo 1. Missing imports - check hiddenimports in spec file
    echo 2. File permission issues - run force_cleanup.bat first
    echo 3. Out of memory - try closing other applications
    pause
    exit /b 1
)

:: Check if executable was created
if not exist "dist\ICTA_Access_Control\ICTA_Access_Control.exe" (
    echo.
    echo Error: Executable not found!
    echo Expected: dist\ICTA_Access_Control\ICTA_Access_Control.exe
    echo.
    echo Checking dist folder contents:
    if exist "dist" (
        dir dist /s /b
    ) else (
        echo dist folder does not exist!
    )
    pause
    exit /b 1
)

echo.
echo Executable created: dist\ICTA_Access_Control\ICTA_Access_Control.exe
for %%A in ("dist\ICTA_Access_Control\ICTA_Access_Control.exe") do echo Size: %%~zA bytes

:: Check for Inno Setup
echo.
echo Step 5: Creating installer with Inno Setup...

set "INNO_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "INNO_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    echo Found Inno Setup 6 at: !INNO_PATH!
) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set "INNO_PATH=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    echo Found Inno Setup 5 at: !INNO_PATH!
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "INNO_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
    echo Found Inno Setup 6 at: !INNO_PATH!
) else if exist "C:\Program Files\Inno Setup 5\ISCC.exe" (
    set "INNO_PATH=C:\Program Files\Inno Setup 5\ISCC.exe"
    echo Found Inno Setup 5 at: !INNO_PATH!
)

if not "!INNO_PATH!"=="" (
    :: Check if setup.iss exists
    if not exist "setup.iss" (
        echo.
        echo Error: setup.iss not found!
        echo Please create setup.iss in the current directory.
        pause
        exit /b 1
    )
    
    echo.
    echo Running Inno Setup...
    "!INNO_PATH!" setup.iss
    
    if errorlevel 1 (
        echo.
        echo Inno Setup failed! Check the error messages above.
        echo The executable is still available in: dist\ICTA_Access_Control\
        pause
        exit /b 1
    )
    
    if exist "installer\ICTA_Access_Control_Setup_v1.2.0.exe" (
        echo.
        echo ========================================
        echo Build complete!
        echo ========================================
        echo Installer: installer\ICTA_Access_Control_Setup_v1.2.0.exe
        for %%A in ("installer\ICTA_Access_Control_Setup_v1.2.0.exe") do echo Size: %%~zA bytes
        echo ========================================
    ) else (
        echo.
        echo Installer created but not found at expected location.
        echo Please check the installer folder.
    )
) else (
    echo.
    echo ========================================
    echo Build complete - Installer skipped!
    echo ========================================
    echo Inno Setup not found!
    echo The executable is available in: dist\ICTA_Access_Control\
    echo.
    echo To create an installer:
    echo 1. Download Inno Setup from: https://jrsoftware.org/isinfo.php
    echo 2. Install Inno Setup
    echo 3. Run: ISCC.exe setup.iss
    echo ========================================
)

echo.
pause