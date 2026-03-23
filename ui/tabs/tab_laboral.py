# -*- coding: utf-8 -*-
"""
Tab principal del módulo laboral.
Integrado en el sistema de tabs existente de la misma forma que tab_facturas,
tab_historial, etc.
Contiene sub-tabs: Empleados | Nóminas | Fichajes | Portal | Informes
"""
from __future__ import annotations
import os
from datetime import datetime, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QLabel,
    QComboBox, QFileDialog, QMessageBox, QFormLayout, QDateEdit,
    QCheckBox, QSpinBox, QGroupBox, QSplitter, QTextEdit, QScrollArea,
    QDialog, QDialogButtonBox, QProgressBar, QInputDialog,
    QSplitter, QSpinBox,
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from core.logging_config import get_logger
from ui.context_menu import add_context_menu

log = get_logger("ui.tab_laboral")

# ── Estilos consistentes con el resto de la app ──────────────────────────────
_BTN_PRI = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
            "padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#2B6CB0;}")
_BTN_SEC = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
            "border-radius:4px;padding:6px 10px;}"
            "QPushButton:hover{background:#E2E8F0;}")
_BTN_DNG = ("QPushButton{background:#C53030;color:white;border-radius:4px;"
            "padding:6px 10px;}QPushButton:hover{background:#9B2C2C;}")
_INP     = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
            "padding:5px 8px;background:white;color:#2D3748;}"
            "QLineEdit:focus{border:1px solid #3182CE;}")
_TABLE   = ("QTableWidget{border:1px solid #E2E8F0;gridline-color:#EDF2F7;"
            "selection-background-color:#EBF8FF;selection-color:#2D3748;}"
            "QHeaderView::section{background:#F7FAFC;border-bottom:2px solid #CBD5E0;"
            "padding:5px 6px;font-weight:bold;}")


# ── Worker para procesamiento de nóminas en hilo ──────────────────────────────

class _NominaWorker(QThread):
    log_signal  = pyqtSignal(str)
    done_signal = pyqtSignal(list)

    def __init__(self, pdf_path: str, db_laboral, enviar_email: bool,
                 carpeta: str, tesseract: str = None):
        super().__init__()
        self.pdf_path     = pdf_path
        self.db           = db_laboral
        self.enviar_email = enviar_email
        self.carpeta      = carpeta
        self.tesseract    = tesseract

    def run(self):
        from laboral.nominas.procesador import ProcesadorNominas
        try:
            proc = ProcesadorNominas(
                db_laboral=self.db,
                carpeta_base=self.carpeta,
                tesseract_path=self.tesseract,
                enviar_email=self.enviar_email,
                progress_cb=lambda m: self.log_signal.emit(m),
            )
            resultados = proc.procesar_pdf(self.pdf_path)
            self.done_signal.emit(resultados)
        except Exception as e:
            self.log_signal.emit(f"❌ Error: {e}")
            self.done_signal.emit([])


# ── Tab principal ─────────────────────────────────────────────────────────────

class TabLaboral(QWidget):
    """Tab del módulo laboral, insertado en el main_window igual que los demás."""

    def __init__(self, db=None, usuario=None, parent=None):
        super().__init__(parent)
        self.db_base  = db
        self.usuario  = usuario

        # Inicializar LaboralDB (crea tablas si no existen)
        from laboral.db_laboral import LaboralDB
        self.db = LaboralDB(db)

        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(self._tab_empleados(),  "👷  Empleados")
        tabs.addTab(self._tab_nominas(),    "💰  Nóminas")
        tabs.addTab(self._tab_fichajes(),   "🕐  Fichajes")
        tabs.addTab(self._tab_portal(),     "🌐  Portal")
        tabs.addTab(self._tab_calendario(), "📅  Calendario")
        tabs.addTab(self._tab_conceptos(),  "📒  Conceptos Nómina")
        tabs.addTab(self._tab_informes(),   "📊  Informes Laborales")

        lay.addWidget(tabs)

    # ── SUB-TAB: EMPLEADOS ────────────────────────────────────────────────────

    def _tab_empleados(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)

        # Barra de acciones
        bar = QHBoxLayout()
        btn_nuevo  = QPushButton("➕ Nuevo Empleado")
        btn_nuevo.setStyleSheet(_BTN_PRI)
        btn_editar = QPushButton("✏️ Editar")
        btn_editar.setStyleSheet(_BTN_SEC)
        btn_baja   = QPushButton("🔴 Dar de Baja")
        btn_baja.setStyleSheet(_BTN_DNG)
        btn_reac   = QPushButton("🟢 Reactivar")
        btn_reac.setStyleSheet(_BTN_SEC.replace("#EDF2F7","#C6F6D5").replace("#2D3748","#276749"))
        btn_eliminar = QPushButton("🗑 Eliminar")
        btn_eliminar.setStyleSheet(_BTN_DNG)
        btn_dispositivos = QPushButton("📱 Dispositivos")
        btn_dispositivos.setStyleSheet(_BTN_SEC)
        self._chk_ver_todos = QCheckBox("Ver todos (incl. baja/eliminados)")
        self._chk_ver_todos.toggled.connect(lambda: self.cargar_empleados())
        self._inp_buscar_emp = QLineEdit()
        self._inp_buscar_emp.setPlaceholderText("Buscar empleado...")
        self._inp_buscar_emp.setStyleSheet(_INP)
        self._inp_buscar_emp.setFixedWidth(200)
        self._inp_buscar_emp.textChanged.connect(self._filtrar_empleados)
        bar.addWidget(btn_nuevo); bar.addWidget(btn_editar)
        bar.addWidget(btn_baja); bar.addWidget(btn_reac)
        bar.addWidget(btn_eliminar); bar.addWidget(btn_dispositivos)
        bar.addWidget(self._chk_ver_todos); bar.addStretch()
        bar.addWidget(QLabel("🔍")); bar.addWidget(self._inp_buscar_emp)
        lay.addLayout(bar)

        # Tabla
        cols = ["ID", "Nombre", "Apellidos", "NIF", "Email",
                "Categoría", "Convenio", "Estado", "F. Incorporación"]
        self._tbl_emp = QTableWidget(0, len(cols))
        self._tbl_emp.setHorizontalHeaderLabels(cols)
        self._tbl_emp.setStyleSheet(_TABLE)
        self._tbl_emp.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_emp.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_emp.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_emp.verticalHeader().setVisible(False)
        lay.addWidget(self._tbl_emp)

        btn_nuevo.clicked.connect(lambda: self._dlg_empleado(None))
        btn_editar.clicked.connect(self._editar_empleado)
        btn_baja.clicked.connect(self._dar_baja_empleado)
        btn_reac.clicked.connect(self._reactivar_empleado)
        btn_eliminar.clicked.connect(self._eliminar_empleado)
        btn_dispositivos.clicked.connect(self._ver_dispositivos_empleado)

        self._tbl_emp.doubleClicked.connect(self._abrir_ficha_empleado)
        self.cargar_empleados()

        # Menú contextual empleados (botón derecho)
        add_context_menu(self._tbl_emp, [
            ("👤 Ver ficha",       lambda r: self._abrir_ficha_empleado()),
            ("✏️ Editar",          lambda r: self._editar_empleado()),
            (None, None),
            ("🟢 Reactivar",       lambda r: self._reactivar_empleado()),
            ("🔴 Dar de baja",     lambda r: self._dar_baja_empleado()),
            ("📱 Dispositivos",    lambda r: self._ver_dispositivos_empleado()),
            (None, None),
            ("🗑 Eliminar",        lambda r: self._eliminar_empleado()),
        ])
        return w

    def _abrir_ficha_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0: return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        emp = self.db.obtener_empleado(emp_id)
        if emp:
            from ui.tabs.laboral.ficha_empleado import FichaEmpleado
            dlg = FichaEmpleado(emp, self.db, parent=self)
            dlg.exec_()
            self.cargar_empleados()

    def cargar_empleados(self, filtro: str = ""):
        ver_todos = getattr(self, "_chk_ver_todos", None) and self._chk_ver_todos.isChecked()
        empleados = self.db.obtener_empleados_todos() if ver_todos else self.db.obtener_empleados()
        self._empleados_cache = empleados
        if filtro:
            f = filtro.lower()
            empleados = [e for e in empleados if
                         f in (e.get("nombre","") + " " + e.get("apellidos","")).lower() or
                         f in (e.get("nif") or "").lower()]
        _COLORES = {
            "baja":      "#FED7D7",
            "eliminado": "#E2E8F0",
            "activo":    "",
        }
        self._tbl_emp.setRowCount(0)
        for emp in empleados:
            r = self._tbl_emp.rowCount()
            self._tbl_emp.insertRow(r)
            vals = [str(emp.get("id","")), emp.get("nombre",""),
                    emp.get("apellidos",""), emp.get("nif",""),
                    emp.get("email",""), emp.get("categoria",""),
                    emp.get("convenio",""), emp.get("estado",""),
                    emp.get("fecha_incorporacion","")]
            color = _COLORES.get(emp.get("estado",""), "")
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, emp.get("id"))
                if color:
                    item.setBackground(QColor(color))
                self._tbl_emp.setItem(r, col, item)

    def _filtrar_empleados(self, texto: str):
        self.cargar_empleados(filtro=texto)

    def _editar_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un empleado")
            return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        emp = self.db.obtener_empleado(emp_id)
        self._dlg_empleado(emp)

    def _dar_baja_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0:
            return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        nombre = (self._tbl_emp.item(row, 1).text() + " " +
                  self._tbl_emp.item(row, 2).text())
        resp = QMessageBox.question(
            self, "Confirmar baja",
            f"¿Dar de baja a <b>{nombre}</b>?",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            hoy = date.today().isoformat()
            self.db.actualizar_empleado(emp_id, {
                "estado": "baja", "fecha_baja": hoy})
            self.cargar_empleados()

    def _reactivar_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un empleado"); return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        nombre = (self._tbl_emp.item(row, 1).text() + " " +
                  self._tbl_emp.item(row, 2).text())
        resp = QMessageBox.question(
            self, "Reactivar empleado",
            f"¿Reactivar a <b>{nombre}</b>?",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            self.db.reactivar_empleado(emp_id)
            self.cargar_empleados()

    def _eliminar_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un empleado"); return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        nombre = (self._tbl_emp.item(row, 1).text() + " " +
                  self._tbl_emp.item(row, 2).text())
        resp = QMessageBox.question(
            self, "Eliminar empleado",
            f"¿Eliminar <b>{nombre}</b>?\n\n"
            "El empleado quedará marcado como eliminado pero se conservará "
            "su historial (nóminas, fichajes, etc.).",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            self.db.eliminar_empleado(emp_id, definitivo=False)
            self.cargar_empleados()

    def _ver_dispositivos_empleado(self):
        row = self._tbl_emp.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un empleado"); return
        emp_id = self._tbl_emp.item(row, 0).data(Qt.UserRole)
        nombre = (self._tbl_emp.item(row, 1).text() + " " +
                  self._tbl_emp.item(row, 2).text())
        self._dlg_dispositivos(emp_id, nombre)

    def _dlg_dispositivos(self, empleado_id: int, nombre_empleado: str):
        """Diálogo de gestión de dispositivos asignados a un empleado."""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📱 Dispositivos — {nombre_empleado}")
        dlg.setMinimumSize(700, 480)
        lay = QVBoxLayout(dlg)

        # Tabla de dispositivos
        cols_d = ["Tipo", "Marca", "Modelo", "IMEI/Serie",
                  "Teléfono", "F.Entrega", "Estado", "Observaciones"]
        tbl = QTableWidget(0, len(cols_d))
        tbl.setHorizontalHeaderLabels(cols_d)
        tbl.setStyleSheet(_TABLE)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        lay.addWidget(tbl)

        def _cargar():
            dispositivos = self.db.obtener_dispositivos(empleado_id=empleado_id)
            tbl.setRowCount(0)
            for d in dispositivos:
                r = tbl.rowCount(); tbl.insertRow(r)
                vals = [d.get("tipo_dispositivo",""), d.get("marca",""),
                        d.get("modelo",""), d.get("imei") or d.get("numero_serie",""),
                        d.get("telefono_asociado",""), d.get("fecha_entrega",""),
                        d.get("estado",""), d.get("observaciones","") or ""]
                _DCOL = {"devuelto":"#C6F6D5","perdido":"#FED7D7","sustituido":"#FEFCBF"}
                color = _DCOL.get(d.get("estado",""), "")
                for col, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    if color:
                        item.setBackground(QColor(color))
                    tbl.setItem(r, col, item)
                    tbl.item(r, col).setData(Qt.UserRole, d.get("id"))

        _cargar()

        # Botones
        bar_d = QHBoxLayout()
        btn_add = QPushButton("➕ Añadir dispositivo"); btn_add.setStyleSheet(_BTN_PRI)
        btn_dev = QPushButton("✅ Marcar devuelto"); btn_dev.setStyleSheet(_BTN_SEC)
        btn_per = QPushButton("❌ Marcar perdido"); btn_per.setStyleSheet(_BTN_DNG)
        bar_d.addWidget(btn_add); bar_d.addWidget(btn_dev)
        bar_d.addWidget(btn_per); bar_d.addStretch()
        lay.addLayout(bar_d)

        def _add_dispositivo():
            d_dlg = QDialog(dlg)
            d_dlg.setWindowTitle("Nuevo dispositivo")
            d_dlg.setMinimumWidth(420)
            d_lay = QVBoxLayout(d_dlg)
            form  = QFormLayout()
            cmb_tipo = QComboBox()
            for t in ["telefono","tablet","portatil","otro"]:
                cmb_tipo.addItem(t)
            inp_marca  = QLineEdit(); inp_marca.setStyleSheet(_INP)
            inp_modelo = QLineEdit(); inp_modelo.setStyleSheet(_INP)
            inp_imei   = QLineEdit(); inp_imei.setStyleSheet(_INP)
            inp_serie  = QLineEdit(); inp_serie.setStyleSheet(_INP)
            inp_telf   = QLineEdit(); inp_telf.setStyleSheet(_INP)
            inp_ext    = QLineEdit(); inp_ext.setStyleSheet(_INP)
            inp_pin    = QLineEdit(); inp_pin.setStyleSheet(_INP)
            inp_obs    = QLineEdit(); inp_obs.setStyleSheet(_INP)
            form.addRow("Tipo:", cmb_tipo)
            form.addRow("Marca:", inp_marca)
            form.addRow("Modelo:", inp_modelo)
            form.addRow("IMEI:", inp_imei)
            form.addRow("Nº Serie:", inp_serie)
            form.addRow("Teléfono:", inp_telf)
            form.addRow("Extensión:", inp_ext)
            form.addRow("PIN:", inp_pin)
            form.addRow("Observaciones:", inp_obs)
            d_lay.addLayout(form)
            btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            btns.accepted.connect(d_dlg.accept)
            btns.rejected.connect(d_dlg.reject)
            d_lay.addWidget(btns)
            if d_dlg.exec_() == QDialog.Accepted:
                self.db.insertar_dispositivo({
                    "empleado_id":       empleado_id,
                    "tipo_dispositivo":  cmb_tipo.currentText(),
                    "marca":             inp_marca.text().strip() or None,
                    "modelo":            inp_modelo.text().strip() or None,
                    "imei":              inp_imei.text().strip() or None,
                    "numero_serie":      inp_serie.text().strip() or None,
                    "telefono_asociado": inp_telf.text().strip() or None,
                    "extension":         inp_ext.text().strip() or None,
                    "pin":               inp_pin.text().strip() or None,
                    "observaciones":     inp_obs.text().strip() or None,
                    "fecha_entrega":     date.today().isoformat(),
                    "estado":            "activo",
                })
                _cargar()

        def _cambiar_estado(nuevo_estado: str):
            row_d = tbl.currentRow()
            if row_d < 0:
                QMessageBox.information(dlg, "Info", "Selecciona un dispositivo"); return
            did = tbl.item(row_d, 0).data(Qt.UserRole)
            datos = {"estado": nuevo_estado}
            if nuevo_estado == "devuelto":
                datos["fecha_devolucion"] = date.today().isoformat()
            self.db.actualizar_dispositivo(did, datos)
            _cargar()

        btn_add.clicked.connect(_add_dispositivo)
        btn_dev.clicked.connect(lambda: _cambiar_estado("devuelto"))
        btn_per.clicked.connect(lambda: _cambiar_estado("perdido"))

        QDialogButtonBox(QDialogButtonBox.Close, parent=dlg).rejected.connect(dlg.reject)
        lay.addWidget(QDialogButtonBox(QDialogButtonBox.Close, parent=dlg))
        dlg.findChildren(QDialogButtonBox)[-1].rejected.connect(dlg.reject)
        dlg.exec_()

    def _dlg_empleado(self, emp: dict = None):
        """Diálogo de alta/edición de empleado."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Nuevo empleado" if emp is None else "Editar empleado")
        dlg.setMinimumWidth(500)
        lay = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contenido = QWidget()
        form = QFormLayout(contenido)
        form.setSpacing(8)
        scroll.setWidget(contenido)

        campos = {}
        def _inp(val=""):
            e = QLineEdit(str(val or ""))
            e.setStyleSheet(_INP)
            return e

        campos["nombre"]            = _inp(emp.get("nombre","") if emp else "")
        campos["apellidos"]         = _inp(emp.get("apellidos","") if emp else "")
        campos["nif"]               = _inp(emp.get("nif","") if emp else "")
        campos["email"]             = _inp(emp.get("email","") if emp else "")
        campos["telefono"]          = _inp(emp.get("telefono","") if emp else "")
        campos["direccion"]         = _inp(emp.get("direccion","") if emp else "")
        campos["numero_ss"]         = _inp(emp.get("numero_ss","") if emp else "")
        campos["categoria"]         = _inp(emp.get("categoria","") if emp else "")
        campos["convenio"]          = _inp(emp.get("convenio","") if emp else "")
        campos["dias_vacaciones"]   = _inp(emp.get("dias_vacaciones",22) if emp else 22)
        campos["contacto_nombre"]   = _inp(emp.get("contacto_nombre","") if emp else "")
        campos["contacto_telefono"] = _inp(emp.get("contacto_telefono","") if emp else "")
        campos["notas"]             = _inp(emp.get("notas","") if emp else "")

        chk_rgpd = QCheckBox("RGPD aceptado")
        chk_rgpd.setChecked(bool(emp.get("rgpd_aceptado",0)) if emp else False)

        form.addRow("Nombre *:",            campos["nombre"])
        form.addRow("Apellidos *:",         campos["apellidos"])
        form.addRow("NIF:",                 campos["nif"])
        form.addRow("Email:",               campos["email"])
        form.addRow("Teléfono:",            campos["telefono"])
        form.addRow("Dirección:",           campos["direccion"])
        form.addRow("Nº Seguridad Social:", campos["numero_ss"])
        form.addRow("Categoría:",           campos["categoria"])
        form.addRow("Convenio:",            campos["convenio"])
        form.addRow("Días vacaciones:",     campos["dias_vacaciones"])
        form.addRow("Contacto emerg.:",     campos["contacto_nombre"])
        form.addRow("Tel. contacto:",       campos["contacto_telefono"])
        form.addRow("Notas:",               campos["notas"])
        form.addRow("",                     chk_rgpd)

        lay.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        datos = {k: v.text().strip() for k, v in campos.items()}
        datos["rgpd_aceptado"] = 1 if chk_rgpd.isChecked() else 0
        if chk_rgpd.isChecked():
            datos["rgpd_fecha"] = date.today().isoformat()

        if not datos.get("nombre") or not datos.get("apellidos"):
            QMessageBox.warning(self, "Error", "Nombre y apellidos son obligatorios")
            return

        if emp:
            self.db.actualizar_empleado(emp["id"], datos)
            QMessageBox.information(self, "OK", "Empleado actualizado")
        else:
            datos["estado"] = "activo"
            datos["fecha_incorporacion"] = date.today().isoformat()
            eid = self.db.insertar_empleado(datos)
            QMessageBox.information(self, "OK", f"Empleado creado (ID {eid})")

        self.cargar_empleados()

    # ── SUB-TAB: NÓMINAS ──────────────────────────────────────────────────────

    def _tab_nominas(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)

        # Panel de procesamiento de PDF
        grp = QGroupBox("Procesar PDF de nóminas")
        glayout = QVBoxLayout(grp)

        r1 = QHBoxLayout()
        self._inp_nom_pdf = QLineEdit()
        self._inp_nom_pdf.setPlaceholderText("Ruta del PDF de nóminas...")
        self._inp_nom_pdf.setStyleSheet(_INP)
        btn_sel_pdf = QPushButton("📂 Seleccionar PDF")
        btn_sel_pdf.setStyleSheet(_BTN_SEC)
        btn_sel_pdf.clicked.connect(self._seleccionar_pdf_nominas)
        r1.addWidget(self._inp_nom_pdf); r1.addWidget(btn_sel_pdf)
        glayout.addLayout(r1)

        r2 = QHBoxLayout()
        self._chk_enviar_email = QCheckBox("Enviar nómina por email a cada empleado")
        self._chk_enviar_email.setChecked(False)
        btn_procesar = QPushButton("⚙️ Procesar nóminas")
        btn_procesar.setStyleSheet(_BTN_PRI)
        btn_procesar.clicked.connect(self._procesar_nominas)
        r2.addWidget(self._chk_enviar_email); r2.addStretch()
        r2.addWidget(btn_procesar)
        glayout.addLayout(r2)

        self._log_nominas = QTextEdit()
        self._log_nominas.setReadOnly(True)
        self._log_nominas.setMaximumHeight(120)
        self._log_nominas.setFont(QFont("Consolas", 8))
        glayout.addWidget(self._log_nominas)

        lay.addWidget(grp)

        # Tabla de nóminas
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Año:"))
        self._spn_nom_anio = QSpinBox()
        self._spn_nom_anio.setRange(2020, 2099)
        self._spn_nom_anio.setValue(datetime.now().year)
        bar.addWidget(self._spn_nom_anio)
        bar.addWidget(QLabel("Mes:"))
        self._cmb_nom_mes = QComboBox()
        self._cmb_nom_mes.addItem("Todos", 0)
        for m, nm in [(i, n) for i, n in {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",
                      5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",
                      10:"Octubre",11:"Noviembre",12:"Diciembre"}.items()]:
            self._cmb_nom_mes.addItem(nm, m)
        bar.addWidget(self._cmb_nom_mes)
        btn_filtrar = QPushButton("🔍 Filtrar")
        btn_filtrar.setStyleSheet(_BTN_SEC)
        btn_filtrar.clicked.connect(self.cargar_nominas)
        bar.addWidget(btn_filtrar); bar.addStretch()
        lay.addLayout(bar)

        cols = ["ID", "Empleado", "Mes", "Año", "Líquido", "SS Emp.", "Estado", "Enviada"]
        self._tbl_nom = QTableWidget(0, len(cols))
        self._tbl_nom.setHorizontalHeaderLabels(cols)
        self._tbl_nom.setStyleSheet(_TABLE)
        self._tbl_nom.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_nom.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_nom.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_nom.verticalHeader().setVisible(False)
        lay.addWidget(self._tbl_nom)

        self.cargar_nominas()

        # Menú contextual nóminas (botón derecho)
        add_context_menu(self._tbl_nom, [
            ("👁 Ver PDF",         lambda r: self._ver_nomina_pdf(r)),
            ("📧 Reenviar email",  lambda r: self._reenviar_nomina(r)),
            (None, None),
            ("🗑 Eliminar nómina", lambda r: self._eliminar_nomina(r)),
        ])
        return w

    def _seleccionar_pdf_nominas(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar PDF de nóminas", "", "PDF (*.pdf)")
        if ruta:
            self._inp_nom_pdf.setText(ruta)

    def _log_nom(self, msg: str):
        self._log_nominas.append(msg)

    def _procesar_nominas(self):
        ruta = self._inp_nom_pdf.text().strip()
        if not ruta or not Path(ruta).exists():
            QMessageBox.warning(self, "Error", "Selecciona un PDF válido")
            return
        try:
            from core.config_loader import get_config
            tesseract = get_config().tesseract_path
        except Exception:
            tesseract = None
        carpeta = self.db._db.get_config_ui("carpeta_empleados", "./Empleados")
        enviar  = self._chk_enviar_email.isChecked()

        self._log_nominas.clear()
        self._log_nom("🚀 Iniciando procesamiento de nóminas...")
        self._worker_nom = _NominaWorker(ruta, self.db, enviar, carpeta, tesseract)
        self._worker_nom.log_signal.connect(self._log_nom)
        self._worker_nom.done_signal.connect(self._on_nominas_procesadas)
        self._worker_nom.start()

    def _on_nominas_procesadas(self, resultados: list):
        ok  = [r for r in resultados if "error" not in r]
        err = [r for r in resultados if "error" in r]
        self._log_nom(f"✅ {len(ok)} nóminas procesadas | ❌ {len(err)} errores")
        for r in err:
            self._log_nom(f"  ❌ {r.get('empleado','?')}: {r.get('error')}")
        self.cargar_nominas()

    def cargar_nominas(self):
        anio = self._spn_nom_anio.value()
        mes  = self._cmb_nom_mes.currentData()
        nominas = self.db.obtener_nominas(
            anio=anio, mes=mes if mes else None)
        self._tbl_nom.setRowCount(0)
        _MESES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",
                  6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",
                  10:"Octubre",11:"Noviembre",12:"Diciembre"}
        for n in nominas:
            r = self._tbl_nom.rowCount()
            self._tbl_nom.insertRow(r)
            vals = [str(n.get("id","")), n.get("nombre_empleado",""),
                    _MESES.get(n.get("mes",0),""), str(n.get("anio","")),
                    f"{n.get('liquido',0):.2f} €", f"{n.get('ss_empresa',0):.2f} €",
                    n.get("estado",""), "✅" if n.get("enviada_email") else ""]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if col == 0:
                    it.setData(Qt.UserRole, n.get("id"))
                self._tbl_nom.setItem(r, col, it)

    # ── SUB-TAB: FICHAJES ─────────────────────────────────────────────────────

    def _tab_fichajes(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)

        # ── Fichaje rápido (entrada/salida desde programa) ────────────────
        grp_fich = QGroupBox("🕐 Fichaje desde programa")
        gf = QVBoxLayout(grp_fich)
        r_emp = QHBoxLayout()
        r_emp.addWidget(QLabel("Empleado:"))
        self._cmb_fichar_emp = QComboBox()
        self._cmb_fichar_emp.addItem("— seleccionar —", 0)
        for emp in self.db.obtener_empleados(solo_activos=True):
            self._cmb_fichar_emp.addItem(
                f"{emp['apellidos']}, {emp['nombre']}", emp["id"])
        r_emp.addWidget(self._cmb_fichar_emp); r_emp.addStretch()
        gf.addLayout(r_emp)

        r_btns = QHBoxLayout()
        btn_entrada = QPushButton("🟢 Registrar Entrada")
        btn_entrada.setStyleSheet(_BTN_PRI.replace("#1F4E79","#276749").replace("#2B6CB0","#22543D"))
        btn_entrada.clicked.connect(self._fichar_entrada)
        btn_salida = QPushButton("🔴 Registrar Salida")
        btn_salida.setStyleSheet(_BTN_PRI.replace("#1F4E79","#C53030").replace("#2B6CB0","#9B2C2C"))
        btn_salida.clicked.connect(self._fichar_salida)
        self._lbl_fichaje_estado = QLabel("")
        self._lbl_fichaje_estado.setStyleSheet("font-weight:bold;font-size:11px;padding:4px 8px;border-radius:4px;")
        r_btns.addWidget(btn_entrada); r_btns.addWidget(btn_salida)
        r_btns.addStretch(); r_btns.addWidget(self._lbl_fichaje_estado)
        gf.addLayout(r_btns)
        lay.addWidget(grp_fich)

        # ── Vista diaria ──────────────────────────────────────────────────
        grp_hoy = QGroupBox("📅 Estado del día")
        gh = QVBoxLayout(grp_hoy)
        r_fecha_hoy = QHBoxLayout()
        self._dt_vista_dia = QDateEdit(QDate.currentDate())
        self._dt_vista_dia.setCalendarPopup(True)
        self._dt_vista_dia.setDisplayFormat("dd/MM/yyyy")
        self._dt_vista_dia.lineEdit().setReadOnly(False)
        btn_actualizar_hoy = QPushButton("🔄 Actualizar")
        btn_actualizar_hoy.setStyleSheet(_BTN_SEC)
        btn_actualizar_hoy.clicked.connect(self._cargar_vista_diaria)
        r_fecha_hoy.addWidget(QLabel("Fecha:")); r_fecha_hoy.addWidget(self._dt_vista_dia)
        r_fecha_hoy.addWidget(btn_actualizar_hoy); r_fecha_hoy.addStretch()
        gh.addLayout(r_fecha_hoy)

        cols_dia = ["Empleado", "Entrada", "Salida", "Minutos", "Estado"]
        self._tbl_dia = QTableWidget(0, len(cols_dia))
        self._tbl_dia.setHorizontalHeaderLabels(cols_dia)
        self._tbl_dia.setStyleSheet(_TABLE)
        self._tbl_dia.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_dia.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_dia.verticalHeader().setVisible(False)
        self._tbl_dia.setFixedHeight(160)
        gh.addWidget(self._tbl_dia)
        lay.addWidget(grp_hoy)

        # ── Importar / sincronizar ZKTeco ─────────────────────────────────
        grp_zk = QGroupBox("📡 ZKTeco — Importar / Sincronizar")
        gz = QHBoxLayout(grp_zk)
        btn_csv = QPushButton("📄 Importar CSV")
        btn_csv.setStyleSheet(_BTN_SEC); btn_csv.clicked.connect(self._importar_csv_fichajes)
        btn_xls = QPushButton("📊 Importar Excel")
        btn_xls.setStyleSheet(_BTN_SEC); btn_xls.clicked.connect(self._importar_excel_fichajes)
        btn_api = QPushButton("📡 Descargar fichajes")
        btn_api.setStyleSheet(_BTN_PRI); btn_api.clicked.connect(self._conectar_zkteco)
        btn_sync = QPushButton("👥 Sincronizar empleados")
        btn_sync.setStyleSheet(_BTN_SEC); btn_sync.clicked.connect(self._sync_empleados_zkteco)
        gz.addWidget(btn_csv); gz.addWidget(btn_xls)
        btn_desc_emp = QPushButton("⬇️ Descargar empleados ZKTeco")
        btn_desc_emp.setStyleSheet(_BTN_SEC); btn_desc_emp.clicked.connect(self._descargar_empleados_zkteco)
        btn_zktime = QPushButton("📂 Importar ZKTime")
        btn_zktime.setStyleSheet(_BTN_SEC); btn_zktime.clicked.connect(self._importar_zktime)
        gz.addWidget(btn_api); gz.addWidget(btn_sync)
        gz.addWidget(btn_desc_emp); gz.addWidget(btn_zktime); gz.addStretch()
        lay.addWidget(grp_zk)

        # ── Vista mensual filtrada ─────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Empleado:"))
        self._cmb_fich_emp = QComboBox()
        self._cmb_fich_emp.addItem("Todos", 0)
        for emp in self.db.obtener_empleados(solo_activos=True):
            self._cmb_fich_emp.addItem(f"{emp['apellidos']}, {emp['nombre']}", emp["id"])
        bar.addWidget(self._cmb_fich_emp)
        bar.addWidget(QLabel("Desde:"))
        self._dt_fich_desde = QDateEdit(QDate(QDate.currentDate().year(), 1, 1))
        self._dt_fich_desde.setCalendarPopup(True); self._dt_fich_desde.setDisplayFormat("dd/MM/yyyy")
        self._dt_fich_desde.lineEdit().setReadOnly(False)
        bar.addWidget(self._dt_fich_desde)
        bar.addWidget(QLabel("Hasta:"))
        self._dt_fich_hasta = QDateEdit(QDate.currentDate())
        self._dt_fich_hasta.setCalendarPopup(True); self._dt_fich_hasta.setDisplayFormat("dd/MM/yyyy")
        self._dt_fich_hasta.lineEdit().setReadOnly(False)
        bar.addWidget(self._dt_fich_hasta)
        btn_filtrar_fich = QPushButton("🔍 Filtrar")
        btn_filtrar_fich.setStyleSheet(_BTN_SEC); btn_filtrar_fich.clicked.connect(self.cargar_fichajes)
        btn_informe = QPushButton("📊 Informe mes")
        btn_informe.setStyleSheet(_BTN_SEC); btn_informe.clicked.connect(self._informe_mes_fichajes)
        bar.addWidget(btn_filtrar_fich); bar.addWidget(btn_informe); bar.addStretch()
        lay.addLayout(bar)

        cols = ["Empleado", "Fecha", "Entrada", "Salida", "Minutos", "Tipo", "Origen", "Obs."]
        self._tbl_fich = QTableWidget(0, len(cols))
        self._tbl_fich.setHorizontalHeaderLabels(cols)
        self._tbl_fich.setStyleSheet(_TABLE)
        self._tbl_fich.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_fich.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_fich.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_fich.verticalHeader().setVisible(False)
        lay.addWidget(self._tbl_fich)

        self.cargar_fichajes()
        self._cargar_vista_diaria()
        return w

    # ── Fichaje desde programa ────────────────────────────────────────────────

    def _fichar_entrada(self):
        emp_id = self._cmb_fichar_emp.currentData()
        if not emp_id:
            QMessageBox.warning(self, "Info", "Selecciona un empleado")
            return
        from laboral.fichajes.fichaje_directo import fichar_entrada
        res = fichar_entrada(self.db, emp_id)
        if res["ok"]:
            msg = f"✅ Entrada registrada: {res['hora']}"
            if res.get("retraso"):
                msg += " ⚠️ RETRASO"
            color = "#FED7AA" if res.get("retraso") else "#C6F6D5"
        else:
            msg = f"ℹ️ {res['msg']}"
            color = "#E2E8F0"
        self._lbl_fichaje_estado.setText(msg)
        self._lbl_fichaje_estado.setStyleSheet(
            f"font-weight:bold;font-size:11px;padding:4px 8px;"
            f"border-radius:4px;background:{color};")
        self.cargar_fichajes()
        self._cargar_vista_diaria()

    def _fichar_salida(self):
        emp_id = self._cmb_fichar_emp.currentData()
        if not emp_id:
            QMessageBox.warning(self, "Info", "Selecciona un empleado")
            return
        from laboral.fichajes.fichaje_directo import fichar_salida
        res = fichar_salida(self.db, emp_id)
        if res["ok"]:
            h = int(res["minutos"] / 60); m = res["minutos"] % 60
            msg = f"✅ Salida: {res['hora']} | {h}h {m}min trabajados"
            if res.get("jornada_incompleta"):
                msg += " ⚠️ JORNADA INCOMPLETA"
            color = "#FED7AA" if res.get("jornada_incompleta") else "#C6F6D5"
        else:
            msg = f"ℹ️ {res['msg']}"
            color = "#E2E8F0"
        self._lbl_fichaje_estado.setText(msg)
        self._lbl_fichaje_estado.setStyleSheet(
            f"font-weight:bold;font-size:11px;padding:4px 8px;"
            f"border-radius:4px;background:{color};")
        self.cargar_fichajes()
        self._cargar_vista_diaria()

    def _cargar_vista_diaria(self):
        fecha = self._dt_vista_dia.date().toString("yyyy-MM-dd")
        from laboral.fichajes.fichaje_directo import vista_diaria
        filas = vista_diaria(self.db, fecha)
        self._tbl_dia.setRowCount(0)
        _COLORES = {"ausente": "#FED7D7", "trabajando": "#C6F6D5", "completado": "#BEE3F8"}
        for f in filas:
            r = self._tbl_dia.rowCount()
            self._tbl_dia.insertRow(r)
            mins = f.get("minutos", 0)
            h, m = divmod(mins, 60)
            tiempo_str = f"{h}h {m}min" if mins else ""
            vals = [f["nombre"], f["entrada"], f["salida"], tiempo_str, f["estado"]]
            color = _COLORES.get(f["estado"], "")
            for col, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if color:
                    from PyQt5.QtGui import QColor
                    item.setBackground(QColor(color))
                self._tbl_dia.setItem(r, col, item)

    def cargar_fichajes(self):
        emp_id = self._cmb_fich_emp.currentData() or None
        desde  = self._dt_fich_desde.date().toString("yyyy-MM-dd")
        hasta  = self._dt_fich_hasta.date().toString("yyyy-MM-dd")
        fichajes = self.db.obtener_fichajes(
            empleado_id=emp_id, fecha_desde=desde, fecha_hasta=hasta)
        self._tbl_fich.setRowCount(0)
        for f in fichajes:
            r = self._tbl_fich.rowCount()
            self._tbl_fich.insertRow(r)
            fecha_raw = f.get("fecha", "")
            try:
                from datetime import datetime as _dt
                fecha_es = _dt.strptime(fecha_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_es = fecha_raw
            mins = f.get("minutos_trabajados") or 0
            h, m = divmod(mins, 60)
            tiempo_str = f"{h}h {m}min" if mins else ""
            vals = [f.get("nombre_empleado",""), fecha_es,
                    f.get("hora_entrada",""), f.get("hora_salida","") or "",
                    tiempo_str, f.get("tipo",""), f.get("origen",""),
                    f.get("observaciones","") or ""]
            for col, v in enumerate(vals):
                self._tbl_fich.setItem(r, col, QTableWidgetItem(str(v)))

    def _informe_mes_fichajes(self):
        emp_id = self._cmb_fich_emp.currentData()
        if not emp_id:
            QMessageBox.information(self, "Info", "Selecciona un empleado para el informe mensual")
            return
        desde = self._dt_fich_desde.date()
        from laboral.fichajes.fichaje_directo import analizar_mes
        res = analizar_mes(self.db, emp_id, desde.year(), desde.month())
        msg = (
            f"Empleado: {res['empleado']}\n"
            f"Período: {res['periodo']}\n\n"
            f"Días laborables: {res['dias_laborables']}\n"
            f"Días trabajados: {res['dias_trabajados']}\n"
            f"Ausencias:       {res['ausencias']}\n"
            f"Retrasos:        {res['retrasos']}\n"
            f"Jornadas incompletas: {res['jornadas_incompletas']}\n\n"
            f"Horas trabajadas: {res['horas_trabajadas']}h\n"
            f"Horas esperadas:  {res['horas_esperadas']}h\n"
            f"Diferencia:       {res['diferencia_horas']:+.2f}h"
        )
        QMessageBox.information(self, f"Informe {res['periodo']}", msg)

    def _importar_csv_fichajes(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Importar CSV de fichajes ZKTeco", "", "CSV (*.csv *.txt)")
        if not ruta:
            return
        from laboral.fichajes.zkteco import ImportadorFichajesCSV
        imp = ImportadorFichajesCSV(self.db)
        res = imp.importar_csv(ruta)
        QMessageBox.information(self, "Importación completada",
            f"Importados: {res.get('importados',0)}\n"
            f"Duplicados: {res.get('duplicados',0)}\nErrores: {res.get('errores',0)}")
        self.cargar_fichajes()

    def _importar_excel_fichajes(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Importar Excel de fichajes ZKTeco", "", "Excel (*.xlsx *.xls)")
        if not ruta:
            return
        from laboral.fichajes.zkteco import ImportadorFichajesCSV
        imp = ImportadorFichajesCSV(self.db)
        res = imp.importar_excel(ruta)
        QMessageBox.information(self, "Importación completada",
            f"Importados: {res.get('importados',0)}\nErrores: {res.get('errores',0)}")
        self.cargar_fichajes()

    def _conectar_zkteco(self):
        cfg = self.db.get_zkteco_config()
        dlg = QDialog(self)
        dlg.setWindowTitle("Descargar fichajes ZKTeco")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        inp_ip  = QLineEdit(cfg.get("ip",""))
        inp_ip.setStyleSheet(_INP)
        inp_pto = QSpinBox(); inp_pto.setRange(1, 65535)
        inp_pto.setValue(cfg.get("puerto", 4370))
        chk_borrar = QCheckBox("Borrar registros del terminal tras importar")
        form.addRow("IP del terminal:", inp_ip)
        form.addRow("Puerto:", inp_pto)
        form.addRow("", chk_borrar)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return
        ip = inp_ip.text().strip(); pto = inp_pto.value()
        if not ip:
            QMessageBox.warning(self, "Error", "Introduce la IP del terminal"); return
        self.db.set_zkteco_config(ip, pto, "admin", "", True)
        from laboral.fichajes.zkteco import ConectorZKTeco
        conector = ConectorZKTeco(ip, pto)
        if conector.conectar():
            res = conector.descargar_fichajes(self.db)
            if chk_borrar.isChecked():
                conector.borrar_registros_terminal()
            QMessageBox.information(self, "ZKTeco",
                f"Importados: {res.get('importados',0)} fichajes\nErrores: {res.get('errores',0)}")
            self.cargar_fichajes()
        else:
            QMessageBox.warning(self, "Error",
                "No se pudo conectar al terminal.\n"
                "Verifica IP, puerto y que pyzk esté instalado:\npip install pyzk")

    def _sync_empleados_zkteco(self):
        cfg = self.db.get_zkteco_config()
        ip  = cfg.get("ip", "")
        if not ip:
            ip, ok = QInputDialog.getText(self, "IP ZKTeco", "IP del terminal:")
            if not ok or not ip:
                return
        from laboral.fichajes.fichaje_directo import sincronizar_empleados_zkteco
        res = sincronizar_empleados_zkteco(self.db, ip, cfg.get("puerto", 4370))
        if "error" in res:
            QMessageBox.warning(self, "Error", res["error"]); return
        msg = (f"En terminal: {res['en_terminal']}\n"
               f"En BD: {res['en_bd']}\n"
               f"Empleados nuevos (en terminal, no en BD): {res['nuevos_bd']}\n"
               f"Sin terminal (activos en BD): {res['no_en_terminal']}")
        QMessageBox.information(self, "Sincronización completada", msg)

    def _descargar_empleados_zkteco(self):
        """Descarga empleados del terminal ZKTeco e importa los que no existen en BD."""
        cfg = self.db.get_zkteco_config()
        ip  = cfg.get("ip", "")
        if not ip:
            ip, ok = QInputDialog.getText(self, "IP ZKTeco", "IP del terminal:")
            if not ok or not ip:
                return
        from laboral.fichajes.zkteco import DescargaEmpleadosZKTeco
        desc = DescargaEmpleadosZKTeco(ip, cfg.get("puerto", 4370))
        res_desc = desc.obtener_empleados_terminal()
        if "error" in res_desc:
            QMessageBox.warning(self, "Error", res_desc["error"]); return
        empleados_zk = res_desc.get("empleados", [])
        if not empleados_zk:
            QMessageBox.information(self, "ZKTeco", "No se encontraron empleados en el terminal.")
            return
        # Preguntar si importar
        resp = QMessageBox.question(
            self, "Empleados ZKTeco",
            f"Se encontraron {len(empleados_zk)} empleados en el terminal.\n"
            "¿Importar los que no estén en la base de datos?",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            res_imp = desc.importar_a_bd(self.db, empleados_zk)
            QMessageBox.information(
                self, "Importación completada",
                f"Importados: {res_imp['importados']}\n"
                f"Ya existían: {res_imp['ya_existian']}")
            self.cargar_empleados()

    def _importar_zktime(self):
        """Importa exportaciones del software ZKTime (empleados o fichajes)."""
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar exportación ZKTime", "",
            "Archivos ZKTime (*.csv *.xlsx *.xls *.txt)")
        if not ruta:
            return
        from laboral.fichajes.zkteco import ImportadorZKTime
        imp = ImportadorZKTime(self.db)
        ext = ruta.lower().rsplit(".", 1)[-1]
        if ext in ("xlsx", "xls"):
            res = imp.importar_excel(ruta)
        else:
            res = imp.importar_csv(ruta)

        if "error" in res:
            QMessageBox.warning(self, "Error ZKTime", res["error"]); return

        tipo = res.get("tipo", "desconocido")
        msg  = (f"Tipo detectado: {tipo}\n"
                f"Importados: {res.get('importados', 0)}\n"
                f"Ya existían: {res.get('ya_existian', 0)}\n"
                f"Errores: {res.get('errores', 0)}")
        QMessageBox.information(self, "Importación ZKTime completada", msg)
        # Recargar según tipo
        if tipo == "empleados":
            self.cargar_empleados()
        else:
            self.cargar_fichajes()

    # ── SUB-TAB: PORTAL ───────────────────────────────────────────────────────

    def _tab_portal(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Portal del Empleado</b>"))

        # Anuncios
        grp_anuncios = QGroupBox("Anuncios activos")
        ga = QVBoxLayout(grp_anuncios)
        self._lst_anuncios = QTextEdit()
        self._lst_anuncios.setReadOnly(True)
        self._lst_anuncios.setMaximumHeight(100)
        ga.addWidget(self._lst_anuncios)
        btn_anuncio = QPushButton("📢 Publicar anuncio")
        btn_anuncio.setStyleSheet(_BTN_SEC)
        btn_anuncio.clicked.connect(self._publicar_anuncio)
        ga.addWidget(btn_anuncio)
        lay.addWidget(grp_anuncios)

        # Mensajes
        grp_msg = QGroupBox("Buzón (sugerencias / denuncias)")
        gm = QVBoxLayout(grp_msg)
        cols_msg = ["Empleado", "Tipo", "Asunto", "Fecha", "Leído"]
        self._tbl_msg = QTableWidget(0, len(cols_msg))
        self._tbl_msg.setHorizontalHeaderLabels(cols_msg)
        self._tbl_msg.setStyleSheet(_TABLE)
        self._tbl_msg.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_msg.setMaximumHeight(150)
        gm.addWidget(self._tbl_msg)
        lay.addWidget(grp_msg)

        # Documentos por empleado
        grp_docs = QGroupBox("Documentos por empleado")
        gd = QVBoxLayout(grp_docs)
        bar_d = QHBoxLayout()
        self._cmb_portal_emp = QComboBox()
        self._cmb_portal_emp.addItem("Todos", 0)
        for emp in self.db.obtener_empleados(solo_activos=True):
            self._cmb_portal_emp.addItem(
                f"{emp['apellidos']}, {emp['nombre']}", emp["id"])
        self._cmb_portal_emp.currentIndexChanged.connect(self.cargar_docs_portal)
        btn_subir = QPushButton("⬆️ Subir documento")
        btn_subir.setStyleSheet(_BTN_SEC)
        btn_subir.clicked.connect(self._subir_doc_portal)
        bar_d.addWidget(self._cmb_portal_emp); bar_d.addStretch()
        bar_d.addWidget(btn_subir)
        gd.addLayout(bar_d)
        cols_docs = ["Tipo", "Título", "Fecha", "Ruta"]
        self._tbl_docs = QTableWidget(0, len(cols_docs))
        self._tbl_docs.setHorizontalHeaderLabels(cols_docs)
        self._tbl_docs.setStyleSheet(_TABLE)
        self._tbl_docs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        gd.addWidget(self._tbl_docs)
        lay.addWidget(grp_docs)

        # ── App móvil — servidor API ──────────────────────────────────────────
        grp_api = QGroupBox("📱 App Móvil de Fichaje — Servidor API")
        grp_api.setStyleSheet("QGroupBox{color:#1F4E79;font-weight:bold;}")
        ga2 = QVBoxLayout(grp_api)

        r_api = QHBoxLayout()
        self._lbl_api_estado = QLabel("⚪ Servidor detenido")
        self._lbl_api_estado.setStyleSheet("font-weight:bold;padding:4px 8px;"
                                            "background:#EDF2F7;border-radius:4px;")
        self._lbl_api_url = QLabel("")
        self._lbl_api_url.setStyleSheet("color:#2B6CB0;font-size:10px;")
        btn_api_start = QPushButton("▶ Iniciar servidor API")
        btn_api_start.setStyleSheet(_BTN_PRI)
        btn_api_start.clicked.connect(self._iniciar_api_movil)
        btn_api_stop = QPushButton("⏹ Detener")
        btn_api_stop.setStyleSheet(_BTN_DNG)
        btn_api_stop.clicked.connect(self._detener_api_movil)
        r_api.addWidget(self._lbl_api_estado)
        r_api.addWidget(self._lbl_api_url)
        r_api.addStretch()
        r_api.addWidget(btn_api_start)
        r_api.addWidget(btn_api_stop)
        ga2.addLayout(r_api)

        info_api = QLabel(
            "El servidor API permite a los empleados fichar desde la app móvil.\n"
            "La app se conecta a la URL mostrada. Asegúrate de que el firewall "
            "permita el puerto 8765."
        )
        info_api.setStyleSheet("color:#666;font-size:9px;")
        info_api.setWordWrap(True)
        ga2.addWidget(info_api)

        # Tokens activos
        r_tok = QHBoxLayout()
        btn_gen_token = QPushButton("🔑 Generar token empleado")
        btn_gen_token.setStyleSheet(_BTN_SEC)
        btn_gen_token.clicked.connect(self._generar_token_empleado)
        r_tok.addWidget(btn_gen_token); r_tok.addStretch()
        ga2.addLayout(r_tok)

        lay.addWidget(grp_api)

        self._api_server = None  # instancia ApiMovilServer

        self._cargar_anuncios()
        self.cargar_docs_portal()
        return w

    def _iniciar_api_movil(self):
        if getattr(self, "_api_server", None) and self._api_server.running:
            QMessageBox.information(self, "API", "El servidor ya está en ejecución.")
            return
        try:
            from laboral.api_movil import ApiMovilServer
            self._api_server = ApiMovilServer(db_laboral=self.db)
            ok = self._api_server.start()
            if ok:
                url = self._api_server.url
                self._lbl_api_estado.setText("🟢 Servidor activo")
                self._lbl_api_estado.setStyleSheet(
                    "font-weight:bold;padding:4px 8px;background:#C6F6D5;border-radius:4px;")
                self._lbl_api_url.setText(f"  URL: {url}/api/v1/")
            else:
                QMessageBox.warning(self, "Error", "No se pudo iniciar el servidor API.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error iniciando API: {e}")

    def _detener_api_movil(self):
        if getattr(self, "_api_server", None):
            self._api_server.stop()
            self._api_server = None
        self._lbl_api_estado.setText("⚪ Servidor detenido")
        self._lbl_api_estado.setStyleSheet(
            "font-weight:bold;padding:4px 8px;background:#EDF2F7;border-radius:4px;")
        self._lbl_api_url.setText("")

    def _generar_token_empleado(self):
        empleados = self.db.obtener_empleados(solo_activos=True)
        if not empleados:
            QMessageBox.information(self, "Info", "No hay empleados activos."); return
        dlg = QDialog(self)
        dlg.setWindowTitle("Generar token app móvil")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        cmb_emp = QComboBox()
        for emp in empleados:
            cmb_emp.addItem(f"{emp['apellidos']}, {emp['nombre']}", emp["id"])
        inp_disp = QLineEdit(); inp_disp.setStyleSheet(_INP)
        inp_disp.setPlaceholderText("Ej: iPhone Juan, Android María")
        form.addRow("Empleado:", cmb_emp)
        form.addRow("Dispositivo:", inp_disp)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return
        emp_id = cmb_emp.currentData()
        disp   = inp_disp.text().strip() or "app_movil"
        token  = self.db.generar_token_empleado(emp_id, disp)
        # Mostrar token en diálogo copiable
        dlg2 = QDialog(self)
        dlg2.setWindowTitle("Token generado")
        dlg2.setMinimumWidth(420)
        lay2 = QVBoxLayout(dlg2)
        lay2.addWidget(QLabel("Comparte este token con el empleado para configurar la app:"))
        inp_tok = QLineEdit(token); inp_tok.setReadOnly(True)
        inp_tok.setStyleSheet("font-family:monospace;font-size:11px;padding:6px;")
        lay2.addWidget(inp_tok)
        url = getattr(self._api_server, "url", "http://IP_LOCAL:8765") if getattr(self, "_api_server", None) else "http://IP_LOCAL:8765"
        lay2.addWidget(QLabel(f"URL del servidor: {url}"))
        lay2.addWidget(QDialogButtonBox(QDialogButtonBox.Ok, parent=dlg2))
        dlg2.findChildren(QDialogButtonBox)[0].accepted.connect(dlg2.accept)
        dlg2.exec_()

    def _cargar_anuncios(self):
        anuncios = self.db.obtener_anuncios_activos()
        self._lst_anuncios.clear()
        for a in anuncios:
            tipo = "🔴" if a.get("tipo") == "urgente" else "📢"
            self._lst_anuncios.append(
                f"{tipo} <b>{a.get('titulo')}</b>: {a.get('cuerpo','')[:80]}")

    def _publicar_anuncio(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Publicar anuncio")
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        inp_tit  = QLineEdit(); inp_tit.setStyleSheet(_INP)
        inp_cuerpo = QTextEdit()
        cmb_tipo = QComboBox()
        cmb_tipo.addItems(["anuncio", "urgente", "protocolo"])
        form.addRow("Título:", inp_tit)
        form.addRow("Texto:", inp_cuerpo)
        form.addRow("Tipo:", cmb_tipo)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            self.db.cursor.execute("""
                INSERT INTO laboral_portal_anuncios(titulo,cuerpo,tipo,activo)
                VALUES(?,?,?,1)""",
                (inp_tit.text().strip(), inp_cuerpo.toPlainText().strip(),
                 cmb_tipo.currentText()))
            self.db.conn.commit()
            self._cargar_anuncios()

    def cargar_docs_portal(self):
        emp_id = self._cmb_portal_emp.currentData() or None
        docs   = self.db.obtener_documentos_portal(empleado_id=emp_id)
        self._tbl_docs.setRowCount(0)
        for d in docs:
            r = self._tbl_docs.rowCount()
            self._tbl_docs.insertRow(r)
            for col, v in enumerate([d.get("tipo",""), d.get("titulo",""),
                                      (d.get("fecha_subida","") or "")[:10],
                                      d.get("ruta","")]):
                self._tbl_docs.setItem(r, col, QTableWidgetItem(str(v)))

    def _subir_doc_portal(self):
        emp_id = self._cmb_portal_emp.currentData()
        if not emp_id:
            QMessageBox.warning(self, "Info", "Selecciona un empleado primero")
            return
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar documento", "", "PDF (*.pdf)")
        if not ruta:
            return
        titulo, ok = QFileDialog.getOpenFileName(self, "Título del documento", "", "")
        titulo = Path(ruta).stem
        self.db.insertar_documento_portal({
            "empleado_id": emp_id, "tipo": "otro",
            "titulo": titulo, "ruta": ruta
        })
        self.cargar_docs_portal()

    # ── SUB-TAB: INFORMES ─────────────────────────────────────────────────────

    # ── SUB-TAB: CALENDARIO LABORAL ──────────────────────────────────────────

    def _tab_calendario(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Calendario Laboral</b>"))

        # Filtros
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Año:"))
        self._spn_cal_anio = QSpinBox()
        self._spn_cal_anio.setRange(2020, 2099)
        self._spn_cal_anio.setValue(datetime.now().year)
        bar.addWidget(self._spn_cal_anio)
        bar.addWidget(QLabel("Mes:"))
        self._cmb_cal_mes = QComboBox()
        for m, nm in [(i, n) for i, n in {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",
                      5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",
                      10:"Octubre",11:"Noviembre",12:"Diciembre"}.items()]:
            self._cmb_cal_mes.addItem(nm, m)
        self._cmb_cal_mes.setCurrentIndex(datetime.now().month - 1)
        bar.addWidget(self._cmb_cal_mes)
        bar.addWidget(QLabel("Empleado:"))
        self._cmb_cal_emp = QComboBox()
        self._cmb_cal_emp.addItem("Global (empresa)", 0)
        for emp in self.db.obtener_empleados(solo_activos=True):
            self._cmb_cal_emp.addItem(f"{emp['apellidos']}, {emp['nombre']}", emp["id"])
        bar.addWidget(self._cmb_cal_emp)
        btn_ver = QPushButton("📅 Ver calendario")
        btn_ver.setStyleSheet(_BTN_SEC); btn_ver.clicked.connect(self._cargar_calendario)
        btn_imp = QPushButton("📄 Importar desde PDF")
        btn_imp.setStyleSheet(_BTN_SEC); btn_imp.clicked.connect(self._importar_calendario_pdf)
        btn_add = QPushButton("➕ Añadir día especial")
        btn_add.setStyleSheet(_BTN_PRI); btn_add.clicked.connect(self._add_dia_calendario)
        bar.addWidget(btn_ver); bar.addWidget(btn_imp); bar.addWidget(btn_add)
        bar.addStretch()
        lay.addLayout(bar)

        # Tabla del calendario
        cols_cal = ["Fecha", "Día semana", "Tipo", "Horas jornada", "Descripción"]
        self._tbl_cal = QTableWidget(0, len(cols_cal))
        self._tbl_cal.setHorizontalHeaderLabels(cols_cal)
        self._tbl_cal.setStyleSheet(_TABLE)
        self._tbl_cal.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_cal.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_cal.verticalHeader().setVisible(False)
        lay.addWidget(self._tbl_cal)

        # Panel de resumen de horas
        grp_horas = QGroupBox("Resumen de horas (empleado seleccionado)")
        gh = QHBoxLayout(grp_horas)
        self._lbl_cal_resumen = QLabel("Selecciona empleado y mes para calcular")
        self._lbl_cal_resumen.setStyleSheet("font-weight:bold;padding:6px;")
        btn_calcular = QPushButton("⚙️ Calcular horas")
        btn_calcular.setStyleSheet(_BTN_SEC)
        btn_calcular.clicked.connect(self._calcular_horas_calendario)
        gh.addWidget(self._lbl_cal_resumen); gh.addStretch(); gh.addWidget(btn_calcular)
        lay.addWidget(grp_horas)
        return w

    def _cargar_calendario(self):
        anio   = self._spn_cal_anio.value()
        mes    = self._cmb_cal_mes.currentData()
        emp_id = self._cmb_cal_emp.currentData() or None
        dias   = self.db.obtener_calendario(anio, mes, empleado_id=emp_id)
        _DIAS  = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
        _TIPOS_COLOR = {
            "laborable":     "",
            "festivo":       "#FED7D7",
            "festivo_local": "#FEFCBF",
            "vacacion":      "#C6F6D5",
        }
        self._tbl_cal.setRowCount(0)
        for d in dias:
            r = self._tbl_cal.rowCount(); self._tbl_cal.insertRow(r)
            fecha_raw = d.get("fecha","")
            try:
                from datetime import datetime as _dt
                dt      = _dt.strptime(fecha_raw, "%Y-%m-%d")
                fecha_s = dt.strftime("%d/%m/%Y")
                dia_sem = _DIAS[dt.weekday()]
            except Exception:
                fecha_s = fecha_raw; dia_sem = ""
            tipo  = d.get("tipo_dia","laborable")
            color = _TIPOS_COLOR.get(tipo,"")
            for col, v in enumerate([fecha_s, dia_sem, tipo,
                                      str(d.get("horas_jornada",8)),
                                      d.get("descripcion","") or ""]):
                item = QTableWidgetItem(v)
                if color:
                    item.setBackground(QColor(color))
                self._tbl_cal.setItem(r, col, item)

    def _add_dia_calendario(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Añadir día especial")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        dt_fecha = QDateEdit(QDate.currentDate())
        dt_fecha.setCalendarPopup(True); dt_fecha.setDisplayFormat("dd/MM/yyyy")
        cmb_tipo = QComboBox()
        cmb_tipo.addItems(["festivo","festivo_local","vacacion","laborable"])
        spn_horas = QSpinBox(); spn_horas.setRange(0, 12); spn_horas.setValue(8)
        inp_desc  = QLineEdit(); inp_desc.setStyleSheet(_INP)
        form.addRow("Fecha:",         dt_fecha)
        form.addRow("Tipo:",          cmb_tipo)
        form.addRow("Horas jornada:", spn_horas)
        form.addRow("Descripción:",   inp_desc)
        lay.addLayout(form)
        emp_id = self._cmb_cal_emp.currentData() or None
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            self.db.insertar_dia_calendario({
                "fecha":         dt_fecha.date().toString("yyyy-MM-dd"),
                "tipo_dia":      cmb_tipo.currentText(),
                "horas_jornada": spn_horas.value(),
                "descripcion":   inp_desc.text().strip() or None,
                "empleado_id":   emp_id,
            })
            self._cargar_calendario()

    def _calcular_horas_calendario(self):
        emp_id = self._cmb_cal_emp.currentData()
        if not emp_id:
            QMessageBox.information(self, "Info", "Selecciona un empleado específico"); return
        anio = self._spn_cal_anio.value()
        mes  = self._cmb_cal_mes.currentData()
        res  = self.db.calcular_horas_mes(emp_id, anio, mes)
        self._lbl_cal_resumen.setText(
            f"Trabajadas: {res['horas_trabajadas']}h  |  "
            f"Teóricas: {res['horas_teoricas']}h  |  "
            f"Extra: +{res['horas_extra']}h  |  "
            f"Faltantes: -{res['horas_faltantes']}h  |  "
            f"Ausencias: {res['ausencias']} días"
        )

    def _importar_calendario_pdf(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Importar calendario laboral", "", "PDF (*.pdf)")
        if not ruta:
            return
        try:
            from ocr.pipeline import extract_text
            from core.config_loader import get_config
            cfg  = get_config()
            text, _ = extract_text(ruta, tesseract_path=cfg.tesseract_path,
                                    languages=cfg.ocr_languages)
            # Detectar fechas y festivos con regex básico
            import re
            festivos_detectados = 0
            anio = self._spn_cal_anio.value()
            # Patrón: fechas tipo "25/12", "25 de diciembre"
            _MESES_NOM = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                           "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
            patron_dia_mes = re.findall(r"(\d{1,2})[/\-\s](?:de\s+)?(\w+)", text.lower())
            for dia_s, mes_s in patron_dia_mes:
                mes_n = _MESES_NOM.get(mes_s.lower())
                if mes_n and 1 <= int(dia_s) <= 31:
                    try:
                        self.db.insertar_dia_calendario({
                            "fecha":    f"{anio}-{mes_n:02d}-{int(dia_s):02d}",
                            "tipo_dia": "festivo",
                            "descripcion": "Importado desde PDF",
                        })
                        festivos_detectados += 1
                    except Exception:
                        pass
            QMessageBox.information(
                self, "Importación completada",
                f"Se detectaron y añadieron {festivos_detectados} posibles festivos.\n"
                "Revisa y ajusta manualmente si es necesario.")
            self._cargar_calendario()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error importando PDF: {e}")

    # ── SUB-TAB: CONCEPTOS DE NÓMINA ─────────────────────────────────────────

    def _tab_conceptos(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Conceptos de nómina y reparto contable</b>"))

        splitter = QSplitter(Qt.Horizontal)

        # Lista de conceptos
        izq = QWidget()
        izq_lay = QVBoxLayout(izq)
        bar_c = QHBoxLayout()
        btn_add_c = QPushButton("➕ Nuevo concepto"); btn_add_c.setStyleSheet(_BTN_PRI)
        btn_add_c.clicked.connect(self._add_concepto)
        bar_c.addWidget(btn_add_c); bar_c.addStretch()
        izq_lay.addLayout(bar_c)
        cols_c = ["Código", "Descripción", "Tipo"]
        self._tbl_conceptos = QTableWidget(0, len(cols_c))
        self._tbl_conceptos.setHorizontalHeaderLabels(cols_c)
        self._tbl_conceptos.setStyleSheet(_TABLE)
        self._tbl_conceptos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_conceptos.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_conceptos.verticalHeader().setVisible(False)
        self._tbl_conceptos.currentItemChanged.connect(
            lambda cur, _prev: self._on_concepto_selected(self._tbl_conceptos.currentRow()))
        izq_lay.addWidget(self._tbl_conceptos)
        splitter.addWidget(izq)

        # Reparto contable del concepto seleccionado
        der = QWidget()
        der_lay = QVBoxLayout(der)
        der_lay.addWidget(QLabel("<b>Reparto contable</b>"))
        der_lay.addWidget(QLabel("Cada concepto puede repartirse entre varias cuentas.\n"
                                  "Los % deben sumar 100."))
        bar_r = QHBoxLayout()
        btn_add_r = QPushButton("➕ Añadir cuenta"); btn_add_r.setStyleSheet(_BTN_PRI)
        btn_add_r.clicked.connect(self._add_reparto_concepto)
        btn_save_r = QPushButton("💾 Guardar reparto"); btn_save_r.setStyleSheet(_BTN_SEC)
        btn_save_r.clicked.connect(self._guardar_reparto_concepto)
        bar_r.addWidget(btn_add_r); bar_r.addWidget(btn_save_r); bar_r.addStretch()
        der_lay.addLayout(bar_r)
        cols_r = ["Cuenta", "Subcuenta", "% Importe", "Descripción"]
        self._tbl_reparto_c = QTableWidget(0, len(cols_r))
        self._tbl_reparto_c.setHorizontalHeaderLabels(cols_r)
        self._tbl_reparto_c.setStyleSheet(_TABLE)
        self._tbl_reparto_c.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_reparto_c.verticalHeader().setVisible(False)
        der_lay.addWidget(self._tbl_reparto_c)
        self._lbl_total_pct = QLabel("Total: 0%")
        self._lbl_total_pct.setStyleSheet("font-weight:bold;")
        der_lay.addWidget(self._lbl_total_pct)
        splitter.addWidget(der)
        splitter.setSizes([350, 450])

        lay.addWidget(splitter)
        self._concepto_id_sel = None
        self._cargar_conceptos()

        # Menú contextual conceptos (botón derecho)
        add_context_menu(self._tbl_conceptos, [
            ("✏️ Editar concepto",            lambda r: self._editar_concepto(r)),
            ("📒 Configurar reparto contable", lambda r: self._on_concepto_selected(r)),
            (None, None),
            ("🗑 Eliminar concepto",           lambda r: self._eliminar_concepto(r)),
        ])
        return w

    def _editar_concepto(self, row: int = -1):
        """Edita el concepto seleccionado en la tabla."""
        if row < 0:
            row = self._tbl_conceptos.currentRow()
        if row < 0:
            return
        item = self._tbl_conceptos.item(row, 0)
        if not item:
            return
        concepto_id = item.data(Qt.UserRole)
        # Obtener datos actuales
        self.db.cursor.execute(
            "SELECT * FROM laboral_conceptos_nomina WHERE id=?", (concepto_id,))
        cols = [d[0] for d in self.db.cursor.description]
        row_data = self.db.cursor.fetchone()
        if not row_data:
            return
        datos = dict(zip(cols, row_data))

        dlg = QDialog(self)
        dlg.setWindowTitle("Editar concepto de nómina")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        inp_cod  = QLineEdit(datos.get("codigo",""));  inp_cod.setStyleSheet(_INP)
        inp_desc = QLineEdit(datos.get("descripcion","")); inp_desc.setStyleSheet(_INP)
        cmb_tipo = QComboBox()
        cmb_tipo.addItems(["devengo","deduccion","empresa"])
        cmb_tipo.setCurrentText(datos.get("tipo","devengo"))
        chk_activo = QCheckBox("Activo")
        chk_activo.setChecked(bool(datos.get("activo", 1)))
        form.addRow("Código:", inp_cod)
        form.addRow("Descripción:", inp_desc)
        form.addRow("Tipo:", cmb_tipo)
        form.addRow("", chk_activo)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            self.db.cursor.execute(
                "UPDATE laboral_conceptos_nomina SET codigo=?, descripcion=?, tipo=?, activo=? WHERE id=?",
                (inp_cod.text().strip(), inp_desc.text().strip(),
                 cmb_tipo.currentText(), 1 if chk_activo.isChecked() else 0,
                 concepto_id))
            self.db.conn.commit()
            self._cargar_conceptos()

    def _eliminar_concepto(self, row: int = -1):
        """Elimina el concepto de nómina seleccionado."""
        if row < 0:
            row = self._tbl_conceptos.currentRow()
        if row < 0:
            return
        item = self._tbl_conceptos.item(row, 0)
        if not item:
            return
        concepto_id = item.data(Qt.UserRole)
        codigo = item.text()
        desc   = self._tbl_conceptos.item(row, 1).text() if self._tbl_conceptos.item(row, 1) else ""
        resp = QMessageBox.question(
            self, "Eliminar concepto",
            f"Eliminar concepto {codigo} - {desc}?"

            "Se eliminarán también sus repartos contables.",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            self.db.cursor.execute(
                "DELETE FROM laboral_conceptos_nomina WHERE id=?", (concepto_id,))
            self.db.conn.commit()
            self._concepto_id_sel = None
            self._tbl_reparto_c.setRowCount(0)
            self._cargar_conceptos()

    def _ver_nomina_pdf(self, row: int = -1):
        """Abre el PDF de la nómina seleccionada."""
        if row < 0:
            row = self._tbl_nom.currentRow()
        if row < 0:
            return
        item = self._tbl_nom.item(row, 0)
        if not item:
            return
        nomina_id = item.data(Qt.UserRole) if item.data(Qt.UserRole) else None
        if not nomina_id:
            return
        self.db.cursor.execute("SELECT pdf_path FROM laboral_nominas WHERE id=?", (nomina_id,))
        row_data = self.db.cursor.fetchone()
        if row_data and row_data[0]:
            import subprocess, os
            path = row_data[0]
            if os.path.exists(path):
                try:
                    os.startfile(path)
                except Exception:
                    subprocess.Popen(["xdg-open", path])
            else:
                QMessageBox.warning(self, "No encontrado", "PDF no encontrado:\n" + str(path))

    def _reenviar_nomina(self, row: int = -1):
        """Reenvía por email la nómina seleccionada."""
        QMessageBox.information(self, "Info",
            "Para reenviar, marca la nómina como no enviada y vuelve a procesarla.")

    def _eliminar_nomina(self, row: int = -1):
        """Elimina el registro de nómina de la BD."""
        if row < 0:
            row = self._tbl_nom.currentRow()
        if row < 0:
            return
        resp = QMessageBox.question(
            self, "Eliminar nómina",
            "¿Eliminar este registro de nómina? (no borra el PDF)",
            QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            item = self._tbl_nom.item(row, 0)
            if item and item.data(Qt.UserRole):
                self.db.cursor.execute(
                    "DELETE FROM laboral_nominas WHERE id=?", (item.data(Qt.UserRole),))
                self.db.conn.commit()
                self.cargar_nominas()

    def _cargar_conceptos(self):
        conceptos = self.db.obtener_conceptos_nomina()
        self._tbl_conceptos.setRowCount(0)
        _TIPO_COLOR = {"devengo":"","deduccion":"#FED7D7","empresa":"#FEFCBF"}
        for c in conceptos:
            r = self._tbl_conceptos.rowCount(); self._tbl_conceptos.insertRow(r)
            color = _TIPO_COLOR.get(c.get("tipo",""),"")
            for col, v in enumerate([c.get("codigo",""), c.get("descripcion",""), c.get("tipo","")]):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, c.get("id"))
                if color: item.setBackground(QColor(color))
                self._tbl_conceptos.setItem(r, col, item)

    def _on_concepto_selected(self, row):
        if row < 0: return
        self._concepto_id_sel = self._tbl_conceptos.item(row, 0).data(Qt.UserRole)
        cuentas = self.db.obtener_cuentas_concepto(self._concepto_id_sel)
        self._tbl_reparto_c.setRowCount(0)
        total_pct = 0
        for c in cuentas:
            r = self._tbl_reparto_c.rowCount(); self._tbl_reparto_c.insertRow(r)
            pct = float(c.get("porcentaje", 0))
            total_pct += pct
            for col, v in enumerate([c.get("cuenta",""), c.get("subcuenta",""),
                                      f"{pct:.1f}", c.get("descripcion","") or ""]):
                self._tbl_reparto_c.setItem(r, col, QTableWidgetItem(v))
        color = "#276749" if abs(total_pct - 100) < 0.01 else "#C53030"
        self._lbl_total_pct.setText(f"Total: {total_pct:.1f}%")
        self._lbl_total_pct.setStyleSheet(f"font-weight:bold;color:{color};")

    def _add_reparto_concepto(self):
        r = self._tbl_reparto_c.rowCount()
        self._tbl_reparto_c.insertRow(r)
        for col, v in enumerate(["", "", "100.0", ""]):
            self._tbl_reparto_c.setItem(r, col, QTableWidgetItem(v))

    def _guardar_reparto_concepto(self):
        if not self._concepto_id_sel:
            QMessageBox.warning(self, "Info", "Selecciona un concepto primero"); return
        from core.utils import parse_es_float_safe as _pfs
        cuentas = []
        total_pct = 0
        for r in range(self._tbl_reparto_c.rowCount()):
            cta = (self._tbl_reparto_c.item(r,0) or QTableWidgetItem("")).text().strip()
            sub = (self._tbl_reparto_c.item(r,1) or QTableWidgetItem("")).text().strip()
            pct = _pfs((self._tbl_reparto_c.item(r,2) or QTableWidgetItem("100")).text(), 100.0)
            desc= (self._tbl_reparto_c.item(r,3) or QTableWidgetItem("")).text().strip()
            if cta:
                cuentas.append({"cuenta":cta,"subcuenta":sub,"porcentaje":pct,"descripcion":desc})
                total_pct += pct
        if abs(total_pct - 100) > 0.01:
            QMessageBox.warning(self, "Error",
                f"Los porcentajes deben sumar 100% (actual: {total_pct:.1f}%)"); return
        self.db.guardar_cuentas_concepto(self._concepto_id_sel, cuentas)
        QMessageBox.information(self, "OK", "Reparto guardado correctamente")
        self._on_concepto_selected(self._tbl_conceptos.currentRow())

    def _add_concepto(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Nuevo concepto de nómina")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        inp_cod  = QLineEdit(); inp_cod.setStyleSheet(_INP)
        inp_desc = QLineEdit(); inp_desc.setStyleSheet(_INP)
        cmb_tipo = QComboBox(); cmb_tipo.addItems(["devengo","deduccion","empresa"])
        form.addRow("Código:", inp_cod)
        form.addRow("Descripción:", inp_desc)
        form.addRow("Tipo:", cmb_tipo)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            cod  = inp_cod.text().strip()
            desc = inp_desc.text().strip()
            if cod and desc:
                self.db.cursor.execute(
                    "INSERT OR IGNORE INTO laboral_conceptos_nomina(codigo,descripcion,tipo) VALUES(?,?,?)",
                    (cod, desc, cmb_tipo.currentText()))
                self.db.conn.commit()
                self._cargar_conceptos()

    def _tab_informes(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Informes laborales</b>"))

        grp1 = QGroupBox("Costes laborales")
        g1   = QHBoxLayout(grp1)
        g1.addWidget(QLabel("Año:"))
        self._spn_inf_anio = QSpinBox()
        self._spn_inf_anio.setRange(2020, 2099)
        self._spn_inf_anio.setValue(datetime.now().year)
        g1.addWidget(self._spn_inf_anio)
        btn_costes = QPushButton("📊 Exportar Excel Costes")
        btn_costes.setStyleSheet(_BTN_PRI)
        btn_costes.clicked.connect(self._exportar_costes)
        g1.addWidget(btn_costes); g1.addStretch()
        lay.addWidget(grp1)

        grp2 = QGroupBox("Asistencia mensual")
        g2   = QHBoxLayout(grp2)
        g2.addWidget(QLabel("Año:")); self._spn_asi_anio = QSpinBox()
        self._spn_asi_anio.setRange(2020, 2099)
        self._spn_asi_anio.setValue(datetime.now().year)
        g2.addWidget(self._spn_asi_anio)
        g2.addWidget(QLabel("Mes:")); self._cmb_asi_mes = QComboBox()
        for m, nm in [(i, n) for i, n in {1:"Enero",2:"Febrero",3:"Marzo",
                      4:"Abril",5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",
                      9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}.items()]:
            self._cmb_asi_mes.addItem(nm, m)
        self._cmb_asi_mes.setCurrentIndex(datetime.now().month - 1)
        g2.addWidget(self._cmb_asi_mes)
        btn_asist = QPushButton("📊 Exportar Excel Asistencia")
        btn_asist.setStyleSheet(_BTN_PRI)
        btn_asist.clicked.connect(self._exportar_asistencia)
        g2.addWidget(btn_asist); g2.addStretch()
        lay.addWidget(grp2)

        grp3 = QGroupBox("Rellenar plantilla Excel de la empresa")
        g3   = QVBoxLayout(grp3)
        r3a  = QHBoxLayout()
        self._inp_plantilla_excel = QLineEdit()
        self._inp_plantilla_excel.setPlaceholderText("Ruta de la plantilla Excel...")
        self._inp_plantilla_excel.setStyleSheet(_INP)
        btn_sel_plt = QPushButton("📂 Seleccionar")
        btn_sel_plt.setStyleSheet(_BTN_SEC)
        btn_sel_plt.clicked.connect(lambda: self._sel_plantilla())
        r3a.addWidget(self._inp_plantilla_excel); r3a.addWidget(btn_sel_plt)
        g3.addLayout(r3a)
        lbl_info = QLabel("El mapeo de campos se configura en Ajustes > Módulo Laboral")
        lbl_info.setStyleSheet("color:#666;font-size:9px;")
        g3.addWidget(lbl_info)
        lay.addWidget(grp3)
        lay.addStretch()

        return w

    def _exportar_costes(self):
        carpeta = self.db._db.get_config_ui("carpeta_informes", "./informes")
        from laboral.informes.excel_laboral import exportar_costes_laborales
        ruta = exportar_costes_laborales(
            self.db, self._spn_inf_anio.value(), carpeta_salida=carpeta)
        if ruta:
            QMessageBox.information(self, "OK", f"Excel guardado:\n{ruta}")
        else:
            QMessageBox.warning(self, "Error", "No se pudo generar el Excel")

    def _exportar_asistencia(self):
        carpeta = self.db._db.get_config_ui("carpeta_informes", "./informes")
        from laboral.informes.excel_laboral import exportar_asistencia_mensual
        ruta = exportar_asistencia_mensual(
            self.db,
            self._spn_asi_anio.value(),
            self._cmb_asi_mes.currentData(),
            carpeta_salida=carpeta)
        if ruta:
            QMessageBox.information(self, "OK", f"Excel guardado:\n{ruta}")
        else:
            QMessageBox.warning(self, "Error", "No se pudo generar el Excel")

    def _sel_plantilla(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar plantilla Excel", "",
            "Excel (*.xlsx *.xls)")
        if ruta:
            self._inp_plantilla_excel.setText(ruta)
