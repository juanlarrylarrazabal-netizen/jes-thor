# -*- coding: utf-8 -*-
"""
ventana_proveedor.py — Ficha de proveedor con los 7 campos obligatorios.

Campos: CIF, RAZÓN SOCIAL, CUENTA/SUBCUENTA PROVEEDOR, CUENTA/SUBCUENTA GASTO,
        SERIE, TIPO FACTURA, CATEGORÍA
"""
from __future__ import annotations
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt

BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#E2E8F0;}")
INP   = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
         "padding:5px 8px;background:white;}QLineEdit:focus{border:1px solid #3182CE;}")
CMB   = ("QComboBox{border:1px solid #CBD5E0;border-radius:4px;padding:5px 8px;"
         "background:white;}QComboBox:focus{border:1px solid #3182CE;}")


def _get_categorias():
    try:
        from core.config_loader import get_config
        cats = get_config().categories
        if cats:
            return cats
    except Exception:
        pass
    try:
        from config import CATEGORIAS
        return CATEGORIAS
    except Exception:
        return ["COMERCIAL Y POSTVENTA EXTERNAS", "COMUNES EXTERNOS", "GESTORIA", "SEAT", "VARIOS"]


def _get_tipos_factura(db=None):
    if db:
        try:
            tipos = db.obtener_tipos_factura()
            if tipos:
                return [t.get("abreviatura", t.get("nombre", "")) for t in tipos]
        except Exception:
            pass
    return ["FACT", "RECT", "ALB", "NC", "NA", "PRES"]


class VentanaProveedor(QDialog):
    """
    Ficha de proveedor con los 7 campos obligatorios:
    CIF, RAZÓN SOCIAL, CUENTA/SUBCUENTA (PROVEEDOR), CUENTA/SUBCUENTA (GASTO),
    SERIE, TIPO FACTURA, CATEGORÍA.
    """
    def __init__(self, datos_detectados=None, db=None, parent=None):
        super().__init__(parent)
        self.datos_detectados = datos_detectados or {}
        self.db = db
        self.resultado = None
        self.setWindowTitle("Configurar Proveedor")
        self.setMinimumWidth(480)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        lbl = QLabel("Completa los datos del proveedor.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#2B6CB0;font-size:11px;")
        lay.addWidget(lbl)

        box = QGroupBox("Datos del Proveedor")
        box.setStyleSheet("QGroupBox{font-weight:bold;border:1px solid #CBD5E0;"
                          "border-radius:6px;margin-top:8px;padding-top:12px;}")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(9)

        def inp(val="", ph=""):
            e = QLineEdit(str(val or ""))
            e.setPlaceholderText(ph)
            e.setStyleSheet(INP)
            e.setFixedHeight(32)
            return e

        # 1. CIF
        self.e_cif = inp(self.datos_detectados.get("cif_nif", ""), "B12345678 / 12345678A")
        form.addRow("CIF / NIF *:", self.e_cif)

        # 2. RAZÓN SOCIAL
        self.e_razon = inp(
            self.datos_detectados.get("razon_social", "") or
            self.datos_detectados.get("nombre", ""),
            "Razón social (nombre legal)")
        form.addRow("Razón Social *:", self.e_razon)

        # 3. CUENTA / SUBCUENTA (PROVEEDOR)
        cta_prov_lay = QHBoxLayout()
        self.e_cuenta_prov = inp(self.datos_detectados.get("cuenta_proveedor", "400000"), "400000 / 410000")
        self.e_subcuenta_prov = inp(self.datos_detectados.get("subcuenta_proveedor", ""), "Subcuenta (opcional)")
        self.e_cuenta_prov.setFixedWidth(120)
        cta_prov_lay.addWidget(self.e_cuenta_prov)
        cta_prov_lay.addWidget(QLabel("/"))
        cta_prov_lay.addWidget(self.e_subcuenta_prov)
        form.addRow("Cta/Sub Proveedor:", cta_prov_lay)

        # 4. CUENTA / SUBCUENTA (GASTO)
        cta_gasto_lay = QHBoxLayout()
        self.e_cuenta_gasto = inp(self.datos_detectados.get("cuenta_gasto", ""), "628000 / 600000")
        self.e_subcuenta_gasto = inp(self.datos_detectados.get("subcuenta_gasto", ""), "Subcuenta (opcional)")
        self.e_cuenta_gasto.setFixedWidth(120)
        cta_gasto_lay.addWidget(self.e_cuenta_gasto)
        cta_gasto_lay.addWidget(QLabel("/"))
        cta_gasto_lay.addWidget(self.e_subcuenta_gasto)
        form.addRow("Cta/Sub Gasto:", cta_gasto_lay)

        # 5. SERIE
        self.e_serie = inp(self.datos_detectados.get("serie", ""), "A, B, V…")
        form.addRow("Serie:", self.e_serie)

        # 6. TIPO FACTURA
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.setStyleSheet(CMB)
        self.cmb_tipo.setFixedHeight(32)
        for t in _get_tipos_factura(self.db):
            self.cmb_tipo.addItem(t)
        tipo_actual = self.datos_detectados.get("tipo_factura", "")
        if tipo_actual:
            idx = self.cmb_tipo.findText(tipo_actual)
            if idx >= 0:
                self.cmb_tipo.setCurrentIndex(idx)
        form.addRow("Tipo Factura:", self.cmb_tipo)

        # 7. CATEGORÍA
        self.cmb_cat = QComboBox()
        self.cmb_cat.setStyleSheet(CMB)
        self.cmb_cat.setFixedHeight(32)
        for cat in _get_categorias():
            self.cmb_cat.addItem(cat)
        cat_actual = self.datos_detectados.get("categoria", "")
        if cat_actual:
            idx = self.cmb_cat.findText(cat_actual)
            if idx >= 0:
                self.cmb_cat.setCurrentIndex(idx)
        form.addRow("Categoría:", self.cmb_cat)

        lay.addWidget(box)

        bar = QHBoxLayout()
        bar.addStretch()
        btn_cancel = QPushButton("❌ Cancelar")
        btn_cancel.setStyleSheet(BTN_S)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("💾 Guardar")
        btn_ok.setStyleSheet(BTN_P)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._guardar)
        bar.addWidget(btn_cancel)
        bar.addWidget(btn_ok)
        lay.addLayout(bar)

    def _guardar(self):
        cif    = self.e_cif.text().strip()
        razon  = self.e_razon.text().strip()
        if not razon:
            QMessageBox.warning(self, "Dato obligatorio", "La Razón Social es obligatoria.")
            return
        self.resultado = {
            # Compat: 'nombre' sigue siendo la clave interna; razon_social = nombre legal
            "nombre":              razon,
            "razon_social":        razon,
            "numero_proveedor":    cif or "S/C",
            "cif_nif":             cif,
            "cuenta_proveedor":    self.e_cuenta_prov.text().strip() or "400000",
            "subcuenta_proveedor": self.e_subcuenta_prov.text().strip(),
            "cuenta_gasto":        self.e_cuenta_gasto.text().strip(),
            "subcuenta_gasto":     self.e_subcuenta_gasto.text().strip(),
            "serie":               self.e_serie.text().strip(),
            "tipo_factura":        self.cmb_tipo.currentText(),
            "categoria":           self.cmb_cat.currentText(),
        }
        self.accept()


def solicitar_datos_proveedor(parent_widget, datos_detectados: dict, db=None) -> dict | None:
    dlg = VentanaProveedor(datos_detectados=datos_detectados, db=db, parent=parent_widget)
    if dlg.exec_() == QDialog.Accepted:
        return dlg.resultado
    return None
