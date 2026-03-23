# -*- coding: utf-8 -*-
"""
GestorProveedores — PyQt5 nativo.
Reemplaza la versión Tkinter incompatible con el event loop de PyQt5.

Exporta: abrir_gestor_proveedores(parent_widget=None, proveedor_id=None)
"""
from __future__ import annotations
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QMessageBox, QApplication, QWidget, QSplitter, QFileDialog
)
from PyQt5.QtCore import Qt, QSortFilterProxyModel
from PyQt5.QtGui import QFont, QColor


# ── Estilos compartidos ────────────────────────────────────────────────────────
BTN_PRIMARY   = "QPushButton{background:#1F4E79;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}QPushButton:disabled{background:#A0AEC0;}"
BTN_SECONDARY = "QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#E2E8F0;}"
BTN_DANGER    = "QPushButton{background:#C53030;color:white;border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#9B2C2C;}"
INPUT_STYLE   = "QLineEdit{border:1px solid #CBD5E0;border-radius:4px;padding:5px 8px;background:white;}QLineEdit:focus{border:1px solid #3182CE;}"
TABLE_STYLE   = ("QTableWidget{border:1px solid #E2E8F0;border-radius:4px;gridline-color:#EDF2F7;"
                 "selection-background-color:#EBF8FF;selection-color:#2D3748;}"
                 "QHeaderView::section{background:#F7FAFC;border-bottom:2px solid #CBD5E0;"
                 "padding:6px 8px;font-weight:bold;color:#2D3748;}")
COMBO_STYLE   = "QComboBox{border:1px solid #CBD5E0;border-radius:4px;padding:5px 8px;background:white;}QComboBox:focus{border:1px solid #3182CE;}"


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


def _inp(value="", placeholder=""):
    e = QLineEdit(str(value or ""))
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(INPUT_STYLE)
    e.setFixedHeight(32)
    return e


# ─────────────────────────────────────────────────────────────────────────────
# Formulario de proveedor (crear / editar)
# ─────────────────────────────────────────────────────────────────────────────

class _DialogProveedor(QDialog):
    """
    Diálogo modal para crear o editar un proveedor.
    prov_id=None  → creación
    prov_id=int   → edición
    """
    def __init__(self, db, prov_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.prov_id = prov_id
        self._datos = {}
        self.setWindowTitle("Editar Proveedor" if prov_id else "Nuevo Proveedor")
        self.setMinimumWidth(500)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        if prov_id:
            for p in self.db.obtener_todos_proveedores():
                if p["id"] == prov_id:
                    self._datos = p
                    break
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        # — Tipo ─────────────────────────────────────────────────────────────
        box_tipo = QGroupBox("Automatización")
        box_tipo.setStyleSheet("QGroupBox{font-weight:bold;border:1px solid #CBD5E0;border-radius:6px;"
                               "margin-top:8px;padding-top:12px;}")
        bl = QVBoxLayout(box_tipo)
        self.chk_var = QCheckBox(
            "Proveedor VARIABLE (ej: Amazon, Gasolineras) — requiere clasificación manual siempre")
        self.chk_var.setChecked(bool(self._datos.get("cuenta_variable", 0)))
        bl.addWidget(self.chk_var)
        lay.addWidget(box_tipo)

        # — Datos ─────────────────────────────────────────────────────────────
        box_d = QGroupBox("Datos del Proveedor")
        box_d.setStyleSheet("QGroupBox{font-weight:bold;border:1px solid #CBD5E0;border-radius:6px;"
                            "margin-top:8px;padding-top:12px;}")
        form = QFormLayout(box_d)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self.e_nombre   = _inp(self._datos.get("nombre"),          "Nombre comercial (obligatorio)")
        self.e_num_prov = _inp(self._datos.get("numero_proveedor"),"Ej: PRV-001")
        self.e_cuenta   = _inp(self._datos.get("cuenta_gasto"),    "Ej: 628000 (obligatorio)")
        self.e_cif      = _inp(self._datos.get("cif_nif"),         "B12345678 / 12345678A")
        self.e_email    = _inp(self._datos.get("email"),           "correo@proveedor.com")
        self.e_iban     = _inp(self._datos.get("iban"),            "ES00 0000 0000 00 0000000000")

        self.cmb_cat = QComboBox()
        self.cmb_cat.setStyleSheet(COMBO_STYLE)
        self.cmb_cat.setFixedHeight(32)
        for cat in _get_categorias():
            self.cmb_cat.addItem(cat)
        cat_actual = str(self._datos.get("categoria") or "")
        if cat_actual:
            idx = self.cmb_cat.findText(cat_actual)
            if idx >= 0:
                self.cmb_cat.setCurrentIndex(idx)

        for lbl, w in [("Nombre *:",       self.e_nombre),
                       ("Nº Proveedor:",   self.e_num_prov),
                       ("Cuenta Gasto *:", self.e_cuenta),
                       ("CIF/NIF:",        self.e_cif),
                       ("Email:",          self.e_email),
                       ("IBAN:",           self.e_iban),
                       ("Categoría:",      self.cmb_cat)]:
            form.addRow(lbl, w)
        lay.addWidget(box_d)

        # — Botones ────────────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("💾  Guardar Proveedor")
        btn_ok.setStyleSheet(BTN_PRIMARY)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._guardar)
        bar.addWidget(btn_cancel)
        bar.addWidget(btn_ok)
        lay.addLayout(bar)

    def _guardar(self):
        nombre = self.e_nombre.text().strip()
        cuenta = self.e_cuenta.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Dato obligatorio", "El nombre del proveedor es obligatorio.")
            return
        if not cuenta:
            QMessageBox.warning(self, "Dato obligatorio", "La cuenta de gasto es obligatoria.")
            return
        datos = {
            "nombre":           nombre,
            "numero_proveedor": self.e_num_prov.text().strip(),
            "cuenta_gasto":     cuenta,
            "cif_nif":          self.e_cif.text().strip(),
            "email":            self.e_email.text().strip(),
            "iban":             self.e_iban.text().strip(),
            "categoria":        self.cmb_cat.currentText(),
        }
        try:
            if self.prov_id:
                self.db.actualizar_proveedor(self.prov_id, **datos)
                self.db.marcar_proveedor_variable(self.prov_id, self.chk_var.isChecked())
                QMessageBox.information(self, "Guardado", f"Proveedor «{nombre}» actualizado.")
            else:
                new_id = self.db.insertar_proveedor(datos)
                self.db.marcar_proveedor_variable(new_id, self.chk_var.isChecked())
                QMessageBox.information(self, "Creado", f"Proveedor «{nombre}» creado.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Ventana principal — tabla de proveedores
# ─────────────────────────────────────────────────────────────────────────────

class GestorProveedores(QDialog):
    """
    Ventana principal de gestión de proveedores.
    Filtro en tiempo real, crear / editar / eliminar / importar desde Excel.
    """
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        from database import DatabaseManager
        self.db = db or DatabaseManager()
        self.setWindowTitle("📁  Gestor de Proveedores")
        self.setMinimumSize(980, 640)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._todos = []
        self._build()
        self._cargar()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)

        # — Título ─────────────────────────────────────────────────────────────
        titulo = QLabel("📁  BASE DE DATOS DE PROVEEDORES")
        titulo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        titulo.setStyleSheet("color:#1F4E79;")
        lay.addWidget(titulo)

        # — Barra de búsqueda + botones ─────────────────────────────────────────
        top = QHBoxLayout()
        self.inp_buscar = QLineEdit()
        self.inp_buscar.setPlaceholderText("🔍  Filtrar por nombre, CIF o cuenta…")
        self.inp_buscar.setStyleSheet(INPUT_STYLE)
        self.inp_buscar.setFixedHeight(34)
        self.inp_buscar.textChanged.connect(self._filtrar)
        top.addWidget(self.inp_buscar, 1)
        top.addSpacing(10)

        for txt, fn, st in [
            ("➕ Nuevo",        self._nuevo,    BTN_PRIMARY),
            ("✏️ Editar",       self._editar,   BTN_SECONDARY),
            ("🗑️ Eliminar",     self._eliminar, BTN_DANGER),
            ("📥 Importar XLS", self._importar, BTN_SECONDARY),
        ]:
            b = QPushButton(txt)
            b.setStyleSheet(st)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)

        # — Tabla ──────────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Nombre", "Nº Prov.", "Cuenta Gasto", "Categoría", "CIF/NIF", "Tipo"])
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 110)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._editar)
        lay.addWidget(self.table)

        # — Barra de estado ────────────────────────────────────────────────────
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#718096;font-size:10px;")
        lay.addWidget(self._lbl_status)

    def _cargar(self):
        self._todos = self.db.obtener_todos_proveedores()
        self._mostrar(self._todos)

    def _mostrar(self, lista):
        self.table.setRowCount(0)
        for p in lista:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 26)
            es_var = self.db.obtener_estado_variable(p["id"])
            tipo_txt = "VARIABLE 🔀" if es_var == 1 else ("FIJO 📌" if es_var == 0 else "SIN CONFIG ❓")
            for col, val in enumerate([
                p.get("id", ""),
                p.get("nombre", ""),
                p.get("numero_proveedor", ""),
                p.get("cuenta_gasto", ""),
                p.get("categoria", ""),
                p.get("cif_nif", ""),
                tipo_txt,
            ]):
                item = QTableWidgetItem(str(val or ""))
                if col == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        n = self.table.rowCount()
        self._lbl_status.setText(f"{n} proveedor{'es' if n != 1 else ''}")

    def _filtrar(self, txt):
        tl = txt.lower()
        self._mostrar([
            p for p in self._todos
            if tl in (str(p.get("nombre", "")) + str(p.get("cif_nif", "")) +
                      str(p.get("cuenta_gasto", ""))).lower()
        ])

    def _sel_id(self):
        """Devuelve el ID del proveedor seleccionado o None."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return int(item.text()) if item and item.text().isdigit() else None

    def _nuevo(self):
        dlg = _DialogProveedor(self.db, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar()

    def _editar(self):
        prov_id = self._sel_id()
        if prov_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un proveedor para editar.")
            return
        dlg = _DialogProveedor(self.db, prov_id=prov_id, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar()

    def _eliminar(self):
        prov_id = self._sel_id()
        if prov_id is None:
            QMessageBox.information(self, "Sin selección", "Selecciona un proveedor para eliminar.")
            return
        row = self.table.currentRow()
        nombre = self.table.item(row, 1).text() if self.table.item(row, 1) else str(prov_id)
        if QMessageBox.question(
                self, "Confirmar eliminación",
                f"¿Eliminar el proveedor «{nombre}» y TODAS sus reglas asociadas?\n"
                "Esta acción no se puede deshacer.",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                self.db.eliminar_proveedor(prov_id)
                self._cargar()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{exc}")

    def _importar(self):
        """Importar proveedores desde Excel mediante diálogo PyQt5."""
        try:
            from excel.importar_excel import ImportarProveedoresDialog
            dlg = ImportarProveedoresDialog(self.db, parent=self)
            if dlg.exec_() == QDialog.Accepted:
                self._cargar()
        except ImportError:
            QMessageBox.warning(
                self, "Módulo no disponible",
                "El módulo de importación desde Excel no está disponible.\n"
                "Asegúrate de que 'openpyxl' está instalado.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Error al abrir el importador:\n{exc}")


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def abrir_gestor_proveedores(parent_widget=None, proveedor_id=None):
    """
    Abre el gestor de proveedores como diálogo modal.
    Si proveedor_id no es None, abre directamente el formulario de edición.
    """
    from database import DatabaseManager
    db = DatabaseManager()

    if proveedor_id is not None:
        # Abrir directamente el formulario de edición
        dlg = _DialogProveedor(db, prov_id=proveedor_id, parent=parent_widget)
        dlg.exec_()
    else:
        dlg = GestorProveedores(db=db, parent=parent_widget)
        dlg.exec_()
