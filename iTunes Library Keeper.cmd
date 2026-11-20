@echo off
rem Launches iTunes Library Keeper (no console window). First run: run setup.cmd once.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0iTunesLibraryKeeper.pyw" %*
