# -*- coding: utf-8 -*-
"""
Jerarquía de excepciones propias del sistema.
Permite distinguir errores de dominio de errores de librería.
"""


class GestorError(Exception):
    """Excepción base del sistema."""
    pass


# ── Ingesta ──────────────────────────────────────────────────────────────────

class IngestError(GestorError):
    """Error durante descarga/parsing de correo."""
    pass

class AuthError(IngestError):
    """Fallo de autenticación con el servidor de correo."""
    pass

class AttachmentError(IngestError):
    """No se pudo extraer el adjunto."""
    pass

class DuplicateInvoiceError(IngestError):
    """La factura ya fue procesada (deduplicación por hash)."""
    def __init__(self, file_hash: str):
        self.file_hash = file_hash
        super().__init__(f"Factura ya procesada (hash={file_hash[:16]}...)")


# ── OCR ──────────────────────────────────────────────────────────────────────

class OCRError(GestorError):
    """Error en el pipeline OCR."""
    pass

class TesseractNotFoundError(OCRError):
    """Tesseract no está instalado o no está en el PATH."""
    pass

class PDFReadError(OCRError):
    """No se pudo leer el archivo PDF."""
    pass


# ── Reglas / Clasificación ────────────────────────────────────────────────────

class RuleError(GestorError):
    """Error en el motor de reglas."""
    pass

class ClassificationError(GestorError):
    """No se pudo clasificar la factura."""
    pass

class NoRuleMatchError(ClassificationError):
    """Ninguna regla coincidió (fallback necesario)."""
    pass


# ── Watermark ─────────────────────────────────────────────────────────────────

class WatermarkError(GestorError):
    """Error al estampar el PDF."""
    pass

class AlreadyStampedError(WatermarkError):
    """El PDF ya contiene el sello (idempotencia)."""
    pass


# ── Storage ───────────────────────────────────────────────────────────────────

class StorageError(GestorError):
    """Error al guardar o mover archivos."""
    pass


# ── Configuración ─────────────────────────────────────────────────────────────

class ConfigError(GestorError):
    """Configuración inválida o faltante."""
    pass

class LicenseError(GestorError):
    """Licencia expirada o inválida."""
    pass
