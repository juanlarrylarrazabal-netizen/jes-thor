# -*- coding: utf-8 -*-
"""Ventana principal PyQt5 — JES⚡THOR V1"""
from __future__ import annotations
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QAction, QMessageBox, QApplication, QLabel
)
from PyQt5.QtGui import QFont, QPixmap, QPainter
from PyQt5.QtCore import Qt
import os
from ui.styles import TABS, MENUBAR, STATUSBAR
from core.logging_config import get_logger

_log = get_logger("main_window")


class MainWindow(QMainWindow):
    def __init__(self, usuario: dict, safe_mode: bool = False) -> None:
        super().__init__()
        self.usuario = usuario
        self._safe_mode = safe_mode
        _log.info("Construyendo MainWindow: usuario=%s safe_mode=%s",
                  usuario.get("usuario"), safe_mode)
        from database.manager import DatabaseManager
        self.db = DatabaseManager()
        nombre = usuario.get("nombre_completo", usuario.get("usuario", ""))
        rol    = usuario.get("rol", "").upper()
        self._bg_pixmap = None
        self._cargar_visual()
        empresa = self._cfg_visual.get("empresa","")
        title_emp = f" — {empresa}" if empresa else ""
        self.setWindowTitle(f"⚡ JES⚡THOR V1{title_emp}  —  {nombre} [{rol}]")
        self.resize(1350, 870)
        self.setMinimumSize(1050, 680)
        self._center()
        self._build()

    def _cargar_visual(self):
        self._cfg_visual = {}
        try:
            self._cfg_visual["empresa"] = self.db.get_config_ui("empresa_nombre","")
            bg = self.db.get_config_ui("fondo_path","")
            if bg and os.path.isfile(bg):
                self._bg_pixmap = QPixmap(bg)
            logo = self.db.get_config_ui("logo_path","")
            if logo and os.path.isfile(logo):
                self._cfg_visual["logo"] = logo
        except Exception:
            pass

    def paintEvent(self, event):
        if self._bg_pixmap:
            p = QPainter(self)
            p.drawPixmap(self.rect(), self._bg_pixmap.scaled(
                self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        else:
            super().paintEvent(event)

    def _center(self) -> None:
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _build(self) -> None:
        self._build_menu()
        tabs = QTabWidget()
        tabs.setStyleSheet(TABS)
        tabs.setDocumentMode(True)

        _rol = self.usuario.get("rol", "usuario_basico")
        from ui.permisos import tiene_permiso

        # ── Facturas (siempre disponible) ─────────────────────────────────────
        try:
            from ui.tabs.tab_facturas import TabFacturas
            self.tab_facturas = TabFacturas(self.db, self.usuario)
            tabs.addTab(self.tab_facturas, "📄  Facturas")
            if hasattr(self.tab_facturas, "btn_descargar"):
                self.tab_facturas.btn_descargar.setEnabled(
                    tiene_permiso(_rol, "descargar_correo"))
        except Exception as exc:
            _log.error("Error cargando TabFacturas: %s", exc, exc_info=True)
            self.tab_facturas = self._tab_error("Facturas", exc)
            tabs.addTab(self.tab_facturas, "📄  Facturas ⚠")

        # ── Proveedores ───────────────────────────────────────────────────────
        try:
            from ui.tabs.tab_proveedores import TabProveedores
            self.tab_proveedores = TabProveedores(self.db)
            tabs.addTab(self.tab_proveedores, "🏭  Proveedores")
            if not tiene_permiso(_rol, "tab_proveedores"):
                tabs.setTabEnabled(tabs.count()-1, False)
                tabs.setTabToolTip(tabs.count()-1, "Requiere rol usuario_avanzado o superior")
        except Exception as exc:
            _log.error("Error cargando TabProveedores: %s", exc, exc_info=True)

        # ── Historial ─────────────────────────────────────────────────────────
        try:
            from ui.tabs.tab_historial import TabHistorial
            self.tab_historial = TabHistorial(self.db)
            tabs.addTab(self.tab_historial, "📋  Historial")

            try:
                from ui.tabs.tab_escaner import TabEscaner
                self.tab_escaner = TabEscaner(self.db)
                self.tab_escaner.pdf_ready.connect(self._abrir_pdf_en_visor)
                tabs.addTab(self.tab_escaner, "🖨️  Escáner")
            except Exception as _exc_esc:
                _log.warning("TabEscaner no cargado: %s", _exc_esc)
        except Exception as exc:
            _log.error("Error cargando TabHistorial: %s", exc, exc_info=True)

        # ── Informes (omitir en safe mode, lazy en normal) ────────────────────
        if not self._safe_mode:
            try:
                from ui.tabs.tab_informes import TabInformes
                self.tab_informes = TabInformes(self.db)
                tabs.addTab(self.tab_informes, "📊  Informes")
                if not tiene_permiso(_rol, "tab_informes"):
                    tabs.setTabEnabled(tabs.count()-1, False)
                    tabs.setTabToolTip(tabs.count()-1, "Requiere rol usuario_avanzado o superior")
            except Exception as exc:
                _log.error("Error cargando TabInformes: %s", exc, exc_info=True)
        else:
            _log.info("TabInformes omitida (safe_mode)")

        # ── Módulo Laboral ────────────────────────────────────────────────────
        try:
            from ui.tabs.tab_laboral import TabLaboral
            self.tab_laboral = TabLaboral(self.db, self.usuario)
            tabs.addTab(self.tab_laboral, "👷  Laboral")
            if not tiene_permiso(_rol, "tab_ajustes"):  # mismo permiso que ajustes
                tabs.setTabEnabled(tabs.count()-1, False)
                tabs.setTabToolTip(tabs.count()-1, "Requiere rol admin o superior")
        except Exception as exc:
            _log.error("Error cargando TabLaboral: %s", exc, exc_info=True)

        # ── Ajustes ───────────────────────────────────────────────────────────
        try:
            from ui.tabs.tab_ajustes import TabAjustes
            self.tab_ajustes = TabAjustes(self.db, self.usuario)
            tabs.addTab(self.tab_ajustes, "⚙️  Ajustes")
            if not tiene_permiso(_rol, "tab_ajustes"):
                tabs.setTabEnabled(tabs.count()-1, False)
                tabs.setTabToolTip(tabs.count()-1, "Requiere rol admin o superior")
        except Exception as exc:
            _log.error("Error cargando TabAjustes: %s", exc, exc_info=True)

        tabs.currentChanged.connect(self._on_tab_change)
        self.setCentralWidget(tabs)

        self.status = self.statusBar()
        self.status.setStyleSheet(STATUSBAR)
        modo_txt = "  [MODO SEGURO]" if self._safe_mode else ""
        self._log(f"✅ JES⚡THOR V1 listo.{modo_txt}")
        _log.info("MainWindow construida con %d tabs", tabs.count())

    @staticmethod
    def _tab_error(nombre: str, exc: Exception):
        """Pestaña de error mínima para cuando una tab falla al cargar."""
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel(f"⚠  Error al cargar la pestaña '{nombre}':\n\n{exc}\n\n"
                     f"Consulta los logs para más detalle.")
        lbl.setStyleSheet("color:#C53030;padding:20px;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        return w

    def _on_tab_change(self, idx: int) -> None:
        # Actualizar historial cuando se activa su pestaña
        try:
            widget = self.centralWidget().widget(idx)
            if hasattr(widget, "cargar"):
                widget.cargar()
        except Exception:
            pass

    def _build_menu(self) -> None:
        mb = self.menuBar()
        mb.setStyleSheet(MENUBAR)

        m_file = mb.addMenu("Archivo")
        m_file.addAction("📄 Cargar PDF", lambda: self.tab_facturas._load_pdf() if hasattr(self, "tab_facturas") else None)
        m_file.addAction("🚪 Cerrar sesión", self._logout)
        m_file.addSeparator()
        m_file.addAction("❌ Salir", self.close)

        m_gestion = mb.addMenu("Gestión")
        m_gestion.addAction("🏭 Gestionar Proveedores", self._open_vendors)
        m_gestion.addAction("🔧 Gestionar Reglas",      self._open_rules)

        m_tools = mb.addMenu("Herramientas")
        m_tools.addAction("📊 Excel Resumen / Contable", self._open_excel_export)
        m_tools.addSeparator()
        m_tools.addAction("🔍 Diagnóstico del sistema",  self._run_diagnostics)
        m_tools.addAction("💾 Backup de base de datos",  self._run_backup)

        m_help = mb.addMenu("Ayuda")
        m_help.addAction("ℹ️ Acerca de", self._about)

    def _open_vendors(self) -> None:
        try:
            from gestor_proveedores import abrir_gestor_proveedores
            abrir_gestor_proveedores(self)
            if hasattr(self, "tab_proveedores"):
                self.tab_proveedores.cargar()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _open_rules(self) -> None:
        try:
            from gestor_reglas_proveedor import abrir_gestor_reglas
            abrir_gestor_reglas(self)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _open_excel_export(self) -> None:
        """Abre la pestaña de informes para exportar Excel."""
        try:
            # Navegar a la pestaña Informes
            tabs = self.centralWidget()
            for i in range(tabs.count()):
                if "Informes" in tabs.tabText(i):
                    tabs.setCurrentIndex(i)
                    return
        except Exception:
            pass
        QMessageBox.information(self, "Excel",
            "Usa la pestaña 📊 Informes para exportar Excel Resumen y Contable.")

    def _run_diagnostics(self) -> None:
        from cli.commands import run_diagnostics
        report = run_diagnostics()
        QMessageBox.information(self, "Diagnóstico del Sistema", report)

    def _run_backup(self) -> None:
        try:
            from storage.backup import create_backup
            path = create_backup()
            QMessageBox.information(self, "Backup", f"Backup creado:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error backup", str(exc))

    def _logout(self) -> None:
        if QMessageBox.question(self, "Cerrar sesión", "¿Cerrar sesión y salir?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.close()

    def _about(self) -> None:
        QMessageBox.about(self, "JES⚡THOR V1",
            "<h3>⚡ JES⚡THOR V1</h3>"
            "<p>Sistema Profesional de Gestión Documental</p>"
            "<p><b>Stack:</b> Python · PyQt5 · SQLite · Tesseract OCR · openpyxl · matplotlib</p>"
            "<p><b>Novedades V10:</b><br>"
            "— OCR inteligente: excluye CIF propio B75886887<br>"
            "— Filtros de correo por rango de fechas (24h, 3d, semana, mes)<br>"
            "— Deduplicación de correos por Message-ID<br>"
            "— Módulo de Informes con gráficos interactivos<br>"
            "— Excel Resumen con pivotes por proveedor y categoría<br>"
            "— Excel Contable con asientos libro diario (PGC 2008)<br>"
            "— Historial de correos descargados<br>"
            "— Base de datos extendida con datos financieros</p>"
            "<p>© 2024-2025 JAMF</p>")

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.status.showMessage(f"[{ts}]  {msg}", 8000)

    def _abrir_pdf_en_visor(self, ruta: str) -> None:
        """Abre un PDF en el visor manual. Conectado a tab_escaner.pdf_ready."""
        if not ruta or not os.path.exists(ruta):
            _log.warning("_abrir_pdf_en_visor: ruta no válida: %s", ruta)
            return
        try:
            from modulos.visor_pdf_manual import VisorPDFCompleto
            v = VisorPDFCompleto(ruta, db=self.db, parent=self)
            v.show()
        except Exception as exc:
            _log.error("Error abriendo visor PDF: %s", exc)
            QMessageBox.critical(self, "Error", f"No se pudo abrir el visor:\n{exc}")

    def closeEvent(self, event) -> None:
        if QMessageBox.question(self, "Salir", "¿Cerrar JES⚡THOR V1?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()
