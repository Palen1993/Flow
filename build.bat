@echo off
cd /d "%~dp0"
echo ==============================================
echo  Compilando GameFlow Launcher Portable (EXE)
echo ==============================================
call venv\Scripts\activate
python build.py
pause
