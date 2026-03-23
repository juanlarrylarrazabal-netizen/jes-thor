# -*- coding: utf-8 -*-
"""
ia/ai_service.py — B-FIX: Servicio IA unificado (AiBus).
- Gemini 2.5-flash  
- Ollama local con timeout, reintentos y backoff  
- Memoria compartida por hash_pdf + (prov_id, tipo)
- Thread-safe (QThread-compatible)
"""
from __future__ import annotations
import json
import time
from typing import Optional, Dict

from core.logging_config import get_logger
log = get_logger("ai_service")

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_OLLAMA_RETRIES = 2
_OLLAMA_BACKOFF = 1.5  # seconds between retries


class AiBus:
    """
    Punto de entrada unificado para toda la IA del proyecto.
    Uso:
        bus = AiBus(db)
        result = bus.ejecutar_instruccion("Extrae CIF y base", ocr_text)
    """

    def __init__(self, db=None, motor: str = "gemini"):
        self.db = db
        self.motor = motor  # "gemini" | "ollama"
        self._client = None

    def set_motor(self, motor: str):
        self.motor = motor
        self._client = None  # reset client on change

    def _get_client(self):
        if self._client is None:
            from ia.cliente import get_ia_client
            self._client = get_ia_client(self.db, self.motor)
        return self._client

    def _call_with_retry(self, fn, *args, **kwargs):
        """Calls fn with retries + backoff for Ollama; Gemini gets 1 attempt."""
        max_tries = _OLLAMA_RETRIES + 1 if self.motor == "ollama" else 1
        last_exc = None
        for attempt in range(max_tries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_tries - 1:
                    time.sleep(_OLLAMA_BACKOFF * (attempt + 1))
                    self._client = None  # reset for fresh connection
                    log.warning("IA retry %d/%d: %s", attempt + 2, max_tries, exc)
        raise last_exc

    def ejecutar_instruccion(self, instruccion: str, ocr_text: str,
                              campos_actuales: dict = None) -> dict:
        """Ejecuta instrucción libre. Retorna JSON de sugerencias."""
        client = self._get_client()
        return self._call_with_retry(
            client.ejecutar_instruccion, instruccion, ocr_text, campos_actuales
        )

    def sugerir_para_visor(self, ocr_text: str) -> dict:
        """Sugiere trigger, proveedor y campos para el visor de reglas."""
        client = self._get_client()
        return self._call_with_retry(client.sugerir_para_visor, ocr_text)

    # ── Memoria compartida ────────────────────────────────────────────────────

    def memory_get(self, hash_pdf: str = None, prov_id: int = None, tipo: str = "") -> Optional[dict]:
        if not self.db: return None
        try: return self.db.ia_memory_get(hash_pdf=hash_pdf, prov_id=prov_id, tipo=tipo)
        except Exception: return None

    def memory_set(self, memo: dict, hash_pdf: str = None,
                   prov_id: int = None, tipo: str = "") -> None:
        if not self.db: return
        try: self.db.ia_memory_set(memo, hash_pdf=hash_pdf, prov_id=prov_id, tipo=tipo)
        except Exception as e: log.debug("ia_memory_set failed: %s", e)

    def memory_load_for_pdf(self, ruta_pdf: str, prov_id: int = None) -> Optional[dict]:
        """Carga memo por hash del PDF real."""
        try:
            import hashlib
            with open(ruta_pdf, "rb") as f:
                hash_pdf = hashlib.sha256(f.read()).hexdigest()
            return self.memory_get(hash_pdf=hash_pdf, prov_id=prov_id)
        except Exception:
            return None

    def memory_save_for_pdf(self, ruta_pdf: str, memo: dict, prov_id: int = None) -> None:
        """Guarda memo por hash del PDF real."""
        try:
            import hashlib
            with open(ruta_pdf, "rb") as f:
                hash_pdf = hashlib.sha256(f.read()).hexdigest()
            self.memory_set(memo, hash_pdf=hash_pdf, prov_id=prov_id)
        except Exception as e:
            log.debug("memory_save_for_pdf failed: %s", e)


def get_ai_bus(db=None, motor: str = None) -> AiBus:
    """Factory con motor leído de BD si no se especifica."""
    if motor is None and db:
        try: motor = db.get_config_ui("visor_ia_motor", "gemini")
        except Exception: motor = "gemini"
    return AiBus(db=db, motor=motor or "gemini")
