@echo off
cd /d "%~dp0"
echo ========================================================
echo  Sincronizando GameFlow (Git + Proyecto + App Personal)
echo ========================================================
call venv\Scripts\activate
python scripts\auto_update.py --verbose
echo.
pause
