@echo off
chcp 65001 >nul
title Instalador JES⚡THOR V1
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║        JES⚡THOR V1 V15 — INSTALADOR          ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Descarga Python 3.10+ desde https://python.org
    pause & exit /b 1
)
echo [OK] Python encontrado

:: Crear entorno virtual
if not exist "venv" (
    echo [1/8] Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 ( echo [ERROR] No se pudo crear venv & pause & exit /b 1 )
)
echo [OK] Entorno virtual listo

:: Activar entorno
call venv\Scripts\activate.bat

:: Actualizar pip
echo [2/8] Actualizando pip...
python -m pip install --upgrade pip --quiet

:: Instalar dependencias
echo [3/8] Instalando PyQt5...
pip install PyQt5>=5.15.9 --quiet
echo [4/8] Instalando PyMuPDF (fitz)...
pip install PyMuPDF>=1.23.0 --quiet
echo [5/8] Instalando OCR y imagen...
pip install pytesseract>=0.3.10 Pillow>=10.0.0 pdf2image>=1.16.0 numpy>=1.24.0 --quiet
echo [6/8] Instalando Excel y datos...
pip install openpyxl>=3.1.0 pandas>=2.0.0 matplotlib>=3.7.0 --quiet
echo [7/8] Instalando criptografia y utilidades...
pip install cryptography>=41.0.0 pypdf>=3.0.0 reportlab>=4.0.0 qrcode>=7.4.0 --quiet
pip install PyYAML>=6.0.0 python-dateutil>=2.8.2 --quiet
echo [8/8] Instalando IA (Gemini)...
pip install google-generativeai>=0.7.0 --quiet

:: Verificar instalaciones críticas
echo.
echo [VERIFICACION] Comprobando modulos criticos...
python -c "import PyQt5; print('[OK] PyQt5')" 2>nul || echo "[WARN] PyQt5 no disponible"
python -c "import fitz; print('[OK] PyMuPDF')" 2>nul || echo "[WARN] PyMuPDF no disponible"
python -c "import pytesseract; print('[OK] pytesseract')" 2>nul || echo "[WARN] pytesseract no disponible"
python -c "import openpyxl; print('[OK] openpyxl')" 2>nul || echo "[WARN] openpyxl no disponible"
python -c "import cryptography; print('[OK] cryptography')" 2>nul || echo "[WARN] cryptography no disponible"
python -c "import matplotlib; print('[OK] matplotlib')" 2>nul || echo "[WARN] matplotlib — instalando..." && pip install matplotlib --quiet
python -c "import google.generativeai; print('[OK] Gemini AI')" 2>nul || echo "[INFO] google-generativeai no instalado (opcional)"

:: Crear lanzadores
echo.
echo [INFO] Creando lanzador INICIAR.bat...
echo @echo off > INICIAR.bat
echo call venv\Scripts\activate.bat >> INICIAR.bat
echo python GESTOR_PRO.pyw >> INICIAR.bat
echo pause >> INICIAR.bat

:: Tesseract warning
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║  IMPORTANTE: Para OCR en escaneos instala Tesseract OCR:   ║
echo ║  https://github.com/UB-Mannheim/tesseract/wiki             ║
echo ║  (incluye paquete de idioma español: spa.traineddata)      ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo ✅ Instalacion completada. Ejecuta INICIAR.bat para arrancar.
echo.
pause
