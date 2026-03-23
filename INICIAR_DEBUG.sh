#!/bin/bash
# GESTOR FACTURAS PRO v15.0 — MODO DEBUG (Linux / macOS)
echo "============================================================"
echo " GESTOR FACTURAS PRO v15.0 — MODO DEBUG"
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export GESTOR_DEBUG=1
export QT_DEBUG_PLUGINS=1
export PYTHONFAULTHANDLER=1
export PYTHONUNBUFFERED=1

LOGDIR="${HOME}/.local/share/GestorPro/logs"
mkdir -p "$LOGDIR"

echo "Logs en: $LOGDIR"
echo ""

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 GESTOR_PRO.pyw "$@" 2>&1 | tee "$LOGDIR/session_$(date +%Y%m%d_%H%M%S).log"
