# -*- coding: utf-8 -*-
"""Pestaña de proveedores."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLineEdit, QLabel, QAbstractItemView, QMessageBox
)
from PyQt5.QtCore import Qt
from ui.styles import BTN_PRIMARY, BTN_SECONDARY, BTN_DANGER, TABLE, INPUT


class TabProveedores(QWidget):
    def __init__(self, db, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._todos = []
        self._build()
        self.cargar()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)

        # Barra superior
        bar = QHBoxLayout()
        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("🔍  Buscar proveedor por nombre o CIF...")
        self.inp_search.setFixedHeight(36)
        self.inp_search.setStyleSheet(INPUT)
        self.inp_search.textChanged.connect(self._filter)
        bar.addWidget(self.inp_search)
        bar.addStretch()
        for txt, fn, st in [
            ("➕ Nuevo",   self._new,    BTN_PRIMARY),
            ("✏️ Editar",  self._edit,   BTN_SECONDARY),
            ("🔧 Reglas",  self._rules,  BTN_SECONDARY),
        ]:
            b = QPushButton(txt); b.setStyleSheet(st); b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(34); b.clicked.connect(fn); bar.addWidget(b)
        lay.addLayout(bar)

        # Tabla
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Nombre", "Nº Prov.", "Cuenta", "Categoría", "CIF/NIF"])
        self.table.setStyleSheet(TABLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 45)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._edit)
        lay.addWidget(self.table)

    def cargar(self) -> None:
        self._todos = self.db.obtener_todos_proveedores()
        self._show(self._todos)

    def _show(self, lista) -> None:
        self.table.setRowCount(0)
        for p in lista:
            row = self.table.rowCount(); self.table.insertRow(row)
            self.table.setRowHeight(row, 26)
            for col, val in enumerate([p.get("id",""), p.get("nombre",""), p.get("numero_proveedor",""),
                                         p.get("cuenta_gasto",""), p.get("categoria",""), p.get("cif_nif","")]):
                self.table.setItem(row, col, QTableWidgetItem(str(val or "")))

    def _filter(self, txt: str) -> None:
        tl = txt.lower()
        self._show([p for p in self._todos
                    if tl in (p.get("nombre","") + p.get("cif_nif","")).lower()])

    def _new(self) -> None:
        """Abre el gestor de proveedores para crear uno nuevo."""
        try:
            from gestor_proveedores import abrir_gestor_proveedores
            abrir_gestor_proveedores(self)
            self.cargar()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _edit(self) -> None:
        """Abre el gestor de proveedores con el proveedor seleccionado."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un proveedor para editar.")
            return
        try:
            proveedor_id = None
            item = self.table.item(row, 0)
            if item and item.text().isdigit():
                proveedor_id = int(item.text())
            from gestor_proveedores import abrir_gestor_proveedores
            abrir_gestor_proveedores(self, proveedor_id=proveedor_id)
            self.cargar()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _rules(self) -> None:
        try:
            from gestor_reglas_proveedor import abrir_gestor_reglas
            abrir_gestor_reglas(self)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _eliminar(self) -> None:
        """J: Elimina proveedor con confirmación y opción de merge."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Sin selección", "Selecciona un proveedor para eliminar.")
            return
        item = self.table.item(row, 0)
        if not item or not item.text().isdigit():
            return
        pid  = int(item.text())
        name = (self.table.item(row, 1).text() if self.table.item(row, 1) else str(pid))

        resp = QMessageBox.question(
            self, "Eliminar proveedor",
            f"¿Eliminar '{name}' (ID {pid})?\n\n"
            "Si tiene facturas/reglas dependientes, puedes unificarlo\n"
            "con otro proveedor antes de eliminar.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if resp == QMessageBox.Cancel:
            return
        if resp == QMessageBox.No:
            # Ofrecer unificar
            self._unificar_hacia(pid)
            return
        try:
            self.db.eliminar_proveedor_con_merge(pid)
            self.cargar()
            QMessageBox.information(self, "Eliminado", f"Proveedor '{name}' eliminado.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{exc}")

    def _unificar_hacia(self, src_id: int) -> None:
        """J: Mueve referencias de src_id a un proveedor destino elegido."""
        from PyQt5.QtWidgets import QInputDialog
        destinos = [(p["id"], p["nombre"]) for p in (self._todos or [])
                    if p["id"] != src_id]
        if not destinos:
            QMessageBox.information(self, "Sin destino", "No hay otro proveedor al que unificar.")
            return
        choices = [f"{d[0]} — {d[1]}" for d in destinos]
        choice, ok = QInputDialog.getItem(
            self, "Unificar a", "Selecciona el proveedor destino:", choices, 0, False)
        if not ok: return
        dst_id = destinos[choices.index(choice)][0]
        try:
            self.db.eliminar_proveedor_con_merge(src_id, merge_into_id=dst_id)
            self.cargar()
            QMessageBox.information(self, "Unificado",
                f"Proveedor ID {src_id} unificado en ID {dst_id} y eliminado.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo unificar:\n{exc}")

    def _unificar_duplicados(self) -> None:
        """J: Detecta proveedores con nombre similar y ofrece unificar."""
        try:
            grupos = self.db.buscar_proveedores_duplicados()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc)); return
        if not grupos:
            QMessageBox.information(self, "Sin duplicados",
                "No se detectaron proveedores con nombre similar (normalizado)."); return
        msg = f"Se detectaron {len(grupos)} grupos de posibles duplicados:\n\n"
        for g in grupos[:5]:
            msg += "  • " + ", ".join(f"{p['nombre']} (ID:{p['id']})" for p in g) + "\n"
        if len(grupos) > 5:
            msg += f"  … y {len(grupos)-5} grupos más."
        msg += "\n\n¿Abrir gestor de proveedores para revisar?"
        if QMessageBox.question(self, "Posibles duplicados", msg,
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            from gestion.gestor_proveedores import abrir_gestor_proveedores
            try: abrir_gestor_proveedores(self); self.cargar()
            except Exception: pass
