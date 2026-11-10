@echo off
cd /d "%~dp0"
echo ========================================================
echo  Descargando ultimas mejoras de GameFlow desde GitHub...
echo ========================================================
git pull origin main
echo.
echo ========================================================
echo  Listo. Tu carpeta Lanzador esta actualizada.
echo ========================================================
pause
