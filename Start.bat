@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python universal_downloader.py
pause