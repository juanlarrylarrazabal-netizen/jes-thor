@echo off
chcp 65001 > nul 2>&1
cd /d "%~dp0"
echo ============================================================
echo  JES⚡THOR V1 — MODO SEGURO
echo  (Sin OCR / IA / Informes pesados)
echo ============================================================
echo.

set GESTOR_SAFE_MODE=1
set GESTOR_DEBUG=1

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo Si la app arranca en modo seguro pero no en normal,
echo el problema esta en las dependencias pesadas (OCR/matplotlib/IA).
echo.

python GESTOR_PRO.pyw --safe-mode 2>&1
echo.
echo --- Presiona cualquier tecla para cerrar ---
pause > nul
