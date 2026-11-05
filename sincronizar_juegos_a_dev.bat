@echo off
cd /d "%~dp0"
echo ========================================================
echo  Sincronizando biblioteca de juegos hacia Desarrollo
echo ========================================================
call venv\Scripts\activate
python scripts\sync_from_player.py
pause
