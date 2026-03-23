# -*- coding: utf-8 -*-
"""
Logging estructurado — V15.2 con rotación, faulthandler y ID de correlación.

NUEVO EN V15.2:
  - RotatingFileHandler (5×5 MB) en lugar de FileHandler simple
  - setup_excepthook(): captura excepciones Python no manejadas
  - setup_qt_message_handler(): captura qWarning / qCritical
  - setup_faulthandler(): volcado de traza en crash nativo (SIGSEGV, etc.)
  - LOG_DIR configurable por variable de entorno GESTOR_LOG_DIR
  - Modo DEBUG si GESTOR_DEBUG=1
"""
import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Variable de contexto: ID de factura activa para correlación ───────────────
_invoice_ctx: ContextVar[str] = ContextVar("invoice_id", default="-")


def set_invoice_context(invoice_id: str) -> None:
    _invoice_ctx.set(str(invoice_id))


def clear_invoice_context() -> None:
    _invoice_ctx.set("-")


# ── Directorio de logs ────────────────────────────────────────────────────────
def _default_log_dir() -> Path:
    """Devuelve el directorio de logs por defecto según la plataforma."""
    env = os.environ.get("GESTOR_LOG_DIR")
    if env:
        return Path(env)
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "JesThor" / "logs"
    elif platform.system() == "Darwin":
        return Path.home() / "Library" / "Logs" / "JesThor"
    else:
        return Path.home() / ".local" / "share" / "JesThor" / "logs"


LOG_DIR: Path = _default_log_dir()

# Referencia al file handler (para cambiar ruta desde Ajustes)
_file_handler: Optional[logging.Handler] = None


# ── Filtros y formateadores ───────────────────────────────────────────────────
class InvoiceContextFilter(logging.Filter):
    """Añade el ID de factura activo a cada registro."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.invoice_id = _invoice_ctx.get()
        return True


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:<8}{self.RESET}"
        return super().format(record)


# ── Configuración central ─────────────────────────────────────────────────────
def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
    log_dir: Optional[Path] = None,
) -> None:
    """
    Configura el sistema de logging una sola vez.
    Seguro si se llama más de una vez (idempotente).
    """
    global LOG_DIR, _file_handler

    if log_dir:
        LOG_DIR = Path(log_dir)

    # Modo debug por variable de entorno
    if os.environ.get("GESTOR_DEBUG", "0") == "1":
        level = "DEBUG"

    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger("gestor")
    root.setLevel(log_level)

    if root.handlers:
        return  # ya configurado

    fmt_file = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | thd=%(thread)d | invoice=%(invoice_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_console = ColorFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    ctx_filter = InvoiceContextFilter()

    if log_to_console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt_console)
        ch.addFilter(ctx_filter)
        root.addHandler(ch)

    if log_to_file:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_file = LOG_DIR / f"gestor_{datetime.now():%Y%m}.log"
            fh = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            fh.setFormatter(fmt_file)
            fh.addFilter(ctx_filter)
            root.addHandler(fh)
            _file_handler = fh
        except OSError as e:
            root.warning("No se pudo crear el archivo de log: %s", e)

    root.info(
        "=== JES⚡THOR V1 iniciado | Python %s | %s | PID=%d ===",
        sys.version.split()[0], platform.system(), os.getpid()
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"gestor.{name}")


def get_log_dir() -> Path:
    return LOG_DIR


# ── faulthandler: volcado de traza en crash nativo ────────────────────────────
def setup_faulthandler() -> None:
    """
    Activa faulthandler para obtener un stack trace en crash nativo
    (SIGSEGV, SIGABRT, etc.). Escribe a un fichero de crash.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        crash_file = LOG_DIR / "crash_dump.txt"
        fh = open(crash_file, "a", encoding="utf-8")
        fh.write(f"\n{'='*60}\nCrash dump iniciado: {datetime.now()}\n{'='*60}\n")
        fh.flush()
        faulthandler.enable(file=fh)
    except Exception:
        # Sin log dir, al menos activar en stderr
        faulthandler.enable()


# ── sys.excepthook global ─────────────────────────────────────────────────────
def setup_excepthook() -> None:
    """
    Instala un manejador global de excepciones no capturadas.
    NUNCA cierra la app en silencio: registra el error y muestra un diálogo.
    """
    _log = get_logger("excepthook")

    def _handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        incident_id = str(uuid.uuid4())[:8].upper()
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

        _log.critical(
            "EXCEPCIÓN NO CAPTURADA [ID=%s]\n%s",
            incident_id, tb_str
        )

        # Guardar en archivo de incidentes
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            inc_file = LOG_DIR / f"incident_{incident_id}.log"
            inc_file.write_text(
                f"ID: {incident_id}\nFecha: {datetime.now()}\n\n{tb_str}",
                encoding="utf-8"
            )
        except Exception:
            pass

        # Mostrar diálogo si hay QApplication activa
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Error Inesperado")
                msg.setText(
                    f"<b>Error inesperado (ID: {incident_id})</b><br><br>"
                    f"<code>{exc_type.__name__}: {exc_value}</code><br><br>"
                    f"El log completo está en:<br>"
                    f"<code>{LOG_DIR}</code>"
                )
                msg.setDetailedText(tb_str)
                msg.addButton("Continuar", QMessageBox.AcceptRole)
                btn_quit = msg.addButton("Cerrar aplicación", QMessageBox.RejectRole)
                msg.exec_()
                if msg.clickedButton() == btn_quit:
                    app.quit()
        except Exception:
            # Sin Qt, imprimir por stderr como fallback
            print(f"\n[ERROR {incident_id}]\n{tb_str}", file=sys.stderr)

    sys.excepthook = _handler


# ── qInstallMessageHandler para mensajes Qt ───────────────────────────────────
def setup_qt_message_handler() -> None:
    """
    Captura qDebug/qWarning/qCritical/qFatal y los redirige al sistema de logging.
    """
    _log = get_logger("qt")
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

        def _qt_handler(msg_type, context, message):
            if msg_type == QtMsgType.QtDebugMsg:
                _log.debug("[Qt] %s", message)
            elif msg_type == QtMsgType.QtInfoMsg:
                _log.info("[Qt] %s", message)
            elif msg_type == QtMsgType.QtWarningMsg:
                _log.warning("[Qt] %s (%s:%d)", message,
                             context.file or "?", context.line or 0)
            elif msg_type == QtMsgType.QtCriticalMsg:
                _log.error("[Qt CRITICAL] %s", message)
            elif msg_type == QtMsgType.QtFatalMsg:
                _log.critical("[Qt FATAL] %s", message)

        qInstallMessageHandler(_qt_handler)
    except Exception as e:
        get_logger("logging_config").warning(
            "No se pudo instalar qInstallMessageHandler: %s", e
        )
