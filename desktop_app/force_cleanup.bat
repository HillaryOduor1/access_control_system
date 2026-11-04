@echo off
echo ========================================
echo Force Cleanup - ICTA Access Control
echo ========================================

:: Kill any processes that might be using the files
echo.
echo Step 1: Killing any running instances...
taskkill /f /im ICTA_Access_Control.exe 2>nul
taskkill /f /im python.exe 2>nul
taskkill /f /im pyinstaller.exe 2>nul

:: Wait for processes to fully terminate
echo.
echo Step 2: Waiting for processes to terminate...
timeout /t 3 /nobreak >nul

:: Remove directories with multiple methods
echo.
echo Step 3: Removing build directories...

:: Method 1: Try normal removal
if exist "dist" (
    echo Attempting to remove dist...
    rmdir /s /q "dist" 2>nul
    if exist "dist" (
        echo Normal removal failed, trying force removal...
        :: Method 2: Use takeown to take ownership
        takeown /f "dist" /r /d y >nul 2>&1
        :: Method 3: Use icacls to reset permissions
        icacls "dist" /reset /t /q >nul 2>&1
        :: Method 4: Try removing with RD again
        rmdir /s /q "dist" 2>nul
        if exist "dist" (
            :: Method 5: Use PowerShell to force remove
            powershell -Command "Remove-Item -Path 'dist' -Recurse -Force -ErrorAction SilentlyContinue"
        )
    )
)

if exist "build" (
    echo Attempting to remove build...
    rmdir /s /q "build" 2>nul
    if exist "build" (
        echo Normal removal failed, trying force removal...
        takeown /f "build" /r /d y >nul 2>&1
        icacls "build" /reset /t /q >nul 2>&1
        rmdir /s /q "build" 2>nul
        if exist "build" (
            powershell -Command "Remove-Item -Path 'build' -Recurse -Force -ErrorAction SilentlyContinue"
        )
    )
)

if exist "installer" (
    echo Removing installer...
    rmdir /s /q "installer" 2>nul
    if exist "installer" (
        powershell -Command "Remove-Item -Path 'installer' -Recurse -Force -ErrorAction SilentlyContinue"
    )
)

:: Check if directories still exist
echo.
echo Step 4: Checking results...
if exist "dist" (
    echo WARNING: dist folder still exists! Please manually delete it.
    echo Path: %CD%\dist
) else (
    echo Dist folder removed successfully.
)

if exist "build" (
    echo WARNING: build folder still exists! Please manually delete it.
    echo Path: %CD%\build
) else (
    echo Build folder removed successfully.
)

if exist "installer" (
    echo WARNING: installer folder still exists!
) else (
    echo Installer folder removed successfully.
)

echo.
echo Cleanup complete!
pause