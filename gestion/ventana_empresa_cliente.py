# -*- coding: utf-8 -*-
"""
ventana_empresa_cliente.py — PyQt5 nativo.
Diálogo para configurar los datos de la empresa cliente (la empresa del usuario).
Exporta: abrir_configuracion_empresa(parent_widget=None)
"""
from __future__ import annotations
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QMessageBox
)
from PyQt5.QtCore import Qt

BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#E2E8F0;}")
INP   = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
         "padding:5px 8px;background:white;}QLineEdit:focus{border:1px solid #3182CE;}")


class VentanaEmpresaCliente(QDialog):
    """Configura razón social, CIF, dirección y palabras clave de tu empresa."""
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        from database import DatabaseManager
        self.db = db or DatabaseManager()
        self.setWindowTitle("⚙️  Configurar Mi Empresa (Cliente)")
        self.setMinimumWidth(500)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.datos = self.db.get_empresa_cliente() or {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)

        titulo = QLabel("⚙️  CONFIGURAR MI EMPRESA")
        titulo.setStyleSheet("font-size:14px;font-weight:bold;color:#1F4E79;")
        lay.addWidget(titulo)

        info = QLabel("Introduce los datos de TU empresa para evitar que el motor OCR "
                      "la confunda con un proveedor.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#2B6CB0;font-size:10px;")
        lay.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        def inp(key, placeholder=""):
            e = QLineEdit(str(self.datos.get(key) or ""))
            e.setPlaceholderText(placeholder)
            e.setStyleSheet(INP)
            e.setFixedHeight(32)
            return e

        self.e_razon    = inp("razon_social", "Nombre o razón social")
        self.e_cif      = inp("cif",          "CIF / NIF")
        self.e_dir      = inp("direccion",    "Dirección completa")
        self.e_palabras = inp("palabras_clave_str", "ej: MIEMPRESA, GRUPO MI, MI S.L.")

        # Convertir lista a string para edición
        palabras = self.datos.get("palabras_clave", [])
        if isinstance(palabras, list):
            self.e_palabras.setText(", ".join(palabras))

        for lbl, w in [("Razón Social:", self.e_razon),
                       ("CIF/NIF:",      self.e_cif),
                       ("Dirección:",    self.e_dir),
                       ("Palabras clave\n(separadas por coma):", self.e_palabras)]:
            form.addRow(lbl, w)
        lay.addLayout(form)

        bar = QHBoxLayout()
        bar.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(BTN_S)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("💾  Guardar")
        btn_ok.setStyleSheet(BTN_P)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._guardar)
        bar.addWidget(btn_cancel)
        bar.addWidget(btn_ok)
        lay.addLayout(bar)

    def _guardar(self):
        razon    = self.e_razon.text().strip()
        cif      = self.e_cif.text().strip()
        direccion= self.e_dir.text().strip()
        pals_txt = self.e_palabras.text().strip()
        if not razon and not cif:
            QMessageBox.warning(self, "Datos incompletos",
                                "Debes indicar al menos la razón social o el CIF.")
            return
        palabras = [p.strip() for p in pals_txt.split(",") if p.strip()]
        try:
            self.db.actualizar_datos_empresa(razon, cif, direccion, "", "")
            QMessageBox.information(self, "Guardado",
                                    "Datos de tu empresa guardados correctamente.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error guardando datos: {e}")


def abrir_configuracion_empresa(parent_widget=None):
    """Abre el diálogo de configuración de empresa cliente."""
    dlg = VentanaEmpresaCliente(parent=parent_widget)
    dlg.exec_()
