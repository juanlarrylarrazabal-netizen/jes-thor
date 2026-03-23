@echo off
chcp 65001 > nul
title Generador de Licencias JAMF V12
cd /d "%~dp0\.."
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python licencias/generador_licencias.py
) else (
    python licencias/generador_licencias.py
)
pause
