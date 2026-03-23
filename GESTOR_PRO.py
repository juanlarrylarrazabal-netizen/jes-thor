# -*- coding: utf-8 -*-
"""
JES⚡THOR V1
=========================
Punto de entrada único. Ejecutar sin consola como GESTOR_PRO.pyw en Windows.
Flujo: Instrumentación → Splash → Login → Ventana principal

V18 CORRECCIONES:
  FIX-B: Motor de reglas corregido para proveedores VARIABLES (trigger normalizado)
  FIX-C: Marca de agua ROJA, sin recuadros, opacidad 60%
  FIX-D: QLineEdit siempre editable en visor, sin auto-sobrescritura
  FIX-G: Regex base_imponible expandida + derivación desde total-IVA
  FIX-I: Versionado de archivos reinicia en _v1 (no _(17))
  FIX-H: Informes separados Gastos (6xx) vs Compras Mercaderías (3/4xx)

V15.2 CORRECCIONES (cierre silencioso):
  FIX-1: app.setQuitOnLastWindowClosed(False) — nunca terminar al cerrar login
  FIX-2: MainWindow creado ANTES de que el diálogo de login cierre
  FIX-3: Referencia permanente en app._main_window (anti-GC)
  FIX-4: excepthook global: ninguna excepción cierra en silencio
  FIX-5: Toda excepción en arranque muestra diálogo + escribe log
  FIX-6: faulthandler activo para crashes nativos
  FIX-7: qInstallMessageHandler para warnings/criticals de Qt
  FIX-8: Modo seguro (--safe-mode): sin OCR/IA/matplotlib
"""
import faulthandler
import os
import sys
import time
import traceback

# ── Activar faulthandler inmediatamente (antes de todo) ───────────────────────
faulthandler.enable()

# ── Suprimir DeprecationWarnings de librerías de terceros ────────────────────
# cryptography >= 43 mueve ARC4; pypdf lo importa desde la ruta antigua.
# El warning no afecta al funcionamiento pero ensucia los logs.
import warnings
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"cryptography",
)
warnings.filterwarnings(
    "ignore",
    message=r".*ARC4.*",
    category=DeprecationWarning,
)

# ── Setup de paths ─────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
for sub in ["modulos", "gestion", "descarga", "ocr", "excel",
            "impresion", "licencias", "scripts"]:
    p = os.path.join(ROOT, sub)
    if os.path.isdir(p):
        sys.path.append(p)

# ── Modo seguro ────────────────────────────────────────────────────────────────
SAFE_MODE = "--safe-mode" in sys.argv or os.environ.get("GESTOR_SAFE_MODE", "0") == "1"

# ── Logging (lo más temprano posible) ─────────────────────────────────────────
from core.logging_config import (
    setup_logging, setup_excepthook, setup_faulthandler,
    setup_qt_message_handler, get_logger, LOG_DIR
)

try:
    from core.config_loader import get_config
    _level = get_config().log_level
except Exception:
    _level = "DEBUG" if os.environ.get("GESTOR_DEBUG", "0") == "1" else "INFO"

setup_logging(level=_level)
setup_faulthandler()
setup_excepthook()

log = get_logger("main")
log.info("=== ARRANQUE JES⚡THOR V1 | SAFE_MODE=%s | LOG_DIR=%s ===", SAFE_MODE, LOG_DIR)

# ── Redirigir stderr a log en modo sin consola (Windows .pyw) ─────────────────
if not sys.stderr or sys.stderr.fileno() < 0:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _stderr_log = open(LOG_DIR / "stderr.log", "a", encoding="utf-8", buffering=1)
        sys.stderr = _stderr_log
        sys.stdout = _stderr_log
        log.info("stdout/stderr redirigidos a stderr.log")
    except Exception:
        pass

# ── Carpetas necesarias ────────────────────────────────────────────────────────
try:
    from core.config_loader import get_config as _gc
    _gc().temp_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Splash screen
# ─────────────────────────────────────────────────────────────────────────────
from PyQt5.QtWidgets import QApplication, QSplashScreen, QMessageBox
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QBrush
from PyQt5.QtCore import Qt


class SplashScreen(QSplashScreen):
    def __init__(self) -> None:
        pm = self._build_pixmap()
        super().__init__(pm)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

    @staticmethod
    def _build_pixmap() -> QPixmap:
        pm = QPixmap(540, 310)
        p  = QPainter(pm)
        g  = QLinearGradient(0, 0, 0, 310)
        g.setColorAt(0, QColor("#245D8A"))
        g.setColorAt(1, QColor("#1F4E79"))
        p.fillRect(0, 0, 540, 310, QBrush(g))
        p.fillRect(0, 0, 540, 5, QColor("#4A90D9"))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Segoe UI", 22, QFont.Bold))
        p.drawText(30, 78, "⚡  JES⚡THOR V1")
        p.setPen(QColor("#8DB4D8"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(30, 104, "v1.0  —  Sistema Profesional de Gestión Documental")
        if "--safe-mode" in sys.argv or os.environ.get("GESTOR_SAFE_MODE", "0") == "1":
            p.setPen(QColor("#FBD38D"))
            p.setFont(QFont("Segoe UI", 10, QFont.Bold))
            p.drawText(30, 130, "⚠  MODO SEGURO ACTIVO")
        p.setPen(QColor("#2563A8"))
        p.drawLine(30, 140 if SAFE_MODE else 120, 510, 140 if SAFE_MODE else 120)
        p.setPen(QColor("#2A5070"))
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(30, 295, "Python · PyQt5 · SQLite · Tesseract OCR  ·  © 2025 JAMF")
        p.end()
        return pm

    def update_message(self, msg: str) -> None:
        pm = self.pixmap().copy()
        p  = QPainter(pm)
        p.fillRect(30, 148, 480, 28, QColor("#1F4E79"))
        p.setPen(QColor("#8DB4D8"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(30, 168, f"⏳  {msg}")
        p.end()
        self.setPixmap(pm)
        QApplication.processEvents()


def _apply_app_style(app: QApplication) -> None:
    """F-FIX: Aplica estilo Fusion + tema guardado en BD para contraste WCAG."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    try:
        from ui.theme import load_and_apply_theme
        from database.manager import DatabaseManager
        db = DatabaseManager()
        load_and_apply_theme(db, app)
    except Exception:
        # Fallback a paleta claro estándar (contraste garantizado)
        from PyQt5.QtGui import QPalette
        pal = app.palette()
        pal.setColor(QPalette.Window,          QColor("#F5F7FA"))
        pal.setColor(QPalette.WindowText,      QColor("#1A202C"))
        pal.setColor(QPalette.Base,            QColor("#FFFFFF"))
        pal.setColor(QPalette.AlternateBase,   QColor("#EDF2F7"))
        pal.setColor(QPalette.Button,          QColor("#EDF2F7"))
        pal.setColor(QPalette.ButtonText,      QColor("#1A202C"))
        pal.setColor(QPalette.Highlight,       QColor("#1F4E79"))
        pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        app.setPalette(pal)


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── QApplication ─────────────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("JES⚡THOR V1")
    app.setApplicationVersion("1.0")
    _apply_app_style(app)

    # FIX-1: Desactivar cierre automático al no haber ventanas visibles.
    # Sin esto, cuando el QDialog de login se cierra ANTES de que MainWindow
    # sea visible, la app termina silenciosamente.
    app.setQuitOnLastWindowClosed(False)

    # Instalar el handler de mensajes Qt DESPUÉS de crear QApplication
    setup_qt_message_handler()

    # ── Splash ───────────────────────────────────────────────────────────────
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # Almacena la ventana principal como atributo de app para evitar GC
    app._main_window = None

    try:
        # ── Pasos de carga ────────────────────────────────────────────────────
        steps = [
            ("Verificando base de datos...",     0.15),
            ("Inicializando módulos...",          0.15 if not SAFE_MODE else 0.05),
            ("Preparando motor de reglas...",     0.10),
            ("Preparando interfaz...",            0.05),
        ]
        for msg, delay in steps:
            splash.update_message(msg)
            time.sleep(delay)
            app.processEvents()

        if SAFE_MODE:
            splash.update_message("⚠  Modo Seguro — sin OCR/IA/informes")
            time.sleep(0.2)
            app.processEvents()

        # ── Login ─────────────────────────────────────────────────────────────
        splash.update_message("Abriendo pantalla de acceso...")
        time.sleep(0.05)

        from ui.login_window import LoginWindow
        login = LoginWindow(safe_mode=SAFE_MODE)
        splash.finish(login)

        result = login.exec_()
        usuario = login.usuario_logueado

        if result == LoginWindow.Accepted and usuario:
            log.info("Login exitoso: %s [%s]", usuario.get("usuario"), usuario.get("rol"))

            # FIX-2 + FIX-3: Crear MainWindow ANTES de destruir el login,
            # y guardar referencia permanente en app para evitar GC.
            try:
                from ui.main_window import MainWindow
                app._main_window = MainWindow(usuario, safe_mode=SAFE_MODE)
                app._main_window.show()
                log.info("MainWindow visible")
            except Exception as exc:
                log.critical("Error al crear MainWindow: %s\n%s",
                             exc, traceback.format_exc())
                QMessageBox.critical(
                    None, "Error al abrir la aplicación",
                    f"No se pudo inicializar la ventana principal:\n\n{exc}\n\n"
                    f"Logs en: {LOG_DIR}\n\n"
                    f"Intenta arrancar con:  python GESTOR_PRO.pyw --safe-mode"
                )
                # Reactivar el cierre normal para que la app pueda salir limpiamente
                app.setQuitOnLastWindowClosed(True)
                app.quit()
                return

            # Reactivar cierre normal ahora que MainWindow está visible
            app.setQuitOnLastWindowClosed(True)
            sys.exit(app.exec_())

        else:
            log.info("Login cancelado o fallido — cerrando aplicación.")
            # Reactivar y salir limpiamente
            app.setQuitOnLastWindowClosed(True)
            app.quit()

    except Exception as exc:
        # FIX-5: Cualquier excepción de arranque muestra diálogo y escribe log
        tb_str = traceback.format_exc()
        log.critical("ERROR CRÍTICO en arranque:\n%s", tb_str)
        try:
            QMessageBox.critical(
                None, "Error crítico de arranque",
                f"No se pudo iniciar JES⚡THOR V1:\n\n{exc}\n\n"
                f"Logs detallados en:\n{LOG_DIR}\n\n"
                f"Prueba con: python GESTOR_PRO.pyw --safe-mode"
            )
        except Exception:
            pass
        app.setQuitOnLastWindowClosed(True)
        app.quit()


if __name__ == "__main__":
    main()
