@echo off
setlocal enabledelayedexpansion
REM ADJEHOUSE Build Script for Windows
REM Builds the ADJEHOUSE application into a standalone .exe file with version numbers

REM Change to ADJEHOUSE directory
cd /d "%~dp0"

echo ========================================
echo ADJEHOUSE Build Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

REM Install PyInstaller if not already installed
echo Installing PyInstaller and required libraries...
pip install pyinstaller twilio psutil
echo.

REM Create build directories
echo Creating build directories...
if not exist "build_artifacts" mkdir build_artifacts
if not exist "dist" mkdir dist
echo.

REM Find the next version number
echo Finding next version number...
for /f %%i in ('python get_next_version.py') do set NEXT_VERSION=%%i
echo Next version: %NEXT_VERSION%

REM Update VERSION in adjehouse_main.py (version.txt is no longer used)
echo Updating VERSION in adjehouse_main.py...
python update_version_in_main.py %NEXT_VERSION%

set EXE_NAME=ADJEHOUSE_v%NEXT_VERSION%
echo Building %EXE_NAME%.exe...
echo.

REM Clean up root directory spec files
if exist "*.spec" move "*.spec" "build_artifacts\" >nul 2>&1

REM Build with settings and scrapers folders included
REM Output spec and work files to build_artifacts directory
REM Use absolute paths for data to avoid confusion with spec file location
pyinstaller --onefile ^
    --name "%EXE_NAME%" ^
    --specpath "build_artifacts" ^
    --workpath "build_artifacts" ^
    --distpath "dist" ^
    --console ^
    --add-data "%~dp0scrapers;scrapers" ^
    --add-data "%~dp0signups;signups" ^
    --add-data "%~dp0monitors;monitors" ^
    --hidden-import=selenium ^
    --hidden-import=requests ^
    --hidden-import=imaplib ^
    --hidden-import=email ^
    --hidden-import=json ^
    --hidden-import=html ^
    --hidden-import=html.parser ^
    --hidden-import=twilio ^
    --hidden-import=twilio.rest ^
    --hidden-import=dolphin_base ^
    --hidden-import=capsolver_helper ^
    --hidden-import=lxml ^
    --hidden-import=lxml.html ^
    --hidden-import=lxml.etree ^
    --hidden-import=lxml._elementpath ^
    --hidden-import=discord ^
    --hidden-import=discord.client ^
    --hidden-import=discord.intents ^
    adjehouse_main.py

REM Clean up build directory (PyInstaller maakt dit altijd aan, ook al gebruiken we build_artifacts)
if exist "build" (
    echo.
    echo Cleaning up build directory...
    rd /s /q "build" 2>nul
    if errorlevel 1 (
        echo Warning: Could not fully remove build directory (some files may be in use)
    ) else (
        echo Build directory cleaned up successfully.
    )
)

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo The executable can be found in: dist\%EXE_NAME%.exe
echo.

REM Auto-push to GitHub
echo.
echo ========================================
echo Auto-Push to GitHub
echo ========================================
echo.

REM Find Git executable by searching the system
echo Searching for Git installation...
set GIT_CMD=
set GIT_DIR=
REM First try: check if git is in PATH
git --version >nul 2>&1
if not errorlevel 1 (
    set GIT_CMD=git
    echo Found Git in PATH
) else (
    REM Second try: use where.exe to find git
    for /f "tokens=* delims= " %%i in ('where.exe git 2^>nul') do (
        set "GIT_CMD=%%i"
        echo Found Git at: %%i
        goto :git_found
    )
    
    REM Third try: search common installation locations
    if exist "C:\Program Files\Git\cmd\git.exe" (
        set "GIT_CMD=C:\Program Files\Git\cmd\git.exe"
        set "GIT_DIR=C:\Program Files\Git\cmd"
        echo Found Git at: "C:\Program Files\Git\cmd\git.exe"
    ) else if exist "C:\Program Files (x86)\Git\cmd\git.exe" (
        set "GIT_CMD=C:\Program Files (x86)\Git\cmd\git.exe"
        set "GIT_DIR=C:\Program Files (x86)\Git\cmd"
        echo Found Git at: "C:\Program Files (x86)\Git\cmd\git.exe"
    ) else (
        REM Fourth try: search all Program Files directories
        for /d %%d in ("C:\Program Files\*") do (
            if exist "%%d\Git\cmd\git.exe" (
                set "GIT_CMD=%%d\Git\cmd\git.exe"
                set "GIT_DIR=%%d\Git\cmd"
                echo Found Git at: "%%d\Git\cmd\git.exe"
                goto :git_found
            )
        )
        for /d %%d in ("C:\Program Files (x86)\*") do (
            if exist "%%d\Git\cmd\git.exe" (
                set "GIT_CMD=%%d\Git\cmd\git.exe"
                set "GIT_DIR=%%d\Git\cmd"
                echo Found Git at: "%%d\Git\cmd\git.exe"
                goto :git_found
            )
        )
        
        REM Fifth try: use PowerShell to find Git
        for /f "tokens=* delims= " %%i in ('powershell -NoProfile -Command "try { (Get-Command git -ErrorAction Stop).Source.Trim() } catch { }" 2^>nul') do (
            set "GIT_PATH=%%i"
            if "!GIT_PATH!" neq "" if exist "!GIT_PATH!" (
                set "GIT_CMD=!GIT_PATH!"
                for %%p in ("!GIT_PATH!") do set "GIT_DIR=%%~dp"
                echo Found Git via PowerShell at: !GIT_PATH!
                goto :git_found
            )
        )
        
        echo WARNING: Git is not installed or not found
        echo Searched in:
        echo   - PATH
        echo   - where.exe command
        echo   - C:\Program Files\Git\cmd\git.exe
        echo   - C:\Program Files (x86)\Git\cmd\git.exe
        echo   - All Program Files directories
        echo   - PowerShell Get-Command
        echo.
        echo To install Git, download from: https://git-scm.com/download/win
        echo Or install via: winget install Git.Git
        echo Skipping auto-push to GitHub...
        echo.
        pause
        exit /b 0
    )
)

:git_found
REM If Git directory was found, add it to PATH for this session
if defined GIT_DIR (
    echo Adding Git to PATH for this session...
    set "PATH=!GIT_DIR!;%PATH%"
    set "GIT_CMD=git"
)

REM Verify Git works with the found command
if "%GIT_CMD%"=="" (
    echo WARNING: Git command path is empty
    echo Skipping auto-push to GitHub...
    echo.
    pause
    exit /b 0
)

"%GIT_CMD%" --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Git command failed
    echo Skipping auto-push to GitHub...
    echo.
    pause
    exit /b 0
)

REM Check if we're in a Git repository
"%GIT_CMD%" rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo WARNING: Not in a Git repository
    echo Skipping auto-push to GitHub...
    echo.
    pause
    exit /b 0
)

REM Copy executable to adjehouse.exe for GitHub
echo Copying executable to adjehouse.exe...
copy /y "dist\%EXE_NAME%.exe" "adjehouse.exe" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not copy executable to adjehouse.exe
    echo Skipping auto-push to GitHub...
    echo.
    pause
    exit /b 0
)

REM Stage files for commit
echo Staging files for commit...
"%GIT_CMD%" add adjehouse.exe update_checker.py build_adjehouse.bat .gitignore UPDATE_SYSTEM_README.md adjehouse_main.py update_version_in_main.py >nul 2>&1

REM Check if there are changes to commit
"%GIT_CMD%" diff --cached --quiet
if errorlevel 1 (
    echo Committing changes...
    "%GIT_CMD%" commit -m "Auto-update: Build %NEXT_VERSION%" >nul 2>&1
    
    if errorlevel 1 (
        echo WARNING: Git commit failed
        echo You may need to configure Git user.name and user.email
        echo Skipping push to GitHub...
        echo.
        pause
        exit /b 0
    )
    
    echo Pushing to GitHub...
    "%GIT_CMD%" push origin main >nul 2>&1
    if errorlevel 1 (
        REM Try master branch if main fails
        "%GIT_CMD%" push origin master >nul 2>&1
        if errorlevel 1 (
            echo WARNING: Git push failed
            echo You may need to set up remote or authenticate
            echo Changes are committed locally but not pushed
            echo.
        ) else (
            echo Successfully pushed to GitHub (master branch)!
        )
    ) else (
        echo Successfully pushed to GitHub (main branch)!
    )
) else (
    echo No changes to commit (files already up to date)
)

echo.
echo ========================================
echo Build and Push Complete!
echo ========================================
echo.
echo The executable can be found in: dist\%EXE_NAME%.exe
echo.
echo To run the application, double-click dist\%EXE_NAME%.exe
echo.
pause

