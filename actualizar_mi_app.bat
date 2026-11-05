@echo off
cd /d "%~dp0"
echo ========================================================
echo  Compilando y Actualizando tu aplicacion GameFlow
echo ========================================================
call venv\Scripts\activate
python scripts\sync_to_player.py
pause
