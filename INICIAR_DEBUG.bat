@echo off
chcp 65001 > nul 2>&1
cd /d "%~dp0"
echo ============================================================
echo  JES⚡THOR V1 — MODO DEBUG
echo ============================================================
echo.

set GESTOR_DEBUG=1
set QT_FATAL_WARNINGS=0
set QT_DEBUG_PLUGINS=1
set PYTHONFAULTHANDLER=1

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo Iniciando con debug activo...
echo Logs en: %LOCALAPPDATA%\GestorPro\logs\
echo.

python GESTOR_PRO.pyw 2>&1
echo.
echo --- Presiona cualquier tecla para cerrar ---
pause > nul
