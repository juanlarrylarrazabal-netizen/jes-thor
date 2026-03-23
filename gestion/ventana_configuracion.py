# -*- coding: utf-8 -*-
"""
ventana_configuracion.py — PyQt5 nativo.
Ventana de ajustes rápidos del sistema.
Nota: la mayor parte de la configuración se gestiona desde tab_ajustes.py.
Esta ventana es un punto de acceso rápido mantenido por compatibilidad.
"""
from __future__ import annotations
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QHBoxLayout, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt
import config

BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:8px 16px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:8px 16px;}QPushButton:hover{background:#E2E8F0;}")


class VentanaConfiguracionGlobal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️  Ajustes del Sistema")
        self.setMinimumWidth(480)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)

        titulo = QLabel("AJUSTES DEL SISTEMA")
        titulo.setStyleSheet("font-size:14px;font-weight:bold;color:#1F4E79;")
        lay.addWidget(titulo)

        btn_empresa = QPushButton("🏢  MI EMPRESA")
        btn_empresa.setStyleSheet(BTN_P)
        btn_empresa.setFixedHeight(40)
        btn_empresa.clicked.connect(self._abrir_empresa)
        lay.addWidget(btn_empresa)

        btn_cuentas = QPushButton("📧  CUENTAS GMAIL")
        btn_cuentas.setStyleSheet(BTN_P)
        btn_cuentas.setFixedHeight(40)
        btn_cuentas.clicked.connect(self._abrir_cuentas)
        lay.addWidget(btn_cuentas)

        # Carpeta temporal
        lbl = QLabel("Carpeta temporal de descarga:")
        lbl.setStyleSheet("font-weight:bold;margin-top:8px;")
        lay.addWidget(lbl)

        bar = QHBoxLayout()
        self.inp_path = QLineEdit(str(getattr(config, "CARPETA_TEMPORAL", "./facturas_temp")))
        self.inp_path.setReadOnly(True)
        self.inp_path.setStyleSheet("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;padding:5px;background:#F7FAFC;}")
        btn_carpeta = QPushButton("📁")
        btn_carpeta.setFixedWidth(40)
        btn_carpeta.setStyleSheet(BTN_S)
        btn_carpeta.clicked.connect(self._cambiar_carpeta)
        bar.addWidget(self.inp_path)
        bar.addWidget(btn_carpeta)
        lay.addLayout(bar)

        lay.addStretch()
        btn_cerrar = QPushButton("CERRAR")
        btn_cerrar.setStyleSheet(BTN_S)
        btn_cerrar.clicked.connect(self.accept)
        lay.addWidget(btn_cerrar, alignment=Qt.AlignRight)

    def _abrir_empresa(self):
        from gestion.ventana_empresa_cliente import abrir_configuracion_empresa
        abrir_configuracion_empresa(self)

    def _abrir_cuentas(self):
        from gestion.gestor_cuentas import abrir_gestor_cuentas
        abrir_gestor_cuentas(self)

    def _cambiar_carpeta(self):
        nueva = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta temporal")
        if nueva:
            config.CARPETA_TEMPORAL = nueva
            self.inp_path.setText(nueva)
