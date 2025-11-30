@echo off
echo ========================================
echo Cleanup Build Files
echo ========================================
echo.
echo Dit script verwijdert oude build artifacts:
echo - build\ directory (hele directory)
echo - build_artifacts\*.spec (behalve de nieuwste 5)
echo - build_artifacts\ADJEHOUSE_v* folders (oude versies)
echo - __pycache__ folders
echo.
pause

REM Verwijder hele build directory
echo.
echo Verwijderen van build\ directory...
if exist "build" (
    rd /s /q "build" 2>nul
    if errorlevel 1 (
        echo Warning: Kon build directory niet volledig verwijderen (mogelijk in gebruik)
    ) else (
        echo build\ directory verwijderd.
    )
) else (
    echo build\ directory bestaat niet.
)

REM Verwijder oude .spec files (behoud nieuwste 5)
echo.
echo Verwijderen van oude .spec files (behoud nieuwste 5)...
setlocal enabledelayedexpansion
set count=0
for /f "tokens=*" %%f in ('dir /b /o-d build_artifacts\*.spec 2^>nul') do (
    set /a count+=1
    if !count! leq 5 (
        echo Behouden: %%f
    ) else (
        echo Verwijderen: %%f
        del "build_artifacts\%%f" 2>nul
    )
)
endlocal

REM Verwijder oude build_artifacts subdirectories (behoud nieuwste 5)
echo.
echo Verwijderen van oude build_artifacts\ADJEHOUSE_v* folders (behoud nieuwste 5)...
setlocal enabledelayedexpansion
set count=0
for /f "tokens=*" %%d in ('dir /b /o-d /ad build_artifacts\ADJEHOUSE_v* 2^>nul') do (
    set /a count+=1
    if !count! leq 5 (
        echo Behouden: %%d
    ) else (
        echo Verwijderen: %%d
        rd /s /q "build_artifacts\%%d" 2>nul
    )
)
endlocal

REM Verwijder __pycache__ folders
echo.
echo Verwijderen van __pycache__ folders...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" (
        echo Verwijderen: %%d
        rd /s /q "%%d" 2>nul
    )
)

echo.
echo Cleanup voltooid!
pause

