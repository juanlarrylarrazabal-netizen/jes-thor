# -*- coding: utf-8 -*-
"""
visor_pdf_v12.py — Visor PDF con modo gestoría y selectores de tipo/serie.
"""
from __future__ import annotations
import sys, os, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter,
    QLabel, QLineEdit, QComboBox, QPushButton, QScrollArea,
    QWidget, QButtonGroup, QRadioButton, QGroupBox, QMessageBox,
    QSlider, QApplication, QTextEdit, QTabWidget,
    QSizePolicy, QFrame, QCheckBox, QDateEdit, QFileDialog, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QDate
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QPen, QColor,
                          QFont, QCursor, QWheelEvent)

import logging as _logging
log = _logging.getLogger("visor_pdf_manual")
if not log.handlers:
    _logging.basicConfig(level=_logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

try:
    import fitz
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False

# ── Estilos ──────────────────────────────────────────────────────────────────
BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:5px 12px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}"
         "QPushButton:disabled{background:#A0AEC0;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:5px 12px;}QPushButton:hover{background:#E2E8F0;}")
BTN_D = ("QPushButton{background:#C53030;color:white;border-radius:4px;"
         "padding:5px 12px;}QPushButton:hover{background:#9B2C2C;}")
BTN_G = ("QPushButton{background:#276749;color:white;border-radius:4px;"
         "padding:5px 12px;font-weight:bold;}QPushButton:hover{background:#38A169;}")
BTN_PRIMARY = BTN_P
BTN_SECONDARY = BTN_S
BTN_DANGER = BTN_D
BTN_SUCCESS = BTN_G

# ── Estilos mejorados para inputs ────────────────────────────────────────────
INPUT_STYLE = """
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    border: 1px solid #CBD5E0;
    border-radius: 4px;
    padding: 6px 10px;
    background: white;
    min-height: 24px;
    font-size: 11px;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #3182CE;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #CBD5E0;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px 0 5px;
}
QLabel {
    font-size: 11px;
    color: #2D3748;
}
"""

_FIELD_COLORS = {
    "cif_nif":        QColor(220, 80,  0,  140),
    "base_imponible": QColor(0,   140, 0,  140),
    "iva":            QColor(0,   80,  200, 140),
    "total":          QColor(160, 0,   180, 140),
    "numero_factura": QColor(0,   140, 160, 140),
    "razon_social":   QColor(180, 140, 0,  140),
}

_CAMPOS_REGLA = [
    ("cif_nif",        "CIF/NIF"),
    ("razon_social",   "Razón Social"),
    ("numero_factura", "Nº Factura"),
    ("base_imponible", "Base Imponible"),
    ("iva",            "IVA"),
    ("total",          "Total"),
    ("wm_datos",       "Pos. Datos WM"),
    ("wm_serie",       "Pos. Serie WM"),
]

def _get_tipos_factura(db=None) -> list:
    try:
        if db is not None:
            tipos = db.obtener_tipos_factura()
            return [t["nombre"] for t in tipos] if tipos else []
    except Exception:
        pass
    return ["FACTURA", "ABONO", "TICKET", "RECIBO"]

def _get_categorias():
    try:
        from core.config_loader import get_config
        cats = get_config().categories
        if cats:
            return cats
    except Exception:
        pass
    return ["COMBUSTIBLE", "COMUNICACIONES", "GESTORÍA",
            "MANTENIMIENTO", "SEGUROS", "SUMINISTROS", "VARIOS"]

def _inp_w(val="", ph=""):
    e = QLineEdit(str(val or ""))
    e.setPlaceholderText(ph)
    e.setStyleSheet(INPUT_STYLE)
    e.setFixedHeight(32)
    return e

def _normalise_trigger(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str).strip()

# ═══════════════════════════════════════════════════════════════════════════════
# OCR DE ZONA
# ═══════════════════════════════════════════════════════════════════════════════

def ocr_zona(page, rect_norm: tuple, user_rot: int = 0) -> str:
    if not PYMUPDF_OK or page is None:
        return ""

    x0n, y0n, x1n, y1n = rect_norm
    nr = user_rot % 360

    if nr == 90:
        ox0 = y0n;         oy0 = 1.0 - x1n
        ox1 = y1n;         oy1 = 1.0 - x0n
    elif nr == 180:
        ox0 = 1.0 - x1n;   oy0 = 1.0 - y1n
        ox1 = 1.0 - x0n;   oy1 = 1.0 - y0n
    elif nr == 270:
        ox0 = 1.0 - y1n;   oy0 = x0n
        ox1 = 1.0 - y0n;   oy1 = x1n
    else:
        ox0, oy0, ox1, oy1 = x0n, y0n, x1n, y1n
    rn_pdf = (min(ox0,ox1), min(oy0,oy1), max(ox0,ox1), max(oy0,oy1))

    pr = page.rect
    pw, ph = pr.width, pr.height
    cx0 = rn_pdf[0] * pw;  cy0 = rn_pdf[1] * ph
    cx1 = rn_pdf[2] * pw;  cy1 = rn_pdf[3] * ph
    clip = fitz.Rect(cx0, cy0, cx1, cy1)

    try:
        words = page.get_text("words", clip=clip)
        texto = " ".join(w[4] for w in words).strip()
        if texto:
            return texto
    except Exception:
        pass

    try:
        import pytesseract
        from PIL import Image

        total_render = (page.rotation + nr) % 360
        mat = fitz.Matrix(300 / 72, 300 / 72).prerotate(total_render)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_full = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        iw, ih = img_full.size
        margin = int(300 * 0.04)
        rx0 = max(0,  int(x0n * iw) - margin)
        ry0 = max(0,  int(y0n * ih) - margin)
        rx1 = min(iw, int(x1n * iw) + margin)
        ry1 = min(ih, int(y1n * ih) + margin)
        if rx1 <= rx0 or ry1 <= ry0:
            return ""

        crop = img_full.crop((rx0, ry0, rx1, ry1))
        crop = crop.convert("L")
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        
        for psm in (6, 4, 11):
            config = f"--oem 3 --psm {psm} -l spa+eng"
            result = pytesseract.image_to_string(crop, config=config).strip()
            if result:
                return result
    except Exception:
        pass
    return ""

# ═══════════════════════════════════════════════════════════════════════════════
# OCR AUTOMÁTICO DE PÁGINA COMPLETA
# ═══════════════════════════════════════════════════════════════════════════════

def ocr_pagina_completa(page) -> dict:
    try:
        from ocr.field_extractor import extract_fields
        texto = page.get_text("text") or ""
        if not texto.strip():
            try:
                import pytesseract
                from PIL import Image
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                texto = pytesseract.image_to_string(img, config="--oem 3 --psm 6 -l spa+eng")
            except Exception as e:
                log.error(f"Error en OCR de página: {e}")
        
        if texto:
            fields = extract_fields(texto)
            return {
                "cif_nif": fields.cif_nif or "",
                "base_imponible": str(fields.base_amount or ""),
                "iva": str(fields.vat_amount or ""),
                "total": str(fields.total_amount or ""),
                "numero_factura": fields.invoice_number or "",
                "razon_social": fields.vendor_name or "",
                "_raw_text": texto,
                "_issue_date": fields.issue_date,
                "_vat_pct": fields.vat_pct,        # para sugerir tipo IVA en UI
                "_tipo_iva": fields.tipo_iva,       # tipo normalizado (0/4/10/21)
            }
    except Exception as e:
        log.error(f"Error en OCR automático: {e}")
    return {}

# ═══════════════════════════════════════════════════════════════════════════════
# Canvas PDF
# ═══════════════════════════════════════════════════════════════════════════════

class _PDFCanvas(QLabel):
    zone_selected = pyqtSignal(str, str, object)
    zone_removed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMinimumSize(500, 700)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(QCursor(Qt.CrossCursor))

        self._pixmap_base = None
        self._img_w = 1
        self._img_h = 1
        self._zoom = 1.0
        self._campo = "cif_nif"
        self._mode = "select"
        self._zones = {}
        self._drag_start = None
        self._drag_cur = None
        self._drawing = False
        self._pan_start = None
        self._page_ref = None
        self._norm_rot = 0

    def set_page(self, pm: QPixmap, page_ref=None, norm_rot: int = 0):
        self._pixmap_base = pm
        self._page_ref = page_ref
        self._norm_rot = norm_rot
        self._img_w = pm.width() if pm else 1
        self._img_h = pm.height() if pm else 1
        self._render()

    def set_campo(self, c):
        self._campo = c

    def set_zoom(self, z):
        self._zoom = max(0.3, min(z, 5.0))
        self._render()

    def set_mode(self, mode):
        self._mode = mode
        self.setCursor(QCursor(Qt.OpenHandCursor if mode == "hand" else Qt.CrossCursor))

    def set_zones(self, zones: dict):
        self._zones = zones.copy()
        self._render()

    def clear_all_zones(self):
        self._zones.clear()
        self._render()

    def remove_zone(self, campo: str):
        if campo in self._zones:
            del self._zones[campo]
            self._render()
            self.zone_removed.emit(campo)

    def _render(self):
        if self._pixmap_base is None:
            return
        z = self._zoom
        w = int(self._img_w * z)
        h = int(self._img_h * z)
        pm = self._pixmap_base.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation).copy()
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        for campo, info in self._zones.items():
            rn = info["rect_norm"]
            color = _FIELD_COLORS.get(campo, QColor(100, 100, 255, 140))
            sx = int(rn[0] * w)
            sy = int(rn[1] * h)
            sw = int((rn[2] - rn[0]) * w)
            sh = int((rn[3] - rn[1]) * h)
            sr = QRect(sx, sy, sw, sh)
            p.fillRect(sr, QColor(color.red(), color.green(), color.blue(), 50))
            p.setPen(QPen(color, 2))
            p.drawRect(sr)

            # Etiqueta del campo
            lbl = next((n for k, n in _CAMPOS_REGLA if k == campo), campo)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(QPen(QColor(255, 255, 255), 1))
            bg = QRect(sr.x(), sr.y(), min(sr.width(), 80), 16)
            p.fillRect(bg, QColor(color.red(), color.green(), color.blue(), 200))
            p.drawText(bg.adjusted(2, 1, -2, -1), Qt.AlignVCenter, lbl)

            texto = info.get("texto", "")
            if texto:
                p.setFont(QFont("Segoe UI", 7))
                p.setPen(QPen(QColor(0, 0, 0), 1))
                p.drawText(sr.adjusted(2, 17, -2, -2), Qt.AlignTop | Qt.TextWordWrap, texto[:80])

        if self._drawing and self._drag_start and self._drag_cur:
            color = _FIELD_COLORS.get(self._campo, QColor(100, 100, 255, 140))
            r = QRect(self._drag_start, self._drag_cur).normalized()
            p.fillRect(r, QColor(color.red(), color.green(), color.blue(), 30))
            p.setPen(QPen(color, 2, Qt.DashLine))
            p.drawRect(r)
        p.end()
        self.setPixmap(pm)
        self.resize(pm.size())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self._mode == "select":
                self._drag_start = ev.pos()
                self._drag_cur = ev.pos()
                self._drawing = True
            elif self._mode == "hand":
                self._pan_start = ev.pos()
                self.setCursor(QCursor(Qt.ClosedHandCursor))
        elif ev.button() == Qt.RightButton:
            for campo, info in self._zones.items():
                rn = info["rect_norm"]
                sx = int(rn[0] * self._img_w * self._zoom)
                sy = int(rn[1] * self._img_h * self._zoom)
                sw = int((rn[2] - rn[0]) * self._img_w * self._zoom)
                sh = int((rn[3] - rn[1]) * self._img_h * self._zoom)
                if sx <= ev.x() <= sx + sw and sy <= ev.y() <= sy + sh:
                    self.remove_zone(campo)
                    break

    def mouseMoveEvent(self, ev):
        if self._mode == "select" and self._drawing:
            self._drag_cur = ev.pos()
            self._render()
        elif self._mode == "hand" and self._pan_start:
            d = ev.pos() - self._pan_start
            self._pan_start = ev.pos()
            sc = self.parent()
            if sc and hasattr(sc, "horizontalScrollBar"):
                sc.horizontalScrollBar().setValue(sc.horizontalScrollBar().value() - d.x())
                sc.verticalScrollBar().setValue(sc.verticalScrollBar().value() - d.y())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self._mode == "select" and self._drawing:
                self._drawing = False
                raw = QRect(self._drag_start, ev.pos()).normalized()
                if raw.width() > 8 and raw.height() > 8:
                    iw = self._img_w * self._zoom
                    ih = self._img_h * self._zoom
                    x0n = max(0.0, min(1.0, raw.x() / iw))
                    y0n = max(0.0, min(1.0, raw.y() / ih))
                    x1n = max(0.0, min(1.0, (raw.x() + raw.width()) / iw))
                    y1n = max(0.0, min(1.0, (raw.y() + raw.height()) / ih))
                    rn_view = (x0n, y0n, x1n, y1n)
                    user_rot = getattr(self, "_norm_rot", 0) % 360
                    texto = ocr_zona(self._page_ref, rn_view, user_rot=user_rot)
                    self._zones[self._campo] = {"rect_norm": rn_view, "texto": texto}
                    self._render()
                    self.zone_selected.emit(self._campo, texto, rn_view)
            elif self._mode == "hand":
                self._pan_start = None
                self.setCursor(QCursor(Qt.OpenHandCursor))

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self._zoom + (0.1 if ev.angleDelta().y() > 0 else -0.1))
            ev.accept()
        else:
            super().wheelEvent(ev)


# ═══════════════════════════════════════════════════════════════════════════════
# Panel Reglas (con selectores de tipo y serie)
# ═══════════════════════════════════════════════════════════════════════════════

class _PanelReglas(QWidget):
    rule_saved = pyqtSignal(dict)
    rule_updated = pyqtSignal(dict)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._campos_texto = {}
        self._campos_rect_norm = {}
        self._ocr_auto = {}
        self._ultima_plantilla_textos = {}  # caché textos plantilla activa para _on_zone
        self._reglas_cache = []
        self._current_regla_id = None
        self._val_labels = {}
        self._canvas = None
        self._build()
        self._load_proveedores()

    def _create_label_value(self, text="—", color="#276749"):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{color};font-size:11px;font-weight:bold;background:#F7FAFC;padding:4px 8px;border-radius:4px;")
        lbl.setWordWrap(True)
        lbl.setMinimumHeight(28)
        return lbl

    def _cargar_tipos_factura(self):
        """Carga los tipos de factura desde la BD."""
        self.cmb_tipo_factura.clear()
        self.cmb_tipo_factura.addItem("— Seleccionar tipo —", "")
        try:
            tipos = self.db.obtener_tipos_factura()
            for t in tipos:
                self.cmb_tipo_factura.addItem(t["nombre"], t["id"])
        except Exception as e:
            log.error(f"Error cargando tipos: {e}")

    def _cargar_series(self):
        """Carga las series desde la BD."""
        self.cmb_serie.clear()
        self.cmb_serie.addItem("— Seleccionar serie —", "")
        try:
            series = self.db.obtener_series_factura()
            for s in series:
                self.cmb_serie.addItem(s["nombre"], s["id"])
        except Exception as e:
            log.error(f"Error cargando series: {e}")

    def _build(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        # Ancho mínimo para que los campos no se compriman
        self.setMinimumWidth(420)

        # Título
        title = QLabel("📋 ENTRENADOR DE REGLAS")
        title.setStyleSheet("font-size:14px;font-weight:bold;color:#1F4E79;padding:4px;")
        main_layout.addWidget(title)

        # --- SECCIÓN 1: PROVEEDOR Y REGLA (2 columnas) ---
        grid_top = QGridLayout()
        grid_top.setHorizontalSpacing(15)
        grid_top.setVerticalSpacing(10)

        # Proveedor
        prov_box = QGroupBox("Proveedor")
        prov_layout = QFormLayout(prov_box)
        self.cmb_proveedor = QComboBox()
        self.cmb_proveedor.setStyleSheet(INPUT_STYLE)
        self.cmb_proveedor.setMinimumHeight(32)
        self.cmb_proveedor.currentIndexChanged.connect(self._on_proveedor_changed)
        prov_layout.addRow("Seleccionar:", self.cmb_proveedor)

        self.inp_prov_nombre = QLineEdit()
        self.inp_prov_nombre.setPlaceholderText("Nuevo nombre de proveedor")
        self.inp_prov_nombre.setStyleSheet(INPUT_STYLE)
        self.inp_prov_nombre.setMinimumHeight(32)
        prov_layout.addRow("Nuevo:", self.inp_prov_nombre)

        self.inp_numero_proveedor = QLineEdit()
        self.inp_numero_proveedor.setPlaceholderText("Ej: 001, PRV-023...")
        self.inp_numero_proveedor.setStyleSheet(INPUT_STYLE)
        self.inp_numero_proveedor.setMinimumHeight(32)
        prov_layout.addRow("Nº Proveedor:", self.inp_numero_proveedor)

        grid_top.addWidget(prov_box, 0, 0)

        # Regla a editar
        rule_box = QGroupBox("Regla a editar")
        rule_layout = QVBoxLayout(rule_box)
        rule_sel_layout = QHBoxLayout()
        rule_sel_layout.addWidget(QLabel("Regla:"))
        self.cmb_regla = QComboBox()
        self.cmb_regla.setStyleSheet(INPUT_STYLE)
        self.cmb_regla.setMinimumHeight(32)
        self.cmb_regla.currentIndexChanged.connect(self._on_regla_changed)
        rule_sel_layout.addWidget(self.cmb_regla)
        rule_layout.addLayout(rule_sel_layout)

        self.lbl_regla_id = QLabel("ID: —")
        self.lbl_regla_id.setStyleSheet("color:#718096;font-size:10px;")
        rule_layout.addWidget(self.lbl_regla_id)

        grid_top.addWidget(rule_box, 0, 1)

        main_layout.addLayout(grid_top)

        # --- SECCIÓN 2: TRIGGER ---
        trigger_box = QGroupBox("Trigger (palabra clave)")
        trigger_layout = QVBoxLayout(trigger_box)
        trigger_inp_row = QHBoxLayout()
        self.inp_trigger = QLineEdit()
        self.inp_trigger.setPlaceholderText("Ej: rectificacion, albaran, factura...")
        self.inp_trigger.setStyleSheet(INPUT_STYLE)
        self.inp_trigger.setMinimumHeight(32)
        trigger_inp_row.addWidget(self.inp_trigger)
        btn_check_trigger = QPushButton("🔍 Comprobar")
        btn_check_trigger.setStyleSheet(BTN_SECONDARY)
        btn_check_trigger.setFixedHeight(32)
        btn_check_trigger.setToolTip("Valida si el trigger aparece en el texto OCR de la factura")
        btn_check_trigger.clicked.connect(self._comprobar_trigger)
        trigger_inp_row.addWidget(btn_check_trigger)
        trigger_layout.addLayout(trigger_inp_row)
        self.lbl_trigger_resultado = QLabel("")
        self.lbl_trigger_resultado.setStyleSheet("font-size:10px;padding:2px 4px;")
        trigger_layout.addWidget(self.lbl_trigger_resultado)
        main_layout.addWidget(trigger_box)

        # --- SECCIÓN 3: CONFIGURACIÓN CONTABLE (con tipos y series) ---
        cuenta_box = QGroupBox("Configuración contable")
        cuenta_layout = QGridLayout(cuenta_box)
        cuenta_layout.setHorizontalSpacing(10)
        cuenta_layout.setVerticalSpacing(8)

        # Fila 1: Cuenta gasto y Tipo Factura
        cuenta_layout.addWidget(QLabel("Cuenta gasto:"), 0, 0)
        self.inp_cuenta_gasto = QLineEdit()
        self.inp_cuenta_gasto.setPlaceholderText("628000")
        self.inp_cuenta_gasto.setStyleSheet(INPUT_STYLE)
        self.inp_cuenta_gasto.setMinimumHeight(32)
        cuenta_layout.addWidget(self.inp_cuenta_gasto, 0, 1)

        cuenta_layout.addWidget(QLabel("Tipo Factura:"), 0, 2)
        self.cmb_tipo_factura = QComboBox()
        self.cmb_tipo_factura.setStyleSheet(INPUT_STYLE)
        self.cmb_tipo_factura.setMinimumHeight(32)
        self._cargar_tipos_factura()
        cuenta_layout.addWidget(self.cmb_tipo_factura, 0, 3)

        # Fila 2: Categoría y Serie
        cuenta_layout.addWidget(QLabel("Categoría:"), 1, 0)
        self.cmb_cat = QComboBox()
        self.cmb_cat.setStyleSheet(INPUT_STYLE)
        self.cmb_cat.setMinimumHeight(32)
        for c in _get_categorias():
            self.cmb_cat.addItem(c)
        cuenta_layout.addWidget(self.cmb_cat, 1, 1)

        cuenta_layout.addWidget(QLabel("Serie:"), 1, 2)
        self.cmb_serie = QComboBox()
        self.cmb_serie.setStyleSheet(INPUT_STYLE)
        self.cmb_serie.setMinimumHeight(32)
        self._cargar_series()
        cuenta_layout.addWidget(self.cmb_serie, 1, 3)

        # Fila 3: Cuenta proveedor / subcuenta
        cuenta_layout.addWidget(QLabel("Cta/Sub Prov:"), 2, 0)
        prov_sub_layout = QHBoxLayout()
        self.inp_cta_proveedor = QLineEdit()
        self.inp_cta_proveedor.setText("400000")
        self.inp_cta_proveedor.setStyleSheet(INPUT_STYLE)
        self.inp_cta_proveedor.setFixedWidth(80)
        self.inp_cta_proveedor.setMinimumHeight(32)
        prov_sub_layout.addWidget(self.inp_cta_proveedor)
        prov_sub_layout.addWidget(QLabel("/"))
        self.inp_sub_proveedor = QLineEdit()
        self.inp_sub_proveedor.setPlaceholderText("subcuenta")
        self.inp_sub_proveedor.setStyleSheet(INPUT_STYLE)
        self.inp_sub_proveedor.setMinimumHeight(32)
        prov_sub_layout.addWidget(self.inp_sub_proveedor)
        cuenta_layout.addLayout(prov_sub_layout, 2, 1, 1, 3)

        # Fila 4: Subcuenta gasto
        cuenta_layout.addWidget(QLabel("Subcuenta gasto:"), 3, 0)
        self.inp_subcuenta_gasto = QLineEdit()
        self.inp_subcuenta_gasto.setPlaceholderText("opcional")
        self.inp_subcuenta_gasto.setStyleSheet(INPUT_STYLE)
        self.inp_subcuenta_gasto.setMinimumHeight(32)
        cuenta_layout.addWidget(self.inp_subcuenta_gasto, 3, 1, 1, 1)

        # Fila 4 continuación: Tipo IVA
        cuenta_layout.addWidget(QLabel("Tipo IVA:"), 3, 2)
        self.cmb_tipo_iva = QComboBox()
        self.cmb_tipo_iva.setStyleSheet(INPUT_STYLE)
        self.cmb_tipo_iva.setMinimumHeight(32)
        self.cmb_tipo_iva.addItem("21% (General)",      21)
        self.cmb_tipo_iva.addItem("10% (Reducido)",     10)
        self.cmb_tipo_iva.addItem("4% (Superreducido)", 4)
        self.cmb_tipo_iva.addItem("0% (Exenta)",        0)
        self.cmb_tipo_iva.setToolTip(
            "Tipo de IVA aplicable a este proveedor/regla.\n"
            "El OCR intentará detectarlo automáticamente.\n"
            "21% es el valor por defecto.")
        # FIX-REGRESION-2: solo marcar como tocado cuando el USUARIO lo cambia
        # explícitamente, no cuando lo cambia el OCR o la regla programáticamente
        self._tipo_iva_user_touched = False
        self.cmb_tipo_iva.activated.connect(self._on_tipo_iva_user_changed)
        cuenta_layout.addWidget(self.cmb_tipo_iva, 3, 3)

        main_layout.addWidget(cuenta_box)

        # --- SECCIÓN 4: OPCIONES ESPECIALES ---
        options_layout = QHBoxLayout()
        options_layout.setSpacing(15)

        self.chk_variable = QCheckBox("Proveedor variable")
        self.chk_variable.setStyleSheet("font-size:11px;")
        options_layout.addWidget(self.chk_variable)

        self.chk_rectificativa = QCheckBox("Rectificativa / abono")
        self.chk_rectificativa.setStyleSheet("font-size:11px;color:#C53030;")
        options_layout.addWidget(self.chk_rectificativa)

        self.chk_gestoria = QCheckBox("Factura de gestoría")
        self.chk_gestoria.setStyleSheet("font-size:11px;color:#9F7AEA;")
        self.chk_gestoria.toggled.connect(self._on_gestoria_toggled)
        options_layout.addWidget(self.chk_gestoria)

        self.chk_retencion = QCheckBox("Con retención IRPF")
        self.chk_retencion.setStyleSheet("font-size:11px;color:#C05621;")
        self.chk_retencion.toggled.connect(self._on_retencion_toggled)
        options_layout.addWidget(self.chk_retencion)

        self.chk_reparto = QCheckBox("Reparto entre cuentas")
        self.chk_reparto.setStyleSheet("font-size:11px;color:#2B6CB0;")
        self.chk_reparto.toggled.connect(self._on_reparto_toggled)
        options_layout.addWidget(self.chk_reparto)

        self.chk_cont_auto = QCheckBox("Cont. automática")
        self.chk_cont_auto.setStyleSheet("font-size:11px;color:#1A6B4A;font-weight:bold;")
        self.chk_cont_auto.setToolTip("Marcar si el DMS contabiliza esta factura automáticamente.")
        options_layout.addWidget(self.chk_cont_auto)

        options_layout.addStretch()
        main_layout.addLayout(options_layout)

        # --- SECCIÓN 5: VALORES DETECTADOS (TABLA LIMPIA) ---
        valores_box = QGroupBox("📊 Valores detectados por OCR")
        valores_layout = QGridLayout(valores_box)
        valores_layout.setHorizontalSpacing(15)
        valores_layout.setVerticalSpacing(8)

        # Crear etiquetas en grid de 2 columnas
        campos_mostrar = [
            ("CIF/NIF:", "cif_nif"),
            ("Razón Social:", "razon_social"),
            ("Nº Factura:", "numero_factura"),
            ("Base Imponible:", "base_imponible"),
            ("IVA:", "iva"),
            ("Total:", "total"),
        ]

        for i, (label, key) in enumerate(campos_mostrar):
            row = i // 2
            col = (i % 2) * 2
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight:bold;color:#4A5568;")
            valores_layout.addWidget(lbl, row, col)

            valor_lbl = self._create_label_value()
            self._val_labels[key] = valor_lbl
            valores_layout.addWidget(valor_lbl, row, col + 1)

        # Campo fecha de factura editable
        row_fecha = len(campos_mostrar) // 2
        lbl_fecha = QLabel("Fecha Factura:")
        lbl_fecha.setStyleSheet("font-weight:bold;color:#4A5568;")
        valores_layout.addWidget(lbl_fecha, row_fecha, 0)
        self.inp_fecha_factura = QDateEdit()
        self.inp_fecha_factura.setCalendarPopup(True)
        self.inp_fecha_factura.setDate(QDate.currentDate())
        self.inp_fecha_factura.setDisplayFormat("dd/MM/yyyy")
        self.inp_fecha_factura.setStyleSheet(INPUT_STYLE)
        self.inp_fecha_factura.setMinimumHeight(28)
        # FIX-TECLADO: permitir edición manual con teclado (DD/MM/YYYY)
        self.inp_fecha_factura.lineEdit().setReadOnly(False)
        self.inp_fecha_factura.setToolTip("Fecha de la factura — editable con teclado (DD/MM/YYYY) o calendario")
        valores_layout.addWidget(self.inp_fecha_factura, row_fecha, 1)

        main_layout.addWidget(valores_box)

        # --- SECCIÓN 5b: VALORES A PROCESAR (plantilla > OCR) ---
        # Este panel muestra lo que REALMENTE se va a clasificar/guardar,
        # con la prioridad correcta: plantilla entrenada > OCR automático
        self._proc_box = QGroupBox("📋 Valores a procesar (plantilla > OCR)")
        self._proc_box.setStyleSheet(
            "QGroupBox{font-weight:bold;color:#1F4E79;"
            "border:2px solid #3182CE;border-radius:6px;"
            "margin-top:8px;padding-top:10px;}")
        proc_layout = QGridLayout(self._proc_box)
        proc_layout.setHorizontalSpacing(15)
        proc_layout.setVerticalSpacing(6)

        self._proc_labels = {}
        campos_proc = [
            ("Nº Factura:", "numero_factura"),
            ("Base Imponible:", "base_imponible"),
            ("IVA:", "iva"),
            ("Total:", "total"),
        ]
        _PROC_STYLE = ("font-size:12px;font-weight:bold;color:#1F4E79;"
                       "background:#EBF8FF;padding:4px 8px;border-radius:4px;"
                       "border:1px solid #90CDF4;")
        for i, (label, key) in enumerate(campos_proc):
            row = i // 2; col = (i % 2) * 2
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight:bold;color:#2B6CB0;")
            proc_layout.addWidget(lbl, row, col)
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(_PROC_STYLE)
            val_lbl.setMinimumWidth(100)
            self._proc_labels[key] = val_lbl
            proc_layout.addWidget(val_lbl, row, col + 1)

        main_layout.addWidget(self._proc_box)
        campo_box = QGroupBox("🎯 Campo activo para seleccionar zona")
        campo_layout = QHBoxLayout(campo_box)
        self._bg = QButtonGroup(self)

        for key, nombre in _CAMPOS_REGLA:
            rb = QRadioButton(nombre)
            rb.setStyleSheet("font-size:11px;")
            rb.toggled.connect(
                lambda chk, k=key: (
                    self._canvas and self._canvas.set_campo(k)
                ) if chk and self._canvas else None
            )
            self._bg.addButton(rb)
            campo_layout.addWidget(rb)

        campo_layout.addStretch()
        main_layout.addWidget(campo_box)

        # --- SECCIÓN WM: POSICIÓN MARCA DE AGUA (OPCIONAL) ---
        wm_box = QGroupBox("🖊 Posición Marca de Agua (opcional)")
        wm_box.setStyleSheet("QGroupBox{color:#744210;font-size:10px;border:1px solid #ECC94B;"
                             "border-radius:4px;margin-top:6px;padding-top:8px;}")
        wm_layout = QHBoxLayout(wm_box)
        wm_layout.setSpacing(8)

        lbl_wm = QLabel("Dibuja una zona en el PDF con 'Pos. Datos WM' o 'Pos. Serie WM' "
                         "seleccionado para fijar dónde se coloca la marca de agua.")
        lbl_wm.setWordWrap(True)
        lbl_wm.setStyleSheet("color:#744210;font-size:10px;")
        wm_layout.addWidget(lbl_wm)

        btn_clear_wm = QPushButton("🗑 Limpiar posiciones WM")
        btn_clear_wm.setStyleSheet("QPushButton{background:#FFF9C4;color:#744210;border:1px solid #ECC94B;"
                                    "border-radius:4px;padding:4px 8px;font-size:10px;}"
                                    "QPushButton:hover{background:#FEFCBF;}")
        btn_clear_wm.setFixedHeight(28)
        btn_clear_wm.clicked.connect(self._clear_wm_positions)
        wm_layout.addWidget(btn_clear_wm)

        main_layout.addWidget(wm_box)

        # --- SECCIÓN 7: GESTORÍA (OCULTO INICIALMENTE) ---
        self.grp_gestoria = QGroupBox("💰 Modo Gestoría")
        self.grp_gestoria.setStyleSheet("QGroupBox{color:#9F7AEA;}")
        gest_layout = QFormLayout(self.grp_gestoria)

        self.inp_iva_gestoria = QLineEdit()
        self.inp_iva_gestoria.setPlaceholderText("IVA honorarios (ej: 4,73)")
        self.inp_iva_gestoria.setStyleSheet(INPUT_STYLE + "background:#F3E8FF;")
        self.inp_iva_gestoria.setEnabled(True)   # editable manualmente
        self.inp_iva_gestoria.setMinimumHeight(32)
        self.inp_iva_gestoria.textChanged.connect(self._on_iva_gestoria_changed)
        gest_layout.addRow("IVA honorarios:", self.inp_iva_gestoria)

        self.lbl_base_calculada = QLabel("—")
        self.lbl_base_calculada.setStyleSheet("color:#9F7AEA;font-size:12px;font-weight:bold;background:#FAF5FF;padding:6px;border-radius:4px;")
        gest_layout.addRow("Base calculada:", self.lbl_base_calculada)

        info = QLabel("Selecciona el campo IVA y dibuja un rectángulo. Base = Total - IVA")
        info.setStyleSheet("color:#553C9A;font-size:10px;padding:4px;")
        info.setWordWrap(True)
        gest_layout.addRow(info)

        self.grp_gestoria.setVisible(False)
        main_layout.addWidget(self.grp_gestoria)

        # ── Panel Retención IRPF ─────────────────────────────────────────────
        self.grp_retencion = QGroupBox("🔻 Retención IRPF")
        self.grp_retencion.setStyleSheet("QGroupBox{color:#C05621;font-weight:bold;"
                                          "border:1px solid #FBD38D;border-radius:6px;"
                                          "margin-top:8px;padding-top:10px;}")
        ret_layout = QFormLayout(self.grp_retencion)

        self.inp_ret_pct = QLineEdit()
        self.inp_ret_pct.setPlaceholderText("% retención (ej: 15)")
        self.inp_ret_pct.setStyleSheet(INPUT_STYLE + "background:#FFFAF0;")
        self.inp_ret_pct.setFixedHeight(30)
        self.inp_ret_pct.textChanged.connect(self._on_retencion_pct_changed)
        ret_layout.addRow("% Retención:", self.inp_ret_pct)

        self.inp_ret_importe = QLineEdit()
        self.inp_ret_importe.setPlaceholderText("Importe retenido (calculado automáticamente)")
        self.inp_ret_importe.setStyleSheet(INPUT_STYLE + "background:#FFFAF0;")
        self.inp_ret_importe.setFixedHeight(30)
        ret_layout.addRow("Importe ret.:", self.inp_ret_importe)

        self.lbl_liquido = QLabel("—")
        self.lbl_liquido.setStyleSheet("color:#C05621;font-size:12px;font-weight:bold;"
                                        "background:#FFFAF0;padding:6px;border-radius:4px;")
        ret_layout.addRow("Líquido a pagar:", self.lbl_liquido)

        self.grp_retencion.setVisible(False)
        main_layout.addWidget(self.grp_retencion)

        # ── Panel Reparto entre cuentas ──────────────────────────────────────
        self.grp_reparto = QGroupBox("🔀 Reparto de gasto entre cuentas")
        self.grp_reparto.setStyleSheet("QGroupBox{color:#2B6CB0;font-weight:bold;"
                                        "border:1px solid #90CDF4;border-radius:6px;"
                                        "margin-top:8px;padding-top:10px;}")
        rep_layout = QVBoxLayout(self.grp_reparto)

        # Tabla de líneas de reparto
        self._tbl_reparto = QTableWidget(0, 3)
        self._tbl_reparto.setHorizontalHeaderLabels(["Cuenta", "% Base", "Importe"])
        self._tbl_reparto.horizontalHeader().setStretchLastSection(True)
        self._tbl_reparto.setMinimumHeight(130)
        self._tbl_reparto.setMaximumHeight(220)
        self._tbl_reparto.setStyleSheet("QTableWidget{border:1px solid #BEE3F8;}")
        rep_layout.addWidget(self._tbl_reparto)

        btn_rep_row = QHBoxLayout()
        btn_add_rep = QPushButton("➕ Añadir cuenta")
        btn_add_rep.setStyleSheet("QPushButton{background:#2B6CB0;color:white;"
                                   "border-radius:4px;padding:4px 10px;font-size:10px;}"
                                   "QPushButton:hover{background:#1F4E79;}")
        btn_add_rep.clicked.connect(self._add_reparto_row)
        btn_del_rep = QPushButton("🗑 Eliminar")
        btn_del_rep.setStyleSheet("QPushButton{background:#E53E3E;color:white;"
                                   "border-radius:4px;padding:4px 10px;font-size:10px;}"
                                   "QPushButton:hover{background:#C53030;}")
        btn_del_rep.clicked.connect(self._del_reparto_row)
        self.lbl_reparto_total = QLabel("Total: 0%")
        self.lbl_reparto_total.setStyleSheet("color:#2B6CB0;font-weight:bold;font-size:10px;")
        btn_rep_row.addWidget(btn_add_rep)
        btn_rep_row.addWidget(btn_del_rep)
        btn_rep_row.addStretch()
        btn_rep_row.addWidget(self.lbl_reparto_total)
        rep_layout.addLayout(btn_rep_row)

        self.grp_reparto.setVisible(False)
        main_layout.addWidget(self.grp_reparto)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_save_new = QPushButton("💾 Guardar nueva")
        btn_save_new.setStyleSheet(BTN_PRIMARY)
        btn_save_new.setFixedHeight(38)
        btn_save_new.clicked.connect(self._guardar_nueva)

        btn_update = QPushButton("🔄 Actualizar")
        btn_update.setStyleSheet(BTN_SUCCESS)
        btn_update.setFixedHeight(38)
        btn_update.clicked.connect(self._actualizar_regla)

        btn_clear = QPushButton("🗑️ Limpiar zonas")
        btn_clear.setStyleSheet(BTN_DANGER)
        btn_clear.setFixedHeight(38)
        btn_clear.clicked.connect(self._clear)

        btn_layout.addWidget(btn_save_new)
        btn_layout.addWidget(btn_update)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)
        main_layout.addStretch()

        # Marcar primer radio button
        if self._bg.buttons():
            self._bg.buttons()[0].setChecked(True)

    def _on_gestoria_toggled(self, checked):
        self.grp_gestoria.setVisible(checked)
        if checked:
            if "iva" in self._val_labels:
                self._val_labels["iva"].setStyleSheet("color:#9F7AEA;font-size:11px;font-weight:bold;background:#FAF5FF;padding:4px 8px;border-radius:4px;")
            # Recalcular si ya hay IVA cargado
            self._recalc_base_gestoria()
        else:
            if "iva" in self._val_labels:
                self._val_labels["iva"].setStyleSheet("color:#276749;font-size:11px;font-weight:bold;background:#F7FAFC;padding:4px 8px;border-radius:4px;")
            self.inp_iva_gestoria.clear()
            self.lbl_base_calculada.setText("—")

    def _on_iva_gestoria_changed(self, texto):
        """Recalcula base cuando el usuario escribe o cambia el IVA de gestoría."""
        self._recalc_base_gestoria()

    def _recalc_base_gestoria(self):
        """
        Calcula base = Total - IVA_honorarios y actualiza el display.
        Se llama cuando cambia el IVA, cuando carga la plantilla o cuando llega el OCR.
        """
        if not hasattr(self, "chk_gestoria") or not self.chk_gestoria.isChecked():
            return
        try:
            from core.utils import parse_es_float_safe as _pfs
            iva_text  = self.inp_iva_gestoria.text().strip()
            iva_val   = _pfs(iva_text, 0.0)
            if iva_val <= 0:
                return
            # Total: primero lo marcado por el usuario, luego OCR
            total_text = (self._campos_texto.get("total", "") or
                          self._ocr_auto.get("total", ""))
            total_val  = _pfs(total_text, 0.0)
            if total_val <= 0:
                return

            base_calc = round(total_val - iva_val, 2)
            # Actualizar display
            self.lbl_base_calculada.setText(f"{base_calc:.2f} €")
            ok = abs(base_calc + iva_val - total_val) < 0.02
            color = "#9F7AEA" if ok else "#C53030"
            bg    = "#FAF5FF" if ok else "#FED7D7"
            self.lbl_base_calculada.setStyleSheet(
                f"color:{color};font-size:12px;font-weight:bold;"
                f"background:{bg};padding:6px;border-radius:4px;")

            # Actualizar val_labels base
            self._campos_texto["base_imponible"] = f"{base_calc:.2f}"
            if "base_imponible" in self._val_labels:
                self._val_labels["base_imponible"].setText(f"{base_calc:.2f} €")
                self._val_labels["base_imponible"].setStyleSheet(
                    "color:#9F7AEA;font-size:11px;font-weight:bold;"
                    "background:#FAF5FF;padding:4px 8px;border-radius:4px;")

            # Actualizar panel "Valores a procesar"
            _plantilla_actual = getattr(self, "_ultima_plantilla_textos", {})
            self._actualizar_proc_labels(_plantilla_actual)

            log.debug("Gestoría recalc: base=%s (total=%s - iva=%s)",
                      base_calc, total_val, iva_val)
        except Exception as e:
            log.debug("Gestoría recalc error: %s", e)

    def _on_tipo_iva_user_changed(self, _index):
        """Señal 'activated' solo se emite cuando el USUARIO hace clic → marcamos como tocado."""
        self._tipo_iva_user_touched = True

    def _on_retencion_toggled(self, checked):
        self.grp_retencion.setVisible(checked)
        if not checked:
            self.inp_ret_pct.clear()
            self.inp_ret_importe.clear()
            self.lbl_liquido.setText("—")

    def _on_retencion_pct_changed(self, texto):
        """Calcula automáticamente el importe de retención desde la base."""
        try:
            from core.utils import parse_es_float_safe as _pfs
            pct  = _pfs(texto, 0.0)
            base = _pfs(self._campos_texto.get("base_imponible", "") or
                        self._ocr_auto.get("base_imponible", ""), 0.0)
            if pct > 0 and base > 0:
                importe = round(base * pct / 100, 2)
                self.inp_ret_importe.setText(f"{importe:.2f}")
                # Calcular líquido: total - retención
                total = _pfs(self._campos_texto.get("total", "") or
                             self._ocr_auto.get("total", ""), 0.0)
                if total > 0:
                    liquido = round(total - importe, 2)
                    self.lbl_liquido.setText(f"{liquido:.2f} €")
        except Exception:
            pass

    def _on_reparto_toggled(self, checked):
        self.grp_reparto.setVisible(checked)
        if checked and self._tbl_reparto.rowCount() == 0:
            self._add_reparto_row()

    def _add_reparto_row(self):
        r = self._tbl_reparto.rowCount()
        self._tbl_reparto.insertRow(r)
        self._tbl_reparto.setItem(r, 0, QTableWidgetItem(""))   # cuenta
        self._tbl_reparto.setItem(r, 1, QTableWidgetItem(""))   # % base
        self._tbl_reparto.setItem(r, 2, QTableWidgetItem(""))   # importe
        self._tbl_reparto.cellChanged.connect(self._recalc_reparto)

    def _del_reparto_row(self):
        row = self._tbl_reparto.currentRow()
        if row >= 0:
            self._tbl_reparto.removeRow(row)
            self._recalc_reparto()

    def _recalc_reparto(self):
        """Recalcula importes de reparto y verifica que sumen 100%."""
        from core.utils import parse_es_float_safe as _pfs
        base = _pfs(self._campos_texto.get("base_imponible", "") or
                    self._ocr_auto.get("base_imponible", ""), 0.0)
        total_pct = 0.0
        self._tbl_reparto.cellChanged.disconnect()
        for r in range(self._tbl_reparto.rowCount()):
            try:
                pct_item = self._tbl_reparto.item(r, 1)
                pct = _pfs(pct_item.text() if pct_item else "", 0.0)
                total_pct += pct
                if base > 0 and pct > 0:
                    importe = round(base * pct / 100, 2)
                    self._tbl_reparto.setItem(r, 2, QTableWidgetItem(f"{importe:.2f}"))
            except Exception:
                pass
        color = "#276749" if abs(total_pct - 100) < 0.01 else "#C53030"
        self.lbl_reparto_total.setText(f"Total: {total_pct:.0f}%")
        self.lbl_reparto_total.setStyleSheet(f"color:{color};font-weight:bold;font-size:10px;")
        try:
            self._tbl_reparto.cellChanged.connect(self._recalc_reparto)
        except Exception:
            pass

    def _get_reparto_cuentas(self) -> list:
        """Devuelve la lista de reparto del panel como lista de dicts."""
        from core.utils import parse_es_float_safe as _pfs
        result = []
        for r in range(self._tbl_reparto.rowCount()):
            cta_item = self._tbl_reparto.item(r, 0)
            pct_item = self._tbl_reparto.item(r, 1)
            imp_item = self._tbl_reparto.item(r, 2)
            cta = (cta_item.text().strip() if cta_item else "")
            pct = _pfs(pct_item.text() if pct_item else "", 0.0)
            imp = _pfs(imp_item.text() if imp_item else "", 0.0)
            if cta and pct > 0:
                result.append({"cuenta": cta, "pct": pct, "importe": imp})
        return result

    def _load_proveedores(self):
        self.cmb_proveedor.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_proveedor.addItem("— Seleccionar proveedor —", None)
        try:
            for p in self.db.obtener_todos_proveedores():
                self.cmb_proveedor.addItem(f"{p['nombre']} [{p['numero_proveedor']}]", p)
        except Exception as e:
            log.error(f"Error cargando proveedores: {e}")
        self.cmb_proveedor.blockSignals(False)

    def _on_proveedor_changed(self, idx):
        prov_data = self.cmb_proveedor.itemData(idx)
        if prov_data:
            proveedor_id = prov_data.get("id")
            self._load_reglas_proveedor(proveedor_id)
            self.inp_prov_nombre.setText(prov_data.get("nombre", ""))
            self.inp_numero_proveedor.setText(prov_data.get("numero_proveedor", ""))
        else:
            self.cmb_regla.clear()
            self._reglas_cache = []
            self._current_regla_id = None
            self.lbl_regla_id.setText("ID: —")
            self.inp_numero_proveedor.clear()

    def _load_reglas_proveedor(self, proveedor_id: int):
        self.cmb_regla.blockSignals(True)
        self.cmb_regla.clear()
        self.cmb_regla.addItem("— Seleccionar regla —", None)

        try:
            self._reglas_cache = self.db.obtener_reglas_proveedor(proveedor_id)
            for r in self._reglas_cache:
                trigger = r.get("serie", "") or r.get("trigger", "")
                item_text = f"[ID:{r['id']}] {trigger}"
                self.cmb_regla.addItem(item_text, r)
        except Exception as e:
            log.error(f"Error cargando reglas: {e}")
            self._reglas_cache = []

        self.cmb_regla.blockSignals(False)

    def _on_regla_changed(self, idx):
        regla_data = self.cmb_regla.itemData(idx)
        if not regla_data:
            self._current_regla_id = None
            self.lbl_regla_id.setText("ID: —")
            self._clear()
            return

        self._current_regla_id = regla_data.get("id")
        self.lbl_regla_id.setText(f"ID: {self._current_regla_id}")

        self.inp_trigger.setText(regla_data.get("serie", ""))
        self.chk_cont_auto.setChecked(bool(regla_data.get("cont_automatica", 0)))
        self.inp_cuenta_gasto.setText(regla_data.get("cuenta_gasto", ""))
        self.inp_cta_proveedor.setText(regla_data.get("set_cuenta_proveedor", "400000"))
        self.inp_sub_proveedor.setText(regla_data.get("set_subcuenta_proveedor", ""))
        self.inp_subcuenta_gasto.setText(regla_data.get("set_subcuenta_gasto", ""))

        # Categoría
        cat = regla_data.get("categoria", "VARIOS")
        idx_cat = self.cmb_cat.findText(cat)
        if idx_cat >= 0:
            self.cmb_cat.setCurrentIndex(idx_cat)

        # Tipo de factura
        tipo = regla_data.get("tipo_factura", "") or regla_data.get("set_tipo_factura", "")
        if tipo:
            idx_tipo = self.cmb_tipo_factura.findText(tipo)
            if idx_tipo >= 0:
                self.cmb_tipo_factura.setCurrentIndex(idx_tipo)

        # Serie
        serie = regla_data.get("serie_factura", "") or regla_data.get("set_serie", "")
        if serie:
            idx_serie = self.cmb_serie.findText(serie)
            if idx_serie >= 0:
                self.cmb_serie.setCurrentIndex(idx_serie)

        # Tipo IVA de la regla (solo si el usuario no lo ha tocado explícitamente)
        tipo_iva_regla = regla_data.get("set_tipo_iva", 21) or 21
        if not getattr(self, "_tipo_iva_user_touched", False):
            try:
                tipo_iva_int = int(tipo_iva_regla)
                idx_iva = self.cmb_tipo_iva.findData(tipo_iva_int)
                if idx_iva >= 0:
                    self.cmb_tipo_iva.setCurrentIndex(idx_iva)
            except Exception:
                pass

        # ── Cargar plantilla OCR ──────────────────────────────────────────────
        try:
            proveedor_id = self.cmb_proveedor.currentData().get("id")
            plantillas   = self.db.obtener_plantillas_ocr(proveedor_id)

            # Buscar plantilla por nombre_regla > serie > coincidencia parcial > única
            trigger_val    = regla_data.get("nombre_regla") or regla_data.get("serie", "")
            nombre_plantilla = None
            for clave in [f"regla_{trigger_val}", f"regla_{trigger_val.strip()}"]:
                if clave in plantillas:
                    nombre_plantilla = clave
                    break
            if not nombre_plantilla:
                t_norm = trigger_val.lower().strip()
                for clave in plantillas:
                    if t_norm in clave.lower() or clave.lower().replace("regla_", "") in t_norm:
                        nombre_plantilla = clave
                        break
            if not nombre_plantilla and len(plantillas) == 1:
                nombre_plantilla = list(plantillas.keys())[0]

            if nombre_plantilla in plantillas:
                plantilla_data = plantillas[nombre_plantilla]
                coords         = plantilla_data.get("coords", {})
                textos         = coords.get("textos", {})

                # Mostrar textos de plantilla en val_labels
                # Campos únicos (nº factura, importes) solo si OCR no los tiene
                CAMPOS_UNICOS = {"numero_factura", "base_imponible", "iva", "total"}
                for campo, texto in textos.items():
                    if campo in self._val_labels:
                        ocr_val = self._ocr_auto.get(campo, "")
                        if not ocr_val:
                            self._val_labels[campo].setText(texto[:60] if texto else "—")
                        elif campo not in CAMPOS_UNICOS:
                            self._val_labels[campo].setText(texto[:60] if texto else "—")

                # Panel "Valores a procesar": nunca muestra textos de entrenamiento
                # para campos únicos — el re-OCR de zona los obtendrá al procesar
                self._ultima_plantilla_textos = {}
                self._actualizar_proc_labels({})

                # Cargar zonas en el canvas (rects de la plantilla)
                if "rects" in coords and self._canvas:
                    zonas = {}
                    for campo, rect in coords["rects"].items():
                        zonas[campo] = {
                            "rect_norm": rect,
                            "texto": textos.get(campo, ""),
                        }
                    self._canvas.set_zones(zonas)
                    self._campos_rect_norm = coords.get("rects", {})

                # Restaurar rotación de entrenamiento
                rot = coords.get("rot_entrenamiento", 0)
                if rot and self._canvas:
                    self._canvas._norm_rot = rot

                # Posiciones de marca de agua
                if coords.get("wm_datos") and self._canvas:
                    self._campos_rect_norm["wm_datos"] = coords["wm_datos"]
                    self._canvas._zones["wm_datos"] = {
                        "rect_norm": coords["wm_datos"], "texto": "DATOS WM"}
                if coords.get("wm_serie") and self._canvas:
                    self._campos_rect_norm["wm_serie"] = coords["wm_serie"]
                    self._canvas._zones["wm_serie"] = {
                        "rect_norm": coords["wm_serie"], "texto": "SERIE WM"}
                if (coords.get("wm_datos") or coords.get("wm_serie")) and self._canvas:
                    self._canvas._render()

                # Flags especiales
                if "es_gestoria" in coords:
                    self.chk_gestoria.setChecked(coords["es_gestoria"])
                    if coords["es_gestoria"] and "iva_gestoria" in coords:
                        self.inp_iva_gestoria.setText(coords["iva_gestoria"])
                        self._recalc_base_gestoria()

            else:
                # Sin plantilla entrenada: limpiar canvas y mostrar OCR puro
                self._ultima_plantilla_textos = {}
                self._actualizar_proc_labels({})

        except Exception as e:
            log.error(f"Error cargando plantilla: {e}")


    def set_canvas(self, canvas):
        self._canvas = canvas
        canvas.zone_selected.connect(self._on_zone)
        canvas.zone_removed.connect(self._on_zone_removed)

    def set_ocr_auto(self, ocr_data: dict):
        self._ocr_auto = ocr_data.copy()
        for campo, valor in ocr_data.items():
            if campo.startswith("_"):
                continue  # _raw_text no va a etiquetas visuales
            if campo in self._val_labels and valor:
                self._val_labels[campo].setText(str(valor)[:60] if valor else "—")
        # Actualizar campo fecha si el OCR detectó issue_date
        if hasattr(self, "inp_fecha_factura") and ocr_data.get("_issue_date"):
            try:
                from datetime import datetime as _dt
                d = ocr_data["_issue_date"]
                if isinstance(d, _dt):
                    self.inp_fecha_factura.setDate(QDate(d.year, d.month, d.day))
            except Exception:
                pass

        # Inicializar panel "Valores a procesar" con OCR como baseline
        self._actualizar_proc_labels({})

        # Si modo gestoría está activo y hay IVA guardado, recalcular base
        if getattr(self, "chk_gestoria", None) and self.chk_gestoria.isChecked():
            self._recalc_base_gestoria()

        # Sugerir tipo IVA desde OCR SOLO si el usuario no lo ha cambiado manualmente
        vat_pct = ocr_data.get("_vat_pct")
        if (vat_pct is not None and hasattr(self, "cmb_tipo_iva")
                and not getattr(self, "_tipo_iva_user_touched", False)):
            try:
                tipo_iva_ocr = int(round(float(vat_pct)))
                if tipo_iva_ocr in (0, 4, 10, 21):
                    idx = self.cmb_tipo_iva.findData(tipo_iva_ocr)
                    if idx >= 0:
                        self.cmb_tipo_iva.setCurrentIndex(idx)
                        log.debug("Tipo IVA sugerido por OCR: %d%%", tipo_iva_ocr)
            except Exception:
                pass

    def _actualizar_proc_labels(self, textos_plantilla: dict) -> None:
        """
        Actualiza el panel 'Valores a procesar' con prioridad correcta:
        1. OCR manual del usuario (_campos_texto)  → NARANJA (máxima prioridad)
        2. OCR automático                          → VERDE
        3. Vacío                                   → GRIS  (con tooltip informativo)

        NOTA: numero_factura, base_imponible, iva y total NUNCA muestran el texto
        de entrenamiento — son únicos por factura y se obtendrán del re-OCR de zona
        al procesar. Mostrarlos aquí confundiría con valores de otras facturas.
        """
        if not hasattr(self, "_proc_labels"):
            return
        _MA = ("font-size:12px;font-weight:bold;color:#7B341E;"
               "background:#FEEBC8;padding:4px 8px;border-radius:4px;"
               "border:1px solid #F6AD55;")
        _OC = ("font-size:12px;font-weight:bold;color:#276749;"
               "background:#F0FFF4;padding:4px 8px;border-radius:4px;"
               "border:1px solid #9AE6B4;")
        _EM = "font-size:12px;color:#A0AEC0;padding:4px 8px;border-radius:4px;"
        campos_manuales = getattr(self, "_campos_texto", {})
        for campo in ("numero_factura", "base_imponible", "iva", "total"):
            if campo not in self._proc_labels:
                continue
            lbl = self._proc_labels[campo]
            if campos_manuales.get(campo):
                # Máxima prioridad: marcado manualmente por el usuario en el visor
                lbl.setText(str(campos_manuales[campo])[:40])
                lbl.setStyleSheet(_MA)
                lbl.setToolTip("Valor marcado manualmente por el usuario")
            elif self._ocr_auto.get(campo):
                # OCR automático del PDF
                lbl.setText(str(self._ocr_auto[campo])[:40])
                lbl.setStyleSheet(_OC)
                lbl.setToolTip("Valor detectado por OCR automático")
            else:
                lbl.setText("—")
                lbl.setStyleSheet(_EM)
                if campo == "numero_factura":
                    lbl.setToolTip("Se leerá de la zona entrenada al archivar")
                else:
                    lbl.setToolTip("")

    def _on_zone(self, campo, texto, rect_norm):
        self._campos_texto[campo] = texto
        self._campos_rect_norm[campo] = rect_norm

        if campo in self._val_labels:
            self._val_labels[campo].setText(texto[:60] if texto else "⚠️ Sin texto")
            color = "#C53030" if not texto else ("#9F7AEA" if self.chk_gestoria.isChecked() and campo=="iva" else "#276749")
            self._val_labels[campo].setStyleSheet(f"color:{color};font-size:11px;font-weight:bold;background:#F7FAFC;padding:4px 8px;border-radius:4px;")

        # Actualizar panel "Valores a procesar" — el valor manual tiene prioridad máxima
        # Conservar los textos de plantilla ya cargados si los hay
        _plantilla_actual = getattr(self, "_ultima_plantilla_textos", {})
        self._actualizar_proc_labels(_plantilla_actual)

        # Cálculo para gestoría
        if self.chk_gestoria.isChecked() and campo == "iva" and texto:
            self.inp_iva_gestoria.setText(texto)
            # _recalc_base_gestoria se llamará automáticamente via textChanged signal

    def _on_zone_removed(self, campo):
        if campo in self._campos_texto:
            del self._campos_texto[campo]
        if campo in self._campos_rect_norm:
            del self._campos_rect_norm[campo]
        if campo in self._val_labels:
            if campo in self._ocr_auto and self._ocr_auto[campo]:
                self._val_labels[campo].setText(str(self._ocr_auto[campo])[:60])
            else:
                self._val_labels[campo].setText("—")
        
        if campo == "iva" and self.chk_gestoria.isChecked():
            self.inp_iva_gestoria.clear()
            self.lbl_base_calculada.setText("—")
            if "base_imponible" in self._val_labels:
                if "base_imponible" in self._ocr_auto:
                    self._val_labels["base_imponible"].setText(str(self._ocr_auto["base_imponible"])[:60])
                else:
                    self._val_labels["base_imponible"].setText("—")

    def _comprobar_trigger(self):
        """Valida el trigger contra el texto OCR disponible."""
        trigger = self.inp_trigger.text().strip()
        if not trigger:
            self.lbl_trigger_resultado.setText("⚠️ Escribe un trigger antes de comprobar")
            self.lbl_trigger_resultado.setStyleSheet("color:#C05621;font-size:10px;padding:2px 4px;")
            return

        # Prioridad: texto raw completo (toda la página), luego campos extraídos
        raw_text = self._ocr_auto.get("_raw_text", "")
        if not raw_text:
            raw_text = " ".join(str(v) for k, v in self._ocr_auto.items()
                                if v and not k.startswith("_"))
            raw_text += " " + " ".join(str(v) for v in self._campos_texto.values() if v)

        trigger_norm = _normalise_trigger(trigger)
        raw_norm = _normalise_trigger(raw_text)

        if trigger_norm and trigger_norm in raw_norm:
            self.lbl_trigger_resultado.setText(f"✅ Trigger '{trigger}' encontrado en el texto OCR")
            self.lbl_trigger_resultado.setStyleSheet(
                "color:#276749;font-size:10px;padding:2px 4px;font-weight:bold;background:#F0FFF4;border-radius:3px;")
        else:
            self.lbl_trigger_resultado.setText(
                f"❌ Trigger '{trigger}' NO encontrado en el texto OCR")
            self.lbl_trigger_resultado.setStyleSheet(
                "color:#C53030;font-size:10px;padding:2px 4px;font-weight:bold;background:#FFF5F5;border-radius:3px;")

    def _guardar_nueva(self):
        self._guardar(actualizar=False)

    def _actualizar_regla(self):
        if not self._current_regla_id:
            QMessageBox.warning(self, "Error", "Selecciona una regla para actualizar.")
            return
        self._guardar(actualizar=True)

    def _guardar(self, actualizar: bool = False):
        nombre = self.inp_prov_nombre.text().strip()
        trigger = self.inp_trigger.text().strip()
        cuenta_gasto = self.inp_cuenta_gasto.text().strip()
        cta_prov = self.inp_cta_proveedor.text().strip() or "400000"
        sub_prov = self.inp_sub_proveedor.text().strip()
        sub_gasto = self.inp_subcuenta_gasto.text().strip()
        cat = self.cmb_cat.currentText()
        tipo_factura = self.cmb_tipo_factura.currentText()
        serie = self.cmb_serie.currentText()
        variable = self.chk_variable.isChecked()
        es_rectificativa = self.chk_rectificativa.isChecked()
        es_gestoria = self.chk_gestoria.isChecked()
        iva_gestoria = self.inp_iva_gestoria.text().strip() if es_gestoria else ""
        cont_automatica = self.chk_cont_auto.isChecked()

        if not trigger:
            QMessageBox.warning(self, "Error", "El trigger es obligatorio")
            return
        if not cuenta_gasto:
            QMessageBox.warning(self, "Error", "La cuenta de gasto es obligatoria")
            return

        prov_data = self.cmb_proveedor.currentData()
        proveedor_id = prov_data["id"] if prov_data else None

        # --- Obtener el CIF del proveedor (priorizando zona manual) ---
        cif_proveedor = ""
        
        # 1. Prioridad: zona manual de CIF
        if "cif_nif" in self._campos_texto and self._campos_texto["cif_nif"]:
            cif_proveedor = self._campos_texto["cif_nif"]
            log.info(f"CIF desde zona manual: {cif_proveedor}")
        
        # 2. Si no hay zona manual, usar CIF del proveedor existente
        elif prov_data and prov_data.get("cif_nif"):
            cif_proveedor = prov_data.get("cif_nif", "")
            log.info(f"CIF desde proveedor existente: {cif_proveedor}")
        
        # 3. Fallback a OCR
        else:
            cif_proveedor = self._ocr_auto.get("cif_nif", "")
            log.info(f"CIF desde OCR: {cif_proveedor}")
        # -----------------------------------

        num_proveedor_input = self.inp_numero_proveedor.text().strip() or "PRV"
        if not proveedor_id and nombre:
            proveedor_id = self.db.insertar_proveedor({
                "nombre": nombre or trigger,
                "numero_proveedor": num_proveedor_input,
                "cuenta_gasto": cuenta_gasto,
                "categoria": cat,
                "tipo_factura": tipo_factura,
                "serie": serie,
                "cuenta_proveedor": cta_prov,
                "subcuenta_proveedor": sub_prov,
                "subcuenta_gasto": sub_gasto,
                "cif_nif": cif_proveedor,
            })
        elif proveedor_id and num_proveedor_input and num_proveedor_input != "PRV":
            # Actualizar número de proveedor si el usuario lo modificó
            try:
                self.db.actualizar_proveedor(proveedor_id, numero_proveedor=num_proveedor_input)
            except Exception as _e:
                log.warning("No se pudo actualizar numero_proveedor: %s", _e)
        elif not proveedor_id:
            QMessageBox.warning(self, "Error", "Selecciona o crea un proveedor")
            return

        if not proveedor_id:
            return

        # --- AÑADIR EL CIF AL DICCIONARIO DE DATOS DE LA REGLA ---
        datos_regla = {
            "proveedor_id": proveedor_id,
            "nombre_regla": trigger,
            "serie": trigger,
            "match_cif": cif_proveedor,
            "cuenta_gasto": cuenta_gasto,
            "categoria": cat,
            "tipo_factura": tipo_factura,
            "serie_factura": serie,
            "set_cuenta_proveedor": cta_prov,
            "set_subcuenta_proveedor": sub_prov,
            "set_subcuenta_gasto": sub_gasto,
            "set_categoria": cat,
            "set_tipo_factura": tipo_factura,
            "set_serie": serie,
            "cont_automatica": 1 if cont_automatica else 0,
            "set_tipo_iva": self.cmb_tipo_iva.currentData() if hasattr(self, "cmb_tipo_iva") else 21,
        }
        # --------------------------------------------------------

        if actualizar and self._current_regla_id:
            datos_regla["id"] = self._current_regla_id
            self.db.guardar_regla_determinista(datos_regla)
            QMessageBox.information(self, "OK", f"Regla ID {self._current_regla_id} actualizada")
        else:
            nueva_id = self.db.guardar_regla_determinista(datos_regla)
            QMessageBox.information(self, "OK", f"Nueva regla creada con ID {nueva_id}")

        # BUG-FIX: invalidar la caché del motor de reglas para que la nueva
        # regla se cargue en el próximo proceso sin reiniciar la aplicación
        try:
            from classify.classifier import InvoiceClassifier
            InvoiceClassifier(db=self.db).invalidate_engine()
            log.info("Motor de reglas invalidado tras guardar regla")
        except Exception as _e:
            log.warning("No se pudo invalidar motor de reglas: %s", _e)

        self.db.marcar_proveedor_variable(proveedor_id, variable)

        # --- Guardar patrones de reconocimiento silencioso ---
        try:
            # Guardar el CIF como patrón de alta confianza
            if cif_proveedor and len(cif_proveedor) > 5:
                self.db.guardar_patron_proveedor(
                    proveedor_id, 
                    cif_proveedor, 
                    tipo="texto", 
                    confianza=0.95
                )
                log.info(f"Patrón CIF guardado: {cif_proveedor} para proveedor {proveedor_id}")
            
            # Guardar el trigger como patrón
            if trigger and len(trigger) > 3:
                self.db.guardar_patron_proveedor(
                    proveedor_id,
                    trigger,
                    tipo="texto",
                    confianza=0.85
                )
                log.info(f"Patrón trigger guardado: {trigger} para proveedor {proveedor_id}")
            
            # Guardar texto de zonas seleccionadas como patrones
            for campo, texto in self._campos_texto.items():
                if texto and len(texto) > 4 and campo not in ["cif_nif", "trigger"]:
                    self.db.guardar_patron_proveedor(
                        proveedor_id,
                        texto[:50],
                        tipo="texto",
                        confianza=0.6
                    )
                    log.info(f"Patrón {campo} guardado: {texto[:50]} para proveedor {proveedor_id}")
        except Exception as e:
            log.error(f"Error guardando patrones: {e}")
        # ----------------------------------------------------

        rot = getattr(self._canvas, "_norm_rot", 0) if self._canvas else 0
        # Extraer posiciones WM de los rects (separadas de los campos OCR)
        _wm_datos = self._campos_rect_norm.get("wm_datos")
        _wm_serie = self._campos_rect_norm.get("wm_serie")
        _rects_ocr = {k: v for k, v in self._campos_rect_norm.items()
                      if k not in ("wm_datos", "wm_serie")}
        _textos_ocr = {k: v for k, v in self._campos_texto.items()
                       if k not in ("wm_datos", "wm_serie")}
        campos_json = json.dumps({
            "textos": _textos_ocr,
            "rects": _rects_ocr,
            "rot_entrenamiento": rot,
            "es_rectificativa": es_rectificativa,
            "es_gestoria": es_gestoria,
            "iva_gestoria": iva_gestoria,
            "wm_datos": _wm_datos,
            "wm_serie": _wm_serie,
        })
        nombre_plantilla = f"regla_{trigger}"
        self.db.guardar_plantilla_ocr(proveedor_id, nombre_plantilla, campos_json)

        self._load_reglas_proveedor(proveedor_id)
        # Limpiar zonas tras guardar para evitar que _campos_texto contamine la siguiente regla
        self._clear()

    def _clear_wm_positions(self):
        """Elimina las zonas de posición de marca de agua."""
        for campo in ("wm_datos", "wm_serie"):
            if campo in self._campos_texto:
                del self._campos_texto[campo]
            if campo in self._campos_rect_norm:
                del self._campos_rect_norm[campo]
        if self._canvas:
            # Redibujar zonas sin las WM
            zonas = {k: v for k, v in self._canvas._zones.items()
                     if k not in ("wm_datos", "wm_serie")}
            self._canvas.set_zones(zonas)

    def _clear(self):
        self._campos_texto.clear()
        self._campos_rect_norm.clear()
        self.inp_iva_gestoria.clear()
        self.lbl_base_calculada.setText("—")
        for campo, lbl in self._val_labels.items():
            if campo in self._ocr_auto and self._ocr_auto[campo]:
                lbl.setText(str(self._ocr_auto[campo])[:60])
            else:
                lbl.setText("—")
        if self._canvas:
            self._canvas.clear_all_zones()


# ═══════════════════════════════════════════════════════════════════════════════
# Diálogo principal
# ═══════════════════════════════════════════════════════════════════════════════

class VisorPDFCompleto(QDialog):
    def __init__(self, ruta_pdf: str, datos_ocr: dict = None,
                 db=None, modo_entrenamiento: bool = False,
                 proveedor_id: int = None, parent=None):
        super().__init__(parent)
        self.ruta_pdf = ruta_pdf
        self.datos_ocr = datos_ocr or {}
        self.modo_entr = modo_entrenamiento
        self.proveedor_id = proveedor_id
        self.resultado = None
        self._doc = None
        self._pagina = 0
        self._total_pags = 1
        self._user_rot = {}

        try:
            from database.manager import DatabaseManager
            self.db = db or DatabaseManager()
        except Exception:
            self.db = None

        self.setWindowTitle(f"{'🎓 Entrenador' if modo_entrenamiento else '📄 Visor'} — {os.path.basename(ruta_pdf)}")
        self.setMinimumSize(1400, 860)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()
        self._abrir_pdf()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(self._toolbar())

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.addWidget(self._pdf_panel())
        if self.modo_entr or self.db:
            self._splitter.addWidget(self._right_panel())
            self._splitter.setSizes([int(self.width() * 0.65), int(self.width() * 0.35)])

        lay.addWidget(self._splitter, 1)

        _footer = QHBoxLayout()
        self._status_lbl = QLabel("Listo")
        self._status_lbl.setStyleSheet("color:#4A5568;font-size:10px;")
        _footer.addStretch()
        _footer.addWidget(self._status_lbl)
        _footer_w = QWidget()
        _footer_w.setLayout(_footer)
        lay.addWidget(_footer_w)

    def _toolbar(self):
        tb = QHBoxLayout()

        self._btn_prev = QPushButton("◀ Anterior")
        self._btn_prev.setStyleSheet(BTN_S)
        self._btn_prev.clicked.connect(self._prev_page)

        self._lbl_page = QLabel("1 / 1")
        self._lbl_page.setFixedWidth(70)
        self._lbl_page.setAlignment(Qt.AlignCenter)

        self._btn_next = QPushButton("Siguiente ▶")
        self._btn_next.setStyleSheet(BTN_S)
        self._btn_next.clicked.connect(self._next_page)

        self._sld_zoom = QSlider(Qt.Horizontal)
        self._sld_zoom.setRange(30, 500)
        self._sld_zoom.setValue(150)
        self._sld_zoom.setFixedWidth(130)
        self._sld_zoom.valueChanged.connect(self._on_zoom)
        self._lbl_zoom = QLabel("150%")

        self._btn_select = QPushButton("✏️ Seleccionar")
        self._btn_select.setCheckable(True)
        self._btn_select.setChecked(True)
        self._btn_select.setStyleSheet(BTN_P)
        self._btn_select.clicked.connect(lambda: self._set_mode("select"))

        self._btn_hand = QPushButton("✋ Mano")
        self._btn_hand.setCheckable(True)
        self._btn_hand.setStyleSheet(BTN_S)
        self._btn_hand.clicked.connect(lambda: self._set_mode("hand"))

        btn_rot_l = QPushButton("↺ Girar")
        btn_rot_l.setStyleSheet(BTN_S)
        btn_rot_l.clicked.connect(lambda: self._rotate_view(-90))

        btn_rot_r = QPushButton("↻ Girar")
        btn_rot_r.setStyleSheet(BTN_S)
        btn_rot_r.clicked.connect(lambda: self._rotate_view(90))

        for w in [self._btn_prev, self._lbl_page, self._btn_next,
                  self._sld_zoom, self._lbl_zoom, self._btn_select,
                  self._btn_hand, btn_rot_l, btn_rot_r]:
            tb.addWidget(w)
        tb.addStretch()

        if self.modo_entr:
            b = QPushButton("✅ Guardar")
            b.setStyleSheet(BTN_SUCCESS)
            b.clicked.connect(self.accept)
            tb.addWidget(b)
        else:
            b = QPushButton("✅ Archivar")
            b.setStyleSheet(BTN_SUCCESS)
            b.clicked.connect(self._archivar)
            tb.addWidget(b)

        bc = QPushButton("✖ Cerrar")
        bc.setStyleSheet(BTN_DANGER)
        bc.clicked.connect(self.reject)
        tb.addWidget(bc)
        return tb

    def _pdf_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea{background:#525252;border:none;}")
        self._canvas = _PDFCanvas()
        self._scroll.setWidget(self._canvas)
        lay.addWidget(self._scroll)

        hint = QLabel("💡 Ctrl+Rueda=Zoom · Botón derecho=eliminar zona")
        hint.setStyleSheet("color:#A0AEC0;font-size:9px;")
        lay.addWidget(hint)
        return w

    def _right_panel(self):
        # Contenedor exterior con scroll vertical
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(440)
        scroll.setMaximumWidth(620)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#F7FAFC;}"
            "QScrollBar:vertical{width:8px;background:#EDF2F7;border-radius:4px;}"
            "QScrollBar::handle:vertical{background:#CBD5E0;border-radius:4px;min-height:20px;}"
            "QScrollBar::handle:vertical:hover{background:#A0AEC0;}"
        )

        if self.db:
            self._panel_reglas = _PanelReglas(self.db)
            self._panel_reglas.set_canvas(self._canvas)
            scroll.setWidget(self._panel_reglas)
        else:
            placeholder = QWidget()
            QVBoxLayout(placeholder).addWidget(QLabel("Base de datos no disponible"))
            scroll.setWidget(placeholder)

        return scroll

    def _set_mode(self, mode):
        self._canvas.set_mode(mode)
        self._btn_select.setChecked(mode == "select")
        self._btn_hand.setChecked(mode == "hand")

    def _abrir_pdf(self):
        if not PYMUPDF_OK:
            self._status("⚠️ PyMuPDF no instalado")
            return

        if not self.ruta_pdf or not os.path.exists(self.ruta_pdf):
            QMessageBox.warning(self, "Error", f"No existe el archivo:\n{self.ruta_pdf}")
            return

        # FIX-REGRESION-2/3: resetear flag de IVA tocado por usuario al cargar nuevo PDF
        if hasattr(self, "_panel_reglas") and hasattr(self._panel_reglas, "_tipo_iva_user_touched"):
            self._panel_reglas._tipo_iva_user_touched = False

        try:
            self._doc = fitz.open(self.ruta_pdf)
            self._total_pags = len(self._doc)
            self._render_page(0)

            if self._doc and hasattr(self, "_panel_reglas"):
                # Leer todas las páginas: campos financieros de la última que los tenga
                ocr_merged = {}
                for _pidx in range(len(self._doc)):
                    _pd = ocr_pagina_completa(self._doc[_pidx])
                    for _k, _v in _pd.items():
                        if not _v:
                            continue
                        if _k in ("base_imponible", "iva", "total"):
                            ocr_merged[_k] = _v  # última página con valor gana
                        elif _k not in ocr_merged or not ocr_merged[_k]:
                            ocr_merged[_k] = _v  # primera página con valor gana
                self._panel_reglas.set_ocr_auto(ocr_merged)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir el PDF:\n{e}")

    def _render_page(self, idx):
        if not self._doc:
            return
        page = self._doc[idx]
        zoom = self._sld_zoom.value() / 100.0
        user_rot = self._user_rot.get(idx, 0)
        # PyMuPDF ya aplica page.rotation en get_pixmap - no sumar de nuevo (doble rotación landscape)
        mat = fitz.Matrix(zoom * 2, zoom * 2).prerotate(user_rot % 360)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pm = QPixmap.fromImage(img)
        self._canvas.set_page(pm, page_ref=page, norm_rot=user_rot)
        self._pagina = idx
        self._lbl_page.setText(f"{idx + 1}/{self._total_pags}")

    def _rotate_view(self, degrees):
        cur = self._user_rot.get(self._pagina, 0)
        self._user_rot[self._pagina] = (cur + degrees) % 360
        self._render_page(self._pagina)

    def _prev_page(self):
        if self._pagina > 0:
            self._render_page(self._pagina - 1)

    def _next_page(self):
        if self._pagina < self._total_pags - 1:
            self._render_page(self._pagina + 1)

    def _on_zoom(self, v):
        self._lbl_zoom.setText(f"{v}%")
        if self._doc:
            self._render_page(self._pagina)

    def _archivar(self):
        """Procesa realmente el PDF usando el clasificador existente."""
        from core.models import Invoice
        from classify.classifier import InvoiceClassifier
        from datetime import datetime as _dt, date as _date

        inv = Invoice(file_path=self.ruta_pdf,
                      file_name=os.path.basename(self.ruta_pdf),
                      source="manual")

        # Propagar datos OCR del visor al objeto Invoice antes de procesar
        if hasattr(self, "_panel_reglas"):
            ocr_auto   = self._panel_reglas._ocr_auto or {}
            ocr_manual = self._panel_reglas._campos_texto or {}

            # Número de factura: manual tiene prioridad sobre automático
            inv.numero_factura_manual = (
                ocr_manual.get("numero_factura") or
                ocr_auto.get("numero_factura", "")
            )

            # ── CAMPOS ECONÓMICOS MANUALES (BUG-FIX: antes nunca se pasaban) ──
            # Los valores que el usuario ha remarcado en el visor deben llegar
            # al Invoice para que el clasificador los respete y no los pise.
            from core.utils import parse_es_float_safe as _pfs
            _base = _pfs(ocr_manual.get("base_imponible", ""), 0.0)
            _iva  = _pfs(ocr_manual.get("iva", ""), 0.0)
            _tot  = _pfs(ocr_manual.get("total", ""), 0.0)

            # ── Modo Gestoría ────────────────────────────────────────────────
            # En facturas de gestoría el IVA que marca el usuario es solo el de
            # los honorarios. La base real = Total - IVA_honorarios.
            # Si el usuario marcó el IVA y hay total disponible, recalcular base.
            if hasattr(self, "chk_gestoria") and self.chk_gestoria.isChecked():
                _iva_gest = _pfs(self.inp_iva_gestoria.text().strip(), 0.0)
                if _iva_gest > 0:
                    # IVA viene de la zona marcada por el usuario en modo gestoría
                    _iva = _iva_gest
                    # Total: primero manual, luego OCR
                    _tot_gest = _tot or _pfs(ocr_auto.get("total", ""), 0.0)
                    if _tot_gest > 0:
                        _base = round(_tot_gest - _iva_gest, 2)
                        _tot  = _tot_gest
                        log.info("Gestoría: base calculada = %s (total=%s - iva=%s)",
                                 _base, _tot_gest, _iva_gest)
            # ────────────────────────────────────────────────────────────────

            if _base: inv.fields.base_amount  = _base
            if _iva:  inv.fields.vat_amount   = _iva
            if _tot:  inv.fields.total_amount = _tot
            if ocr_manual.get("cif_nif"):
                inv.fields.cif_nif = ocr_manual["cif_nif"]

            # Marcar como fijados manualmente para que el clasificador
            # no los sobrescriba con la plantilla automática
            inv._manual_base_amount  = _base if _base else None
            inv._manual_vat_amount   = _iva  if _iva  else None
            inv._manual_total_amount = _tot  if _tot  else None

            # ── Retención IRPF ───────────────────────────────────────────────
            if hasattr(self, "chk_retencion") and self.chk_retencion.isChecked():
                ret_pct = _pfs(self.inp_ret_pct.text().strip(), 0.0)
                ret_imp = _pfs(self.inp_ret_importe.text().strip(), 0.0)
                if ret_pct or ret_imp:
                    inv.fields.retention_pct    = ret_pct
                    inv.fields.retention_amount = ret_imp
                    log.info("Retención IRPF manual: %s%% = %s€", ret_pct, ret_imp)

            # ── Tipo IVA manual ──────────────────────────────────────────────
            # FIX-REGRESION-2: solo propagar como "manual" si el usuario lo cambió
            # explícitamente (activated signal). Si lo cambió la regla u OCR,
            # dejamos que el clasificador use la prioridad normal (regla > OCR).
            if hasattr(self, "cmb_tipo_iva") and getattr(self, "_tipo_iva_user_touched", False):
                inv._tipo_iva_manual = self.cmb_tipo_iva.currentData()
                if inv._tipo_iva_manual == 0:
                    inv.fields.vat_amount = 0.0
                    inv.fields.vat_pct    = 0.0
                elif inv._tipo_iva_manual and inv._tipo_iva_manual != 21:
                    inv.fields.vat_pct  = float(inv._tipo_iva_manual)
                    inv.fields.tipo_iva = inv._tipo_iva_manual

            # ── Reparto de cuentas ───────────────────────────────────────────
            if hasattr(self, "chk_reparto") and self.chk_reparto.isChecked():
                reparto = self._get_reparto_cuentas()
                if reparto:
                    inv._reparto_cuentas = reparto
                    log.info("Reparto de cuentas manual: %s", reparto)

            log.info(
                "Campos manuales propagados → base=%s iva=%s total=%s cif=%s",
                _base or "—", _iva or "—", _tot or "—",
                ocr_manual.get("cif_nif", "—")
            )

            # Posiciones de marca de agua guardadas en la plantilla
            rects = self._panel_reglas._campos_rect_norm
            if "wm_datos" in rects and rects["wm_datos"]:
                inv._wm_pos_datos = tuple(rects["wm_datos"])
            if "wm_serie" in rects and rects["wm_serie"]:
                inv._wm_pos_serie = tuple(rects["wm_serie"])

        # Fecha de factura desde el campo editable del visor
        fecha_factura = None
        if hasattr(self, "inp_fecha_factura"):
            qd = self.inp_fecha_factura.date()
            fecha_factura = _dt(qd.year(), qd.month(), qd.day())

        # Detectar discrepancia de mes
        hoy = _dt.now()
        if fecha_factura:
            mismo_mes = (fecha_factura.year == hoy.year and
                         fecha_factura.month == hoy.month)
            if not mismo_mes:
                from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
                dlg = QDialog(self)
                dlg.setWindowTitle("📅 Discrepancia de mes")
                dlg.setMinimumWidth(380)
                lay = QVBoxLayout(dlg)
                lay.setSpacing(12)
                msg = QLabel(
                    f"La fecha de la factura es <b>{fecha_factura.strftime('%d/%m/%Y')}</b><br>"
                    f"pero estás procesando en <b>{hoy.strftime('%B %Y')}</b>.<br><br>"
                    "¿En qué mes quieres contabilizarla?"
                )
                msg.setWordWrap(True)
                msg.setStyleSheet("font-size:12px;padding:4px;")
                lay.addWidget(msg)
                btn_row = QHBoxLayout()
                btn_factura = QPushButton(f"📄 Mes factura ({fecha_factura.strftime('%m/%Y')})")
                btn_factura.setStyleSheet("QPushButton{background:#2B6CB0;color:white;border-radius:4px;"
                                          "padding:8px 14px;font-weight:bold;}QPushButton:hover{background:#1F4E79;}")
                btn_descarga = QPushButton(f"📥 Mes descarga ({hoy.strftime('%m/%Y')})")
                btn_descarga.setStyleSheet("QPushButton{background:#276749;color:white;border-radius:4px;"
                                           "padding:8px 14px;font-weight:bold;}QPushButton:hover{background:#1A4731;}")
                btn_factura.clicked.connect(lambda: dlg.done(1))
                btn_descarga.clicked.connect(lambda: dlg.done(2))
                btn_row.addWidget(btn_factura)
                btn_row.addWidget(btn_descarga)
                lay.addLayout(btn_row)
                resp = dlg.exec_()
                # resp=1 → contabilizar en mes factura, resp=2 → mes descarga
                inv._fecha_contabilizacion = (
                    hoy.strftime("%Y-%m-%d") if resp == 2 else fecha_factura.strftime("%Y-%m-%d")
                )
            else:
                inv._fecha_contabilizacion = fecha_factura.strftime("%Y-%m-%d")

            inv.fields.issue_date = fecha_factura

        try:
            classifier = InvoiceClassifier(db=self.db)
            classifier.process(inv)
        except Exception as exc:
            log.error("Error en clasificación desde visor: %s", exc)
            QMessageBox.warning(self, "Error procesando",
                                f"El procesamiento falló:\n{exc}\n\n"
                                "La factura se marcará para revisión manual.")

        from core.models import InvoiceStatus
        self.resultado = {
            "numero_factura": getattr(inv.fields, "invoice_number", "") or "",
            "cif_nif":        getattr(inv.fields, "cif_nif", "") or "",
            "status":         inv.status.value if inv.status else "unknown",
            "final_path":     inv.final_path or "",
        }
        self.accept()

    def _status(self, msg):
        if hasattr(self, "_status_lbl"):
            self._status_lbl.setText(msg)


# ── API pública ────────────────────────────────────────────────────────

def solicitar_datos_proveedor_manual(parent_widget, ruta_pdf: str, datos_autodetectados: dict) -> "dict | None":
    try:
        from database.manager import DatabaseManager
        db = DatabaseManager()
    except Exception:
        db = None
    dlg = VisorPDFCompleto(
        ruta_pdf=ruta_pdf,
        datos_ocr=datos_autodetectados,
        db=db,
        modo_entrenamiento=False,
        parent=parent_widget,
    )
    return dlg.resultado if dlg.exec_() == QDialog.Accepted else None

def abrir_visor_entrenamiento(parent_widget, ruta_pdf: str, proveedor_id: int = None) -> bool:
    try:
        from database.manager import DatabaseManager
        db = DatabaseManager()
    except Exception:
        db = None
    dlg = VisorPDFCompleto(
        ruta_pdf=ruta_pdf,
        db=db,
        modo_entrenamiento=True,
        proveedor_id=proveedor_id,
        parent=parent_widget,
    )
    return dlg.exec_() == QDialog.Accepted