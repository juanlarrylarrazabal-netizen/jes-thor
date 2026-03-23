# -*- coding: utf-8 -*-
"""
gestor_cuentas.py — PyQt5 nativo.
Gestión de cuentas de correo guardadas en la base de datos.

Clases:
    GestorCuentas             — lógica sin UI (mantiene compatibilidad)
    VentanaCuentasCorreo      — PyQt5 QDialog
Exporta: abrir_gestor_cuentas(parent_widget=None)
         obtener_cuenta_activa() -> dict | None
"""
from __future__ import annotations
import sys, os, sqlite3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox
)
from PyQt5.QtCore import Qt

BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#E2E8F0;}")
BTN_D = ("QPushButton{background:#C53030;color:white;border-radius:4px;"
         "padding:6px 14px;}QPushButton:hover{background:#9B2C2C;}")
INP   = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
         "padding:5px 8px;background:white;}QLineEdit:focus{border:1px solid #3182CE;}")
TBL   = ("QTableWidget{border:1px solid #E2E8F0;border-radius:4px;}"
         "QHeaderView::section{background:#F7FAFC;border-bottom:1px solid #CBD5E0;"
         "padding:5px 8px;font-weight:bold;}")


# ─────────────────────────────────────────────────────────────────────────────
# Capa de datos (sin UI)
# ─────────────────────────────────────────────────────────────────────────────

class GestorCuentas:
    """Gestiona cuentas de correo en SQLite. Sin dependencias de UI."""
    def __init__(self):
        try:
            from config import DB_PATH
            db_path = DB_PATH
        except Exception:
            db_path = "./facturas.db"
        self.conn   = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._crear_tabla()

    def _crear_tabla(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS cuentas_correo (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre   TEXT,
                email    TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                activa   INTEGER DEFAULT 0
            )""")
        self.conn.commit()

    def agregar_cuenta(self, nombre, email, password) -> bool:
        try:
            self.cursor.execute(
                "INSERT INTO cuentas_correo (nombre, email, password) VALUES (?,?,?)",
                (nombre, email, password))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def obtener_todas_cuentas(self):
        self.cursor.execute("SELECT id,nombre,email,activa FROM cuentas_correo")
        return self.cursor.fetchall()

    def obtener_cuenta_activa(self):
        self.cursor.execute(
            "SELECT id,nombre,email,password FROM cuentas_correo WHERE activa=1 LIMIT 1")
        return self.cursor.fetchone()

    def establecer_cuenta_activa(self, id_cuenta):
        self.cursor.execute("UPDATE cuentas_correo SET activa=0")
        self.cursor.execute("UPDATE cuentas_correo SET activa=1 WHERE id=?", (id_cuenta,))
        self.conn.commit()

    def eliminar_cuenta(self, id_cuenta):
        self.cursor.execute("DELETE FROM cuentas_correo WHERE id=?", (id_cuenta,))
        self.conn.commit()

    def cerrar(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# UI — PyQt5
# ─────────────────────────────────────────────────────────────────────────────

class _NuevaCuentaDlg(QDialog):
    """Sub-diálogo para añadir una cuenta de correo."""
    def __init__(self, gestor: GestorCuentas, parent=None):
        super().__init__(parent)
        self.gestor = gestor
        self.setWindowTitle("➕  Nueva Cuenta de Correo")
        self.setMinimumWidth(440)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.e_nombre   = QLineEdit(); self.e_nombre.setPlaceholderText("Cuenta Personal / Empresa…")
        self.e_email    = QLineEdit(); self.e_email.setPlaceholderText("usuario@gmail.com")
        self.e_password = QLineEdit(); self.e_password.setPlaceholderText("Contraseña de aplicación (16 chars)")
        self.e_password.setEchoMode(QLineEdit.Password)
        for w in [self.e_nombre, self.e_email, self.e_password]:
            w.setStyleSheet(INP)
            w.setFixedHeight(32)

        form.addRow("Nombre:",          self.e_nombre)
        form.addRow("Email:",           self.e_email)
        form.addRow("Contraseña App:",  self.e_password)
        lay.addLayout(form)

        lbl = QLabel("💡 Usa una <b>contraseña de aplicación</b> de Google, no tu contraseña normal.<br>"
                     "Obtenerla en: myaccount.google.com → Seguridad → Contraseñas de aplicaciones")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#4A5568;font-size:9px;")
        lay.addWidget(lbl)

        bar = QHBoxLayout()
        bar.addStretch()
        btn_cancel = QPushButton("Cancelar"); btn_cancel.setStyleSheet(BTN_S)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("💾  Guardar"); btn_ok.setStyleSheet(BTN_P)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._guardar)
        bar.addWidget(btn_cancel); bar.addWidget(btn_ok)
        lay.addLayout(bar)

    def _guardar(self):
        nombre = self.e_nombre.text().strip() or self.e_email.text().strip()
        email  = self.e_email.text().strip()
        pw     = self.e_password.text().strip()
        if not email or "@" not in email:
            QMessageBox.warning(self, "Email inválido", "Introduce un email válido."); return
        if not pw or len(pw) < 10:
            QMessageBox.warning(self, "Contraseña inválida",
                                "La contraseña de aplicación debe tener al menos 10 caracteres."); return
        if self.gestor.agregar_cuenta(nombre, email, pw):
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Esta cuenta ya está guardada.")


class VentanaCuentasCorreo(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gestor = GestorCuentas()
        self.setWindowTitle("📧  Gestionar Cuentas de Correo")
        self.setMinimumSize(680, 440)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self._build()
        self._cargar()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)

        titulo = QLabel("📧  CUENTAS DE CORREO GUARDADAS")
        titulo.setStyleSheet("font-size:13px;font-weight:bold;color:#1F4E79;")
        lay.addWidget(titulo)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Nombre", "Email", "Activa"])
        self.table.setStyleSheet(TBL)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 80)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)

        bar = QHBoxLayout()
        for txt, fn, st in [
            ("➕ Nueva Cuenta",         self._nueva,   BTN_P),
            ("✅ Activar Seleccionada", self._activar, BTN_S),
            ("🗑️ Eliminar",             self._eliminar, BTN_D),
        ]:
            b = QPushButton(txt); b.setStyleSheet(st)
            b.setFixedHeight(34); b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch()
        btn_cerrar = QPushButton("Cerrar"); btn_cerrar.setStyleSheet(BTN_S)
        btn_cerrar.clicked.connect(self.accept)
        bar.addWidget(btn_cerrar)
        lay.addLayout(bar)

    def _cargar(self):
        self.table.setRowCount(0)
        for id_c, nombre, email, activa in self.gestor.obtener_todas_cuentas():
            row = self.table.rowCount(); self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(nombre or ""))
            self.table.setItem(row, 1, QTableWidgetItem(email))
            item = QTableWidgetItem("✓ Sí" if activa else "No")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, item)
            self.table.item(row, 0).setData(Qt.UserRole, id_c)

    def _sel_id(self):
        row = self.table.currentRow()
        if row < 0: return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _nueva(self):
        dlg = _NuevaCuentaDlg(self.gestor, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar()

    def _activar(self):
        id_c = self._sel_id()
        if id_c is None:
            QMessageBox.information(self, "Sin selección", "Selecciona una cuenta."); return
        self.gestor.establecer_cuenta_activa(id_c)
        self._cargar()
        QMessageBox.information(self, "Activada", "Cuenta activada. Se usará automáticamente.")

    def _eliminar(self):
        id_c = self._sel_id()
        if id_c is None:
            QMessageBox.information(self, "Sin selección", "Selecciona una cuenta."); return
        if QMessageBox.question(self, "Confirmar", "¿Eliminar esta cuenta?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.gestor.eliminar_cuenta(id_c)
            self._cargar()

    def closeEvent(self, event):
        self.gestor.cerrar()
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def abrir_gestor_cuentas(parent_widget=None):
    dlg = VentanaCuentasCorreo(parent=parent_widget)
    dlg.exec_()


def obtener_cuenta_activa() -> dict | None:
    gestor = GestorCuentas()
    cuenta = gestor.obtener_cuenta_activa()
    gestor.cerrar()
    if cuenta:
        return {"id": cuenta[0], "nombre": cuenta[1], "email": cuenta[2], "password": cuenta[3]}
    return None
