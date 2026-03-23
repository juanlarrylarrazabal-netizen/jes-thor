# -*- coding: utf-8 -*-
"""
LoginWindow V15.2 — Corrección del cierre silencioso.

FIXES aplicados:
  FIX-A: exec_() ya no sobreescribe el return value del QDialog nativo.
          El flujo correcto es: QDialog.exec_() → Accepted/Rejected.
  FIX-B: self.done(QDialog.Accepted) solo se llama cuando el login es VÁLIDO.
          El método exec_() devuelve QDialog.Accepted/Rejected estándar.
  FIX-C: Botón Entrar desactivado durante validación, reactivado siempre.
  FIX-D: Todos los errores muestran label de feedback, NUNCA cierran la app.
  FIX-E: Modo seguro: indica al usuario que está en safe mode.
  FIX-F: Sin autocompletado ni sugerencias en campos.
  FIX-G: Logs completos de cada intento.
"""
from __future__ import annotations
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QApplication
)
from PyQt5.QtGui import QFont, QPixmap, QPainter
from PyQt5.QtCore import Qt, QTimer

from core.logging_config import get_logger

log = get_logger("login")


class LoginWindow(QDialog):
    """
    Ventana de login.

    Uso correcto en main():
        login = LoginWindow()
        if login.exec_() == QDialog.Accepted and login.usuario_logueado:
            ...
    """

    def __init__(self, safe_mode: bool = False) -> None:
        super().__init__()
        self.usuario_logueado: dict | None = None
        self._safe_mode = safe_mode
        self._bg_pixmap = None
        self._intentos = 0

        self.setWindowTitle("JES⚡THOR V1 — Acceso")
        self.setMinimumSize(480, 560 if safe_mode else 540)
        self.resize(480, 560 if safe_mode else 540)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )

        self._construir_ui()
        self._aplicar_visual()
        self._centrar()

        log.info("LoginWindow iniciada (safe_mode=%s)", safe_mode)

    # ── Posicionado ───────────────────────────────────────────────────────────
    def _centrar(self) -> None:
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    # ── Visual desde BD ───────────────────────────────────────────────────────
    def _aplicar_visual(self) -> None:
        try:
            from database.manager import DatabaseManager
            db = DatabaseManager()
            logo_path = db.get_config_ui("logo_path", "")
            if logo_path and os.path.isfile(logo_path):
                pix = QPixmap(logo_path).scaled(
                    80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self._lbl_logo.setPixmap(pix)
                self._lbl_logo.setVisible(True)
            empresa = db.get_config_ui("empresa_nombre", "")
            if empresa:
                self._lbl_empresa.setText(empresa)
                self._lbl_empresa.setVisible(True)
            bg = db.get_config_ui("fondo_path", "")
            if bg and os.path.isfile(bg):
                self._bg_pixmap = QPixmap(bg)
        except Exception as e:
            log.debug("_aplicar_visual: %s (no crítico)", e)

    def paintEvent(self, event) -> None:
        if self._bg_pixmap:
            p = QPainter(self)
            p.drawPixmap(
                self.rect(),
                self._bg_pixmap.scaled(
                    self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                ),
            )
        else:
            super().paintEvent(event)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Cabecera
        cab = QFrame()
        cab.setFixedHeight(150)
        cab.setStyleSheet("background-color:#1F4E79;")
        cab_lay = QVBoxLayout(cab)
        cab_lay.setAlignment(Qt.AlignCenter)

        self._lbl_logo = QLabel()
        self._lbl_logo.setAlignment(Qt.AlignCenter)
        self._lbl_logo.setVisible(False)

        self._lbl_empresa = QLabel("")
        self._lbl_empresa.setFont(QFont("Segoe UI", 9))
        self._lbl_empresa.setStyleSheet("color:#8DB4D8;background:transparent;")
        self._lbl_empresa.setAlignment(Qt.AlignCenter)
        self._lbl_empresa.setVisible(False)

        titulo = QLabel("🧾  JES⚡THOR V1")
        titulo.setFont(QFont("Segoe UI", 18, QFont.Bold))
        titulo.setStyleSheet("color:white;background:transparent;")
        titulo.setAlignment(Qt.AlignCenter)

        for w in [self._lbl_logo, titulo, self._lbl_empresa]:
            cab_lay.addWidget(w)
        layout.addWidget(cab)

        franja = QFrame()
        franja.setFixedHeight(4)
        franja.setStyleSheet("background:#4A90D9;")
        layout.addWidget(franja)

        # Banner modo seguro
        if self._safe_mode:
            safe_banner = QFrame()
            safe_banner.setFixedHeight(28)
            safe_banner.setStyleSheet("background:#744210;")
            sb_lay = QHBoxLayout(safe_banner)
            sb_lay.setContentsMargins(10, 0, 10, 0)
            sb_lbl = QLabel("⚠  MODO SEGURO ACTIVO — OCR / IA / Informes desactivados")
            sb_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
            sb_lbl.setStyleSheet("color:#FBD38D;background:transparent;")
            sb_lay.addWidget(sb_lbl)
            layout.addWidget(safe_banner)

        # Formulario
        form = QFrame()
        form.setStyleSheet("background-color:rgba(245,247,250,220);")
        fl = QVBoxLayout(form)
        fl.setContentsMargins(60, 30, 60, 20)
        fl.setSpacing(8)

        lbl_u = QLabel("Usuario")
        lbl_u.setFont(QFont("Segoe UI", 9))
        lbl_u.setStyleSheet("color:#4A5568;background:transparent;")

        self.inp_usuario = QLineEdit()
        self.inp_usuario.setPlaceholderText("Introduce tu usuario")
        self.inp_usuario.setCompleter(None)                  # FIX-F
        self.inp_usuario.setFont(QFont("Segoe UI", 11))
        self.inp_usuario.setFixedHeight(42)
        self.inp_usuario.setStyleSheet(self._estilo_input())

        lbl_p = QLabel("Contraseña")
        lbl_p.setFont(QFont("Segoe UI", 9))
        lbl_p.setStyleSheet("color:#4A5568;background:transparent;")
        lbl_p.setContentsMargins(0, 8, 0, 0)

        self.inp_password = QLineEdit()
        self.inp_password.setPlaceholderText("Introduce tu contraseña")
        self.inp_password.setEchoMode(QLineEdit.Password)
        self.inp_password.setCompleter(None)                 # FIX-F
        self.inp_password.setFont(QFont("Segoe UI", 11))
        self.inp_password.setFixedHeight(42)
        self.inp_password.setStyleSheet(self._estilo_input())

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(
            "color:#E53E3E;font-size:12px;background:transparent;"
        )
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setMinimumHeight(22)

        self.btn_entrar = QPushButton("  ENTRAR  →")
        self.btn_entrar.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_entrar.setFixedHeight(48)
        self.btn_entrar.setCursor(Qt.PointingHandCursor)
        self.btn_entrar.setStyleSheet("""
            QPushButton{background:#1F4E79;color:white;border:none;border-radius:6px;
                        padding:0 20px;margin-top:10px;}
            QPushButton:hover{background:#2563A8;}
            QPushButton:pressed{background:#1a3f63;}
            QPushButton:disabled{background:#A0AEC0;}
        """)

        for w in [lbl_u, self.inp_usuario, lbl_p, self.inp_password,
                  self.lbl_error, self.btn_entrar]:
            fl.addWidget(w)
        fl.addStretch()
        layout.addWidget(form, 1)

        # Pie
        pie = QFrame()
        pie.setFixedHeight(44)
        pie.setStyleSheet("background:#EDF2F7;border-top:1px solid #CBD5E0;")
        pie_lay = QHBoxLayout(pie)
        lbl_v = QLabel("JES⚡THOR V1  v15.0")
        lbl_v.setFont(QFont("Segoe UI", 8))
        lbl_v.setStyleSheet("color:#718096;background:transparent;")
        lbl_v.setAlignment(Qt.AlignCenter)
        pie_lay.addWidget(lbl_v)
        layout.addWidget(pie)

        # Conexiones
        self.btn_entrar.clicked.connect(self._intentar_login)
        self.inp_usuario.returnPressed.connect(lambda: self.inp_password.setFocus())
        self.inp_password.returnPressed.connect(self._intentar_login)
        self.inp_usuario.setFocus()

    @staticmethod
    def _estilo_input() -> str:
        return (
            "QLineEdit{border:1px solid #CBD5E0;border-radius:6px;"
            "padding:0 12px;background:white;color:#2D3748;}"
            "QLineEdit:focus{border:2px solid #2563A8;}"
        )

    # ── Lógica de login ───────────────────────────────────────────────────────
    def _intentar_login(self) -> None:
        usuario  = self.inp_usuario.text().strip().upper()
        password = self.inp_password.text()

        if not usuario or not password:
            self._mostrar_error("⚠  Introduce usuario y contraseña")
            return

        # FIX-C: deshabilitar botón durante validación
        self.btn_entrar.setEnabled(False)
        self.btn_entrar.setText("  Verificando...")
        self.lbl_error.setText("")
        QApplication.processEvents()

        try:
            from database import DatabaseManager
            log.debug("Intentando login: usuario=%s", usuario)
            resultado = DatabaseManager().verificar_login(usuario, password)

            if resultado:
                self._intentos = 0
                self.usuario_logueado = resultado
                log.info("Login OK: %s [%s]", resultado.get("usuario"),
                         resultado.get("rol"))
                # FIX-B: usar QDialog.Accepted estándar, NO self.Accepted
                self.accept()
            else:
                self._intentos += 1
                log.warning("Login fallido: usuario=%s intento=%d",
                            usuario, self._intentos)
                self._mostrar_error("⚠  Usuario o contraseña incorrectos")
                self.inp_password.clear()
                self.inp_password.setFocus()

        except PermissionError as e:
            log.warning("Login bloqueado: %s — %s", usuario, e)
            self._mostrar_error(f"🔒  {e}")

        except Exception as e:
            log.error("Error en login: %s", e, exc_info=True)
            # FIX-D: error nunca cierra la app — muestra feedback
            self._mostrar_error(f"⚠  Error de conexión: {e}")

        finally:
            # FIX-C: SIEMPRE reactivar el botón
            self.btn_entrar.setEnabled(True)
            self.btn_entrar.setText("  ENTRAR  →")

    def _mostrar_error(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        # Limpiar el error después de 5 segundos automáticamente
        QTimer.singleShot(5000, lambda: self.lbl_error.setText(""))

    # FIX-B: No sobreescribir exec_() — usar el comportamiento nativo de QDialog.
    # QDialog.exec_() devuelve QDialog.Accepted (1) si self.accept() fue llamado,
    # QDialog.Rejected (0) si self.reject() fue llamado o se cerró la ventana.
    # En main() se comprueba: login.exec_() == QDialog.Accepted AND login.usuario_logueado
