# -*- coding: utf-8 -*-
"""
GestorReglas V3.1 — Editor completo de reglas con desplegables.
CRUD completo: nombre_regla, match_cif, match_tipo_factura, match_serie, match_categoria,
               set_cuenta_proveedor, set_subcuenta_proveedor, set_cuenta_gasto,
               set_subcuenta_gasto, set_serie, set_categoria, set_tipo_factura.
AHORA: set_serie, set_categoria, set_tipo_factura son QComboBox poblados desde BD.
"""
from __future__ import annotations
import sys
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTextEdit,
    QSplitter, QWidget, QMessageBox, QSpinBox, QCheckBox, QScrollArea,
    QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

BTN_PRIMARY   = "QPushButton{background:#1F4E79;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}"
BTN_SECONDARY = "QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;border-radius:4px;padding:6px 10px;}QPushButton:hover{background:#E2E8F0;}"
BTN_DANGER    = "QPushButton{background:#C53030;color:white;border-radius:4px;padding:6px 10px;}QPushButton:hover{background:#9B2C2C;}"
BTN_WARN      = "QPushButton{background:#B7791F;color:white;border-radius:4px;padding:6px 10px;}QPushButton:hover{background:#975A16;}"
INP_STYLE     = "QLineEdit{border:1px solid #CBD5E0;border-radius:4px;padding:5px 8px;background:white;color:#2D3748;}QLineEdit:focus{border:1px solid #3182CE;}"
TABLE_STYLE   = ("QTableWidget{border:1px solid #E2E8F0;gridline-color:#EDF2F7;"
                 "selection-background-color:#EBF8FF;selection-color:#2D3748;}"
                 "QHeaderView::section{background:#F7FAFC;border-bottom:2px solid #CBD5E0;"
                 "padding:5px 6px;font-weight:bold;color:#2D3748;}")
COMBO_STYLE   = "QComboBox{border:1px solid #CBD5E0;border-radius:4px;padding:5px 8px;background:white;color:#2D3748;}"
GRP_STYLE     = "QGroupBox{font-weight:bold;border:1px solid #CBD5E0;border-radius:6px;margin-top:8px;padding-top:10px;}"


def _inp(ph="", val=""):
    e = QLineEdit()
    e.setPlaceholderText(ph)
    e.setText(str(val or ""))
    e.setStyleSheet(INP_STYLE)
    e.setFixedHeight(32)
    return e


def _sep():
    s = QFrame()
    s.setFrameShape(QFrame.HLine)
    s.setStyleSheet("color:#E2E8F0;")
    return s


class VentanaReglas(QDialog):
    """Editor completo de reglas con todos los campos match_* y set_*."""

    regla_guardada = pyqtSignal(dict)   # emitido tras guardar → visor puede refrescarse

    def __init__(self, db=None, parent=None, state=None):
        super().__init__(parent)
        from database.manager import DatabaseManager
        self.db = db or DatabaseManager()
        self._state = state          # InvoiceRuleState compartido con el visor
        self.proveedor_actual = None
        self._rid_editando = None

        # Cache de valores maestros
        self._tipos_factura = []
        self._series_factura = []
        self._categorias = []
        self._proveedores = []
        
        self._cargar_maestros()

        self.setWindowTitle("🔧  Gestor de Reglas V3.1 — CRUD Completo + Desplegables")
        self.setMinimumSize(1280, 800)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()
        self._cargar_proveedores()

    def _cargar_maestros(self):
        """Carga los valores maestros desde la BD."""
        try:
            self._tipos_factura = self.db.obtener_tipos_factura()
        except Exception:
            self._tipos_factura = [{"nombre": "FACTURA"}, {"nombre": "ABONO"}, {"nombre": "RECTIFICATIVA"}]
        
        try:
            self._series_factura = self.db.obtener_series_factura()
        except Exception:
            self._series_factura = [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}, {"nombre": "R"}]
        
        try:
            self._categorias = self.db.obtener_categorias()
        except Exception:
            self._categorias = [{"nombre": c} for c in [
                "COMERCIAL Y POSTVENTA EXTERNAS", "COMUNES EXTERNOS", "GESTORIA", 
                "SEAT", "COMBUSTIBLE", "COMUNICACIONES", "MANTENIMIENTO", 
                "SEGUROS", "SUMINISTROS", "VARIOS"
            ]]

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)
        t = QLabel("🧠  GESTOR DE REGLAS V3.1 — Editar · Duplicar · Activar/Desactivar")
        t.setFont(QFont("Segoe UI", 12, QFont.Bold))
        t.setStyleSheet("color:#1F4E79;")
        lay.addWidget(t)

        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(6)
        sp.addWidget(self._panel_editor())
        sp.addWidget(self._panel_tabla())
        sp.setStretchFactor(0, 2)
        sp.setStretchFactor(1, 3)
        lay.addWidget(sp)

        bar = QHBoxLayout()
        bar.addStretch()
        bc = QPushButton("✖ Cerrar")
        bc.setStyleSheet(BTN_SECONDARY)
        bc.clicked.connect(self.accept)
        bar.addWidget(bc)
        lay.addLayout(bar)

    def _panel_editor(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        # ── Proveedor ──────────────────────────────────────────────────────────
        grp_prov = QGroupBox("1. Proveedor")
        grp_prov.setStyleSheet(GRP_STYLE)
        fp = QFormLayout(grp_prov)
        fp.setSpacing(7)
        fp.setLabelAlignment(Qt.AlignRight)

        self.cmb_proveedor = QComboBox()
        self.cmb_proveedor.setStyleSheet(COMBO_STYLE)
        self.cmb_proveedor.setFixedHeight(32)
        self.cmb_proveedor.currentIndexChanged.connect(self._on_prov_change)
        fp.addRow("Proveedor:", self.cmb_proveedor)

        self.inp_nombre_regla = _inp("Nombre único de la regla (ej: REPSOL_FACT)")
        fp.addRow("Nombre regla *:", self.inp_nombre_regla)
        lay.addWidget(grp_prov)

        # ── Match (condiciones) ────────────────────────────────────────────────
        grp_match = QGroupBox("2. Condiciones match (CIF + Tipo obligatorios)")
        grp_match.setStyleSheet(GRP_STYLE)
        fm = QFormLayout(grp_match)
        fm.setSpacing(7)
        fm.setLabelAlignment(Qt.AlignRight)

        self.inp_match_cif   = _inp("B12345678 — CIF obligatorio para regla determinista")
        # match_tipo → QComboBox con tipos reales
        self.inp_match_tipo  = QComboBox()
        self.inp_match_tipo.setStyleSheet(COMBO_STYLE)
        self.inp_match_tipo.setFixedHeight(32)
        self.inp_match_tipo.addItem("— cualquier tipo —", "")
        for t in self._tipos_factura:
            self.inp_match_tipo.addItem(t.get("nombre", ""), t.get("nombre", ""))
        # match_serie → QComboBox con series reales
        self.inp_match_serie = QComboBox()
        self.inp_match_serie.setStyleSheet(COMBO_STYLE)
        self.inp_match_serie.setFixedHeight(32)
        self.inp_match_serie.addItem("— cualquier serie —", "")
        for s in self._series_factura:
            self.inp_match_serie.addItem(s.get("nombre", ""), s.get("nombre", ""))
        # match_cat → QComboBox con categorías reales
        self.inp_match_cat   = QComboBox()
        self.inp_match_cat.setStyleSheet(COMBO_STYLE)
        self.inp_match_cat.setFixedHeight(32)
        self.inp_match_cat.addItem("— cualquier categoría —", "")
        for c in self._categorias:
            self.inp_match_cat.addItem(c.get("nombre", ""), c.get("nombre", ""))
        # Trigger = texto libre (excepción: sigue siendo QLineEdit)
        self.inp_trigger     = _inp("gasolina, repsol, A78066508 (keywords OCR para var.)")
        fm.addRow("CIF match:", self.inp_match_cif)
        fm.addRow("Tipo factura match:", self.inp_match_tipo)
        fm.addRow("Serie match:", self.inp_match_serie)
        fm.addRow("Categoría match:", self.inp_match_cat)
        fm.addRow("Trigger / keyword:", self.inp_trigger)
        lay.addWidget(grp_match)

        # ── Set (valores a escribir) ───────────────────────────────────────────
        grp_set = QGroupBox("3. Valores a escribir (set_*)")
        grp_set.setStyleSheet(GRP_STYLE)
        fs = QFormLayout(grp_set)
        fs.setSpacing(7)
        fs.setLabelAlignment(Qt.AlignRight)

        # Cuenta/subcuenta proveedor
        cta_prov = QHBoxLayout()
        self.inp_set_cta_prov = _inp("400000")
        self.inp_set_sub_prov = _inp("subcuenta (opcional)")
        self.inp_set_cta_prov.setFixedWidth(100)
        cta_prov.addWidget(self.inp_set_cta_prov)
        cta_prov.addWidget(QLabel("/"))
        cta_prov.addWidget(self.inp_set_sub_prov)
        fs.addRow("Cta/Sub Proveedor:", cta_prov)

        # Cuenta/subcuenta gasto
        cta_gasto = QHBoxLayout()
        self.inp_cuenta       = _inp("628000 / 600000")   # alias para BD legacy
        self.inp_set_sub_gasto = _inp("subcuenta (opcional)")
        self.inp_cuenta.setFixedWidth(100)
        cta_gasto.addWidget(self.inp_cuenta)
        cta_gasto.addWidget(QLabel("/"))
        cta_gasto.addWidget(self.inp_set_sub_gasto)
        fs.addRow("Cta/Sub Gasto:", cta_gasto)

        # --- CAMPOS CON DESPLEGABLES ---
        # Serie set
        self.cmb_set_serie = QComboBox()
        self.cmb_set_serie.setStyleSheet(COMBO_STYLE)
        self.cmb_set_serie.setFixedHeight(32)
        self.cmb_set_serie.addItem("", "")  # Opción vacía
        for s in self._series_factura:
            nombre = s.get("nombre", "")
            self.cmb_set_serie.addItem(nombre, nombre)
        fs.addRow("Serie set:", self.cmb_set_serie)

        # Categoría set
        self.cmb_set_categoria = QComboBox()
        self.cmb_set_categoria.setStyleSheet(COMBO_STYLE)
        self.cmb_set_categoria.setFixedHeight(32)
        self.cmb_set_categoria.addItem("", "")
        for c in self._categorias:
            nombre = c.get("nombre", "")
            self.cmb_set_categoria.addItem(nombre, nombre)
        fs.addRow("Categoría set:", self.cmb_set_categoria)

        # Tipo factura set
        self.cmb_set_tipo = QComboBox()
        self.cmb_set_tipo.setStyleSheet(COMBO_STYLE)
        self.cmb_set_tipo.setFixedHeight(32)
        self.cmb_set_tipo.addItem("", "")
        for t in self._tipos_factura:
            nombre = t.get("nombre", "")
            self.cmb_set_tipo.addItem(nombre, nombre)
        fs.addRow("Tipo factura set:", self.cmb_set_tipo)

        lay.addWidget(grp_set)

        # ── Opciones ───────────────────────────────────────────────────────────
        grp_op = QGroupBox("4. Opciones")
        grp_op.setStyleSheet(GRP_STYLE)
        fo = QFormLayout(grp_op)
        fo.setSpacing(7)
        self.spn_prio   = QSpinBox()
        self.spn_prio.setRange(1, 100)
        self.spn_prio.setValue(1)
        self.spn_prio.setStyleSheet("QSpinBox{border:1px solid #CBD5E0;border-radius:4px;padding:4px;}")
        self.chk_activa = QCheckBox("Regla activa")
        self.chk_activa.setChecked(True)
        self.chk_activa.setStyleSheet("color:#276749;font-weight:bold;")
        self.chk_cont_auto = QCheckBox("Cont. automática (DMS)")
        self.chk_cont_auto.setStyleSheet("color:#1A6B4A;font-weight:bold;")
        self.chk_cont_auto.setToolTip("Marcar si el DMS contabiliza esta factura automáticamente.")
        fo.addRow("Prioridad:", self.spn_prio)
        fo.addRow("", self.chk_activa)
        fo.addRow("", self.chk_cont_auto)
        lay.addWidget(grp_op)

        # ── Modo y botones ─────────────────────────────────────────────────────
        self._lbl_modo = QLabel("▶ NUEVA REGLA")
        self._lbl_modo.setStyleSheet("background:#EBF8FF;color:#2C5282;border-radius:4px;"
                                     "padding:3px 8px;font-size:10px;font-weight:bold;")
        lay.addWidget(self._lbl_modo)

        brow = QHBoxLayout()
        btn_g = QPushButton("💾 Guardar")
        btn_g.setStyleSheet(BTN_PRIMARY)
        btn_g.setFixedHeight(34)
        btn_g.clicked.connect(self._guardar_regla)
        btn_n = QPushButton("➕ Nueva")
        btn_n.setStyleSheet(BTN_SECONDARY)
        btn_n.setFixedHeight(34)
        btn_n.clicked.connect(self._nueva_regla)
        brow.addWidget(btn_g)
        brow.addWidget(btn_n)
        lay.addLayout(brow)

        # ── Probar trigger en OCR ──────────────────────────────────────────────
        grp_ocr = QGroupBox("🔄 Probar trigger en texto OCR")
        grp_ocr.setStyleSheet(GRP_STYLE)
        go = QVBoxLayout(grp_ocr)
        go.addWidget(QLabel("Pega texto OCR para ver qué regla se dispararía:"))
        self.txt_ocr = QTextEdit()
        self.txt_ocr.setPlaceholderText("AMAZON EU SARL · FACTURA/2024/001 · Total: 99,99 €")
        self.txt_ocr.setFixedHeight(70)
        self.txt_ocr.setStyleSheet("QTextEdit{border:1px solid #CBD5E0;border-radius:4px;"
                                   "background:white;color:#2D3748;}")
        self.txt_ocr.textChanged.connect(self._live_probar)
        go.addWidget(self.txt_ocr)
        btn_test = QPushButton("🔍 Probar trigger ahora")
        btn_test.setStyleSheet(BTN_SECONDARY)
        btn_test.clicked.connect(self._probar_ocr)
        go.addWidget(btn_test)
        self.lbl_res = QLabel("—")
        self.lbl_res.setWordWrap(True)
        self.lbl_res.setStyleSheet("color:#2B6CB0;padding:4px;font-weight:bold;")
        go.addWidget(self.lbl_res)
        lay.addWidget(grp_ocr)

        lay.addStretch()
        w.setWidget(container)
        return w

    def _panel_tabla(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        gb = QGroupBox("Lista de Reglas")
        gb.setStyleSheet(GRP_STYLE)
        bt = QVBoxLayout(gb)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Proveedor", "Nombre Regla", "Match CIF", "Match Tipo",
             "Cta Gasto", "Cat", "Estado"])
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c, w_ in [(0, 35), (1, 100), (3, 95), (4, 70), (5, 80), (6, 80), (7, 55)]:
            self.table.setColumnWidth(c, w_)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(lambda r, c: self._cargar_en_editor(r))
        bt.addWidget(self.table)
        lay.addWidget(gb, 3)

        bbar = QHBoxLayout()
        for lbl, style, slot in [
            ("✏️ Editar",      BTN_PRIMARY,   lambda: self._cargar_en_editor()),
            ("📋 Duplicar",    BTN_SECONDARY, self._duplicar),
            ("⏸ Activar/Des", BTN_WARN,      self._toggle),
            ("🗑️ Eliminar",   BTN_DANGER,    self._eliminar),
        ]:
            b = QPushButton(lbl)
            b.setStyleSheet(style)
            b.setFixedHeight(32)
            b.clicked.connect(slot)
            bbar.addWidget(b)
        lay.addLayout(bbar)
        return w

    # ── Lógica ─────────────────────────────────────────────────────────────────

    def _cargar_proveedores(self):
        self.cmb_proveedor.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_proveedor.addItem("── TODAS ──", None)
        self.cmb_proveedor.addItem("── GLOBALES ──", 0)
        for p in self.db.obtener_todos_proveedores():
            self.cmb_proveedor.addItem(
                f"{p.get('nombre','?')} (ID:{p['id']})", p["id"])
        self.cmb_proveedor.blockSignals(False)
        self.cmb_proveedor.setCurrentIndex(0)
        self.proveedor_actual = None
        self._actualizar_tabla()

    def _on_prov_change(self, idx):
        self.proveedor_actual = self.cmb_proveedor.itemData(idx)
        self._actualizar_tabla()

    def _actualizar_tabla(self):
        self.table.setRowCount(0)
        pv = self.proveedor_actual
        reglas = self.db.obtener_reglas_proveedor(pv if pv else None)
        provs = {p["id"]: p.get("nombre", "?") for p in self.db.obtener_todos_proveedores()}
        for r in reglas:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, 26)
            pid   = r.get("proveedor_id")
            pname = provs.get(pid, "GLOBAL") if pid else "GLOBAL"
            activa = r.get("activa", 1)
            nombre_r = r.get("nombre_regla") or r.get("serie", "")
            for col, val in enumerate([
                r.get("id", ""), pname, nombre_r,
                r.get("match_cif", ""), r.get("match_tipo_factura", ""),
                r.get("set_cuenta_gasto") or r.get("cuenta_gasto", ""),
                r.get("set_categoria") or r.get("categoria", ""),
                "✅" if activa else "⏸",
            ]):
                item = QTableWidgetItem(str(val or ""))
                if col == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                if not activa:
                    item.setForeground(QColor("#A0AEC0"))
                elif pname == "GLOBAL" and col == 1:
                    item.setForeground(QColor("#C05621"))
                self.table.setItem(row, col, item)

    def _get_rid(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Sin selección", "Selecciona una regla primero.")
            return None, None
        item = self.table.item(row, 0)
        return row, int(item.text()) if item else None

    def _cargar_en_editor(self, row=None):
        if row is None:
            row = self.table.currentRow()
        if row < 0:
            return
        rid_item = self.table.item(row, 0)
        if not rid_item:
            return
        rid = int(rid_item.text())
        reglas = self.db.obtener_reglas_proveedor(None)
        r = next((x for x in reglas if x.get("id") == rid), None)
        if not r:
            return
        self._rid_editando = rid
        # Proveedor
        pid = r.get("proveedor_id")
        if pid:
            idx = self.cmb_proveedor.findData(pid)
            if idx >= 0:
                self.cmb_proveedor.blockSignals(True)
                self.cmb_proveedor.setCurrentIndex(idx)
                self.cmb_proveedor.blockSignals(False)
        # Campos
        self.inp_nombre_regla.setText(r.get("nombre_regla") or r.get("serie", ""))
        self.inp_match_cif.setText(r.get("match_cif", ""))
        self._set_combo_value(self.inp_match_tipo,  r.get("match_tipo_factura", "") or "")
        self._set_combo_value(self.inp_match_serie, r.get("match_serie", "") or "")
        self._set_combo_value(self.inp_match_cat,   r.get("match_categoria", "") or "")
        self.inp_trigger.setText(r.get("serie", ""))   # trigger legacy = serie
        self.inp_set_cta_prov.setText(r.get("set_cuenta_proveedor", ""))
        self.inp_set_sub_prov.setText(r.get("set_subcuenta_proveedor", ""))
        self.inp_cuenta.setText(r.get("set_cuenta_gasto") or r.get("cuenta_gasto", ""))
        self.inp_set_sub_gasto.setText(r.get("subcuenta_gasto") or r.get("set_subcuenta_gasto", ""))
        
        # Cargar valores en comboboxes
        self._set_combo_value(self.cmb_set_serie, r.get("set_serie", ""))
        self._set_combo_value(self.cmb_set_categoria, r.get("set_categoria") or r.get("categoria", ""))
        self._set_combo_value(self.cmb_set_tipo, r.get("set_tipo_factura", ""))
        
        self.spn_prio.setValue(int(r.get("prioridad", 1)))
        self.chk_activa.setChecked(bool(r.get("activa", 1)))
        self.chk_cont_auto.setChecked(bool(r.get("cont_automatica", 0)))
        # --- CORRECCIÓN: Eliminado el 'u' que causaba error ---
        self._lbl_modo.setText(f"✏️ EDITANDO ID {rid}")
        self._lbl_modo.setStyleSheet("background:#FFFBEB;color:#B7791F;border-radius:4px;"
                                     "padding:3px 8px;font-size:10px;font-weight:bold;")

    def _set_combo_value(self, combo, valor):
        """Selecciona el valor en un combobox si existe."""
        if not valor:
            combo.setCurrentIndex(0)
            return
        for i in range(combo.count()):
            if combo.itemData(i) == valor or combo.itemText(i) == valor:
                combo.setCurrentIndex(i)
                return
        # Si no existe, añadirlo temporalmente
        combo.addItem(valor, valor)
        combo.setCurrentIndex(combo.count() - 1)

    def _nueva_regla(self):
        self._rid_editando = None
        for w in [self.inp_nombre_regla, self.inp_match_cif, self.inp_trigger,
                  self.inp_set_cta_prov, self.inp_set_sub_prov, self.inp_cuenta,
                  self.inp_set_sub_gasto]:
            w.clear()
        self.inp_match_tipo.setCurrentIndex(0)
        self.inp_match_serie.setCurrentIndex(0)
        self.inp_match_cat.setCurrentIndex(0)
        self.cmb_set_serie.setCurrentIndex(0)
        self.cmb_set_categoria.setCurrentIndex(0)
        self.cmb_set_tipo.setCurrentIndex(0)
        self.spn_prio.setValue(1)
        self.chk_activa.setChecked(True)
        self.chk_cont_auto.setChecked(False)
        self._lbl_modo.setText("▶ NUEVA REGLA")
        self._lbl_modo.setStyleSheet("background:#EBF8FF;color:#2C5282;border-radius:4px;"
                                     "padding:3px 8px;font-size:10px;font-weight:bold;")

    def _guardar_regla(self):
        nombre_regla = self.inp_nombre_regla.text().strip()
        trigger      = self.inp_trigger.text().strip()   # keyword/disparador legacy
        cuenta       = self.inp_cuenta.text().strip()

        # El nombre_regla o el trigger deben existir
        if not nombre_regla and not trigger:
            QMessageBox.warning(self, "Dato obligatorio",
                                "Introduce el Nombre de la regla o un Trigger.")
            return

        # Obtener valores de los comboboxes
        set_serie = self.cmb_set_serie.currentData() or self.cmb_set_serie.currentText()
        set_categoria = self.cmb_set_categoria.currentData() or self.cmb_set_categoria.currentText()
        set_tipo = self.cmb_set_tipo.currentData() or self.cmb_set_tipo.currentText()

        datos = {
            "nombre_regla":            nombre_regla or trigger,
            "serie":                   trigger or nombre_regla,   # compat BD legacy
            "match_cif":               self.inp_match_cif.text().strip(),
            "match_tipo_factura":      self.inp_match_tipo.currentData() or "",
            "match_serie":             self.inp_match_serie.currentData() or "",
            "match_categoria":         self.inp_match_cat.currentData() or "",
            "set_cuenta_proveedor":    self.inp_set_cta_prov.text().strip(),
            "set_subcuenta_proveedor": self.inp_set_sub_prov.text().strip(),
            "set_cuenta_gasto":        cuenta,
            "cuenta_gasto":            cuenta,                    # compat BD legacy
            "set_subcuenta_gasto":     self.inp_set_sub_gasto.text().strip(),
            "subcuenta_gasto":         self.inp_set_sub_gasto.text().strip(),
            "set_serie":               set_serie,
            "set_categoria":           set_categoria,
            "categoria":               set_categoria,
            "set_tipo_factura":        set_tipo,
            "prioridad":               self.spn_prio.value(),
            "activa":                  1 if self.chk_activa.isChecked() else 0,
            "cont_automatica":         1 if self.chk_cont_auto.isChecked() else 0,
            "rule_type":               "determinista",
        }

        try:
            if self._rid_editando:
                datos["id"] = self._rid_editando
                self.db.guardar_regla_determinista(datos)
                QMessageBox.information(self, "Guardado",
                                        f"Regla ID {self._rid_editando} actualizada.")
            else:
                pid = self.proveedor_actual if self.proveedor_actual else 0
                datos["proveedor_id"] = pid
                nid = self.db.guardar_regla_determinista(datos)
                QMessageBox.information(self, "Guardada",
                                        f"Regla «{nombre_regla or trigger}» creada (ID {nid}).")
            self._nueva_regla()
            self._actualizar_tabla()
            # Notificar al visor si hay state compartido
            if self._state:
                self._state._engine = None   # invalidar caché del motor
            self.regla_guardada.emit(datos)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{exc}")

    def _duplicar(self):
        _, rid = self._get_rid()
        if rid is None:
            return
        try:
            nid = self.db.duplicar_regla_proveedor(rid)
            self._actualizar_tabla()
            QMessageBox.information(self, "Duplicada",
                                    f"Regla {rid} duplicada → nuevo ID {nid}.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo duplicar:\n{exc}")

    def _toggle(self):
        _, rid = self._get_rid()
        if rid is None:
            return
        try:
            nuevo = self.db.toggle_regla_proveedor(rid)
            self._actualizar_tabla()
            self.lbl_res.setText(
                f"Regla ID {rid} {'activada ✅' if nuevo else 'desactivada ⏸'}.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo cambiar:\n{exc}")

    def _eliminar(self):
        row, rid = self._get_rid()
        if rid is None:
            return
        item = self.table.item(row, 2)
        disp = item.text() if item else str(rid)
        if QMessageBox.question(
                self, "Confirmar", f"¿Eliminar la regla «{disp}»?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                self.db.eliminar_regla_proveedor(rid)
                self._actualizar_tabla()
                if self._rid_editando == rid:
                    self._nueva_regla()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{exc}")

    def _live_probar(self):
        if len(self.txt_ocr.toPlainText().strip()) > 8:
            self._probar_ocr()

    def _probar_ocr(self):
        texto = self.txt_ocr.toPlainText().strip()
        if not texto:
            return
        try:
            from rules.engine import RuleEngine
            vendors = self.db.obtener_todos_proveedores()
            rules   = self.db.obtener_reglas_proveedor(None)
            eng = RuleEngine(vendors, rules)
            from core.models import InvoiceFields
            # Extraer CIF del texto para probar modo determinista también
            import re
            cif_m = re.search(r'\b[A-Z]\d{7}[A-Z0-9]\b|\b\d{8}[A-Z]\b', texto)
            cif = cif_m.group(0) if cif_m else ""
            fields = InvoiceFields(cif_nif=cif)
            res = eng.classify(texto, fields)
            if res and res.vendor:
                regla_n = getattr(res, "nombre_regla", "") or ""
                self.lbl_res.setText(
                    f"✅ MATCH  —  Proveedor: «{res.vendor.name}»"
                    f"  |  Regla: {regla_n}"
                    f"  |  Cuenta: {res.expense_account}"
                    f"  |  Cat: {res.category}"
                    f"  |  Confianza: {res.confidence:.0%}")
                self.lbl_res.setStyleSheet(
                    "color:#276749;font-weight:bold;background:#F0FFF4;"
                    "border-radius:4px;padding:6px;")
            else:
                self.lbl_res.setText("❌ Sin coincidencia para este texto.")
                self.lbl_res.setStyleSheet(
                    "color:#C53030;font-weight:bold;background:#FFF5F5;"
                    "border-radius:4px;padding:6px;")
        except Exception as exc:
            self.lbl_res.setText(f"Error: {exc}")
            self.lbl_res.setStyleSheet("color:#C53030;padding:4px;")


def abrir_gestor_reglas(parent_widget=None, state=None):
    from database.manager import DatabaseManager
    dlg = VentanaReglas(db=DatabaseManager(), parent=parent_widget, state=state)
    dlg.exec_()