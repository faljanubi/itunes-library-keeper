@echo off
rem Builds a standalone Windows app (no Python needed to run it) into dist\iTunes Library Keeper\
cd /d "%~dp0"
if not exist .build-env (
  py -3 -m venv .build-env || python -m venv .build-env
)
rem (re)install dependencies each time, so an older build environment picks up new ones
".build-env\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller || exit /b 1
".build-env\Scripts\python.exe" -m PyInstaller --noconfirm --clean --log-level WARN ^
  --name "iTunes Library Keeper" --windowed --onedir --icon "%~dp0assets\icon.ico" ^
  --version-file "%~dp0assets\version_info.txt" ^
  --hidden-import win32timezone ^
  --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" ^
  "%~dp0iTunesLibraryKeeper.pyw"
rem Trim parts of Qt this app never uses: the software OpenGL renderer, Qt's own translations
rem (the app is English and uses the native Windows file dialogs) and the network TLS plugins.
set "QT=%~dp0dist\iTunes Library Keeper\_internal\PySide6"
if exist "%QT%\opengl32sw.dll" del /q "%QT%\opengl32sw.dll"
for %%d in (translations plugins\tls plugins\networkinformation) do if exist "%QT%\%%d" rmdir /s /q "%QT%\%%d"
echo.
echo Built: dist\iTunes Library Keeper\iTunes Library Keeper.exe
pause
