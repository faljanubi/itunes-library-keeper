@echo off
rem Builds both release versions into dist\:
rem   iTunesLibraryKeeper-<version>-portable-win64.zip  (no install; settings kept in its own data folder)
rem   iTunesLibraryKeeper-<version>-setup.exe           (installer; settings in %APPDATA%)
rem Needs Inno Setup 6.3+ for the installer:  winget install JRSoftware.InnoSetup
cd /d "%~dp0"
set "ISCC="
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe") do if exist "%%~p" set "ISCC=%%~p"
if not defined ISCC (
  echo Inno Setup 6 was not found. Install it with:  winget install JRSoftware.InnoSetup
  pause
  exit /b 1
)
call "%~dp0build.cmd" < nul || exit /b 1
cd /d "%~dp0"
for /f "delims=" %%v in ('call "%~dp0.build-env\Scripts\python.exe" -c "from toolkit.version import VERSION; print(VERSION)"') do set "VER=%%v"
if not defined VER (
  echo Could not read the version from toolkit\version.py
  exit /b 1
)

rem ---- portable: the app folder + README.txt (an exe Setup didn't install keeps its data in .\data)
set "PORT=%~dp0dist\portable"
if exist "%PORT%" rmdir /s /q "%PORT%"
xcopy /e /i /q /y "%~dp0dist\iTunes Library Keeper" "%PORT%\iTunes Library Keeper" > nul || exit /b 1
copy /y "%~dp0assets\README.txt" "%PORT%\iTunes Library Keeper\" > nul || exit /b 1
copy /y "%~dp0LICENSE" "%PORT%\iTunes Library Keeper\LICENSE.txt" > nul || exit /b 1
set "ZIP=%~dp0dist\iTunesLibraryKeeper-%VER%-portable-win64.zip"
if exist "%ZIP%" del /q "%ZIP%"
"%SystemRoot%\System32\tar.exe" -a -c -f "%ZIP%" -C "%PORT%" "iTunes Library Keeper" || exit /b 1

rem ---- installer (its uninstaller beside the .exe makes the installed app use %APPDATA%)
"%ISCC%" /Q "%~dp0installer\iTunesLibraryKeeper.iss" || exit /b 1

echo.
echo Built in dist\:
echo   iTunesLibraryKeeper-%VER%-portable-win64.zip
echo   iTunesLibraryKeeper-%VER%-setup.exe
pause
