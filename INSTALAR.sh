#!/usr/bin/env bash
# Instalador Gestor Facturas Pro V15 — Linux/macOS
set -e

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        GESTOR FACTURAS PRO V15 — INSTALADOR          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python3 no encontrado. Instala python3 (>= 3.10)"
    exit 1
fi
echo "[OK] Python3: $(python3 --version)"

# Crear entorno virtual
if [ ! -d "venv" ]; then
    echo "[1/8] Creando entorno virtual..."
    python3 -m venv venv
fi
echo "[OK] Entorno virtual listo"

# Activar
source venv/bin/activate

# Actualizar pip
echo "[2/8] Actualizando pip..."
pip install --upgrade pip --quiet

# Dependencias
echo "[3/8] Instalando PyQt5..."
pip install "PyQt5>=5.15.9" --quiet
echo "[4/8] Instalando PyMuPDF..."
pip install "PyMuPDF>=1.23.0" --quiet
echo "[5/8] Instalando OCR y imagen..."
pip install "pytesseract>=0.3.10" "Pillow>=10.0.0" "pdf2image>=1.16.0" "numpy>=1.24.0" --quiet
echo "[6/8] Instalando Excel y datos..."
pip install "openpyxl>=3.1.0" "pandas>=2.0.0" "matplotlib>=3.7.0" --quiet
echo "[7/8] Instalando criptografía y utilidades..."
pip install "cryptography>=41.0.0" "pypdf>=3.0.0" "reportlab>=4.0.0" "qrcode>=7.4.0" --quiet
pip install "PyYAML>=6.0.0" "python-dateutil>=2.8.2" --quiet
echo "[8/8] Instalando IA (Gemini)..."
pip install "google-generativeai>=0.7.0" --quiet || echo "[INFO] google-generativeai no instalado (opcional)"

# Verificar
echo ""
echo "[VERIFICACION] Módulos críticos:"
python3 -c "import PyQt5; print('[OK] PyQt5')" 2>/dev/null || echo "[WARN] PyQt5"
python3 -c "import fitz; print('[OK] PyMuPDF')" 2>/dev/null || echo "[WARN] PyMuPDF"
python3 -c "import pytesseract; print('[OK] pytesseract')" 2>/dev/null || echo "[WARN] pytesseract"
python3 -c "import openpyxl; print('[OK] openpyxl')" 2>/dev/null || echo "[WARN] openpyxl"
python3 -c "import cryptography; print('[OK] cryptography')" 2>/dev/null || echo "[WARN] cryptography"
python3 -c "import matplotlib; print('[OK] matplotlib')" 2>/dev/null || pip install matplotlib --quiet

# Lanzador
cat > INICIAR.sh << 'EOF'
#!/usr/bin/env bash
source "$(dirname "$0")/venv/bin/activate"
python3 "$(dirname "$0")/GESTOR_PRO.pyw" "$@"
EOF
chmod +x INICIAR.sh

# Tesseract
echo ""
echo "IMPORTANTE: Para OCR en escaneos instala Tesseract:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  brew install tesseract tesseract-lang"
else
    echo "  sudo apt install tesseract-ocr tesseract-ocr-spa"
fi
echo ""
echo "✅ Instalación completada. Ejecuta: ./INICIAR.sh"
