# -*- coding: utf-8 -*-
"""
CLI y utilidades de diagnóstico del sistema.
Comandos: scan, classify, stamp, diagnostics, backup.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path


def run_diagnostics() -> str:
    """Diagnóstico completo del sistema. Devuelve string con informe."""
    lines = ["=" * 55, "  DIAGNÓSTICO — JES⚡THOR V1", "=" * 55]

    # Python
    lines.append(f"\n✔ Python: {sys.version.split()[0]}")

    # PyQt5
    try:
        from PyQt5.QtCore import PYQT_VERSION_STR
        lines.append(f"✔ PyQt5: {PYQT_VERSION_STR}")
    except ImportError:
        lines.append("✘ PyQt5: NO instalado")

    # SQLite / BD
    try:
        from database.manager import DatabaseManager
        db = DatabaseManager()
        n_provs = len(db.obtener_todos_proveedores())
        n_rules = len(db.obtener_todas_reglas_con_proveedor())
        n_hist  = db.cursor.execute("SELECT COUNT(*) FROM historial_procesado").fetchone()[0]
        lines.append(f"✔ BD SQLite: OK | {n_provs} proveedores | {n_rules} reglas | {n_hist} facturas")
    except Exception as exc:
        lines.append(f"✘ BD SQLite: {exc}")

    # pypdf
    try:
        import pypdf
        lines.append(f"✔ pypdf: {pypdf.__version__}")
    except ImportError:
        lines.append("✘ pypdf: NO instalado  →  pip install pypdf")

    # ReportLab
    try:
        import reportlab
        lines.append(f"✔ ReportLab: {reportlab.__version__}")
    except ImportError:
        lines.append("✘ ReportLab: NO instalado  →  pip install reportlab")

    # PyMuPDF
    try:
        import fitz
        lines.append(f"✔ PyMuPDF: {fitz.__version__}")
    except ImportError:
        lines.append("⚠ PyMuPDF: no instalado (optional)  →  pip install PyMuPDF")

    # Tesseract
    try:
        import pytesseract
        from core.config_loader import get_config
        tpath = get_config().tesseract_path
        if tpath:
            pytesseract.pytesseract.tesseract_cmd = tpath
        ver = pytesseract.get_tesseract_version()
        lines.append(f"✔ Tesseract: {ver}")
    except Exception as exc:
        lines.append(f"⚠ Tesseract: {exc}  →  Instalar desde UB-Mannheim")

    # OpenCV
    try:
        import cv2
        lines.append(f"✔ OpenCV: {cv2.__version__}")
    except ImportError:
        lines.append("⚠ OpenCV: no instalado (opcional)  →  pip install opencv-python")

    # Pillow
    try:
        from PIL import Image
        import PIL
        lines.append(f"✔ Pillow: {PIL.__version__}")
    except ImportError:
        lines.append("✘ Pillow: NO instalado  →  pip install Pillow")

    # PyYAML
    try:
        import yaml
        lines.append(f"✔ PyYAML: OK")
    except ImportError:
        lines.append("✘ PyYAML: NO instalado  →  pip install pyyaml")

    # win32print (solo Windows)
    try:
        import win32print
        lines.append("✔ pywin32: OK (impresión disponible)")
    except ImportError:
        lines.append("⚠ pywin32: no instalado (necesario para imprimir en Windows)")

    # Configuración
    try:
        from core.config_loader import get_config
        cfg = get_config()
        lines.append(f"\n📁 Almacenamiento: {cfg.storage_root}")
        lines.append(f"📁 Temporal:       {cfg.temp_dir}")
        lines.append(f"📁 BD:             {cfg.db_path}")
        lines.append(f"🔧 Log level:      {cfg.log_level}")
    except Exception as exc:
        lines.append(f"⚠ Config: {exc}")

    lines.append("\n" + "=" * 55)
    return "\n".join(lines)


def cmd_classify(path: str) -> None:
    """Clasifica una factura y muestra el resultado en consola."""
    from core.models import Invoice
    from classify.classifier import InvoiceClassifier
    inv = Invoice(file_path=path, file_name=Path(path).name)
    cls = InvoiceClassifier()
    cls.process(inv)
    print(f"Estado:     {inv.status.value}")
    print(f"Proveedor:  {inv.classification.vendor.name if inv.classification.vendor else 'N/A'}")
    print(f"Cuenta:     {inv.classification.expense_account}")
    print(f"Categoría:  {inv.classification.category}")
    print(f"Explicación: {inv.classification.explanation}")
    if inv.final_path:
        print(f"Archivado:  {inv.final_path}")
    if inv.errors:
        print(f"Errores:    {'; '.join(inv.errors)}")


def cmd_stamp(path: str, vendor_code: str, account: str) -> None:
    """Estampa un PDF con el código de proveedor y cuenta."""
    from watermark.stamper import stamp_pdf, is_already_stamped
    from core.exceptions import AlreadyStampedError
    if is_already_stamped(path):
        print(f"⚠ El PDF ya está estampado: {path}")
        return
    try:
        stamp_pdf(path, path, vendor_code, account, overwrite=False)
        print(f"✅ Estampado correctamente: {path}")
    except AlreadyStampedError:
        print(f"⚠ Ya estampado: {path}")
    except Exception as exc:
        print(f"❌ Error: {exc}")


def main_cli() -> None:
    """Punto de entrada para uso desde línea de comandos."""
    import argparse
    parser = argparse.ArgumentParser(description="JES⚡THOR V1 — CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("diagnostics", help="Diagnóstico del sistema")
    p_cls = sub.add_parser("classify", help="Clasificar una factura")
    p_cls.add_argument("path", help="Ruta al PDF")
    p_stm = sub.add_parser("stamp", help="Estampar un PDF")
    p_stm.add_argument("path",         help="Ruta al PDF")
    p_stm.add_argument("vendor_code",  help="Código proveedor")
    p_stm.add_argument("account",      help="Cuenta de gasto")

    args = parser.parse_args()

    if args.cmd == "diagnostics":
        print(run_diagnostics())
    elif args.cmd == "classify":
        cmd_classify(args.path)
    elif args.cmd == "stamp":
        cmd_stamp(args.path, args.vendor_code, args.account)
    else:
        parser.print_help()


if __name__ == "__main__":
    main_cli()
