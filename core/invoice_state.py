# -*- coding: utf-8 -*-
"""
core/invoice_state.py — InvoiceRuleState
Estado compartido (single source of truth) para Visor y Editor de Reglas.

Cada campo lleva su "origen": manual | regla | ia | ocr | ''
Emite señales cuando cambia para refrescar la UI.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_ORIGINS = ("manual", "regla", "ia", "ocr", "")


class InvoiceRuleState(QObject if _HAS_QT else object):
    """
    Fuente de verdad única para todos los campos de factura + regla.
    Todos los formularios del Visor y del Editor de Reglas leen/escriben aquí.
    """

    if _HAS_QT:
        # Señal emitida cuando CUALQUIER campo cambia → la UI que escucha debe refrescarse
        changed = pyqtSignal(str, object)   # (campo, valor_nuevo)
        # Señal cuando se aplica una regla completa
        regla_aplicada = pyqtSignal(dict)

    def __init__(self, parent=None):
        if _HAS_QT:
            super().__init__(parent)
        else:
            super().__init__()

        # ── Proveedor ──────────────────────────────────────────────────────────
        self._proveedor_id:   Optional[int] = None
        self._proveedor_nombre: str = ""
        self._proveedor_origen: str = ""

        # ── Número de factura y Serie ──────────────────────────────────────────
        self._numero_factura: str = ""
        self._numero_origen:  str = ""
        self._serie:          str = ""
        self._serie_origen:   str = ""

        # ── Cuentas contables ──────────────────────────────────────────────────
        self._cuenta_proveedor:    str = ""
        self._subcuenta_proveedor: str = ""
        self._cuenta_gasto:        str = ""
        self._subcuenta_gasto:     str = ""

        # ── Datos financieros ──────────────────────────────────────────────────
        self._cif:            str = ""
        self._razon_social:   str = ""
        self._base_imponible: str = ""
        self._iva:            str = ""
        self._total:          str = ""

        # ── Clasificación ──────────────────────────────────────────────────────
        self._tipo_factura:    str = ""
        self._categoria:       str = ""
        self._es_rectificativa: bool = False
        self._id_regla_aplicada: Optional[int] = None
        self._nombre_regla:    str = ""     # trigger: nombre de la regla aplicada

        # ── Triggers (múltiples, normalizados) ────────────────────────────────
        self._triggers: List[str] = []

        # ── Zonas/regiones (coords normalizadas 0..1) ─────────────────────────
        self._zonas: Dict[str, Any] = {}

    # ── Helpers internos ───────────────────────────────────────────────────────

    def _set(self, campo: str, valor, emit: bool = True):
        attr = f"_{campo}"
        if hasattr(self, attr) and getattr(self, attr) == valor:
            return
        setattr(self, attr, valor)
        if emit and _HAS_QT:
            try:
                self.changed.emit(campo, valor)
            except Exception:
                pass

    # ── Setters con origen ────────────────────────────────────────────────────

    def set_proveedor(self, pid: Optional[int], nombre: str, origen: str = ""):
        self._proveedor_id = pid
        self._set("proveedor_nombre", nombre)
        self._proveedor_origen = origen

    def set_numero_factura(self, val: str, origen: str = "ocr"):
        # Precedencia: manual > regla > ia > ocr — no sobreescribir si ya hay uno mejor
        prec = _ORIGINS.index(origen) if origen in _ORIGINS else 99
        cur_prec = _ORIGINS.index(self._numero_origen) if self._numero_origen in _ORIGINS else 99
        if not self._numero_factura or prec <= cur_prec:
            self._numero_origen = origen
            self._set("numero_factura", val)

    def set_serie(self, val: str, origen: str = "ocr"):
        prec = _ORIGINS.index(origen) if origen in _ORIGINS else 99
        cur_prec = _ORIGINS.index(self._serie_origen) if self._serie_origen in _ORIGINS else 99
        if not self._serie or prec <= cur_prec:
            self._serie_origen = origen
            self._set("serie", val)

    def set_cif(self, val: str):           self._set("cif", val)
    def set_razon_social(self, val: str):  self._set("razon_social", val)
    def set_base_imponible(self, val: str): self._set("base_imponible", val)
    def set_iva(self, val: str):            self._set("iva", val)
    def set_total(self, val: str):          self._set("total", val)
    def set_tipo_factura(self, val: str):  self._set("tipo_factura", val)
    def set_categoria(self, val: str):     self._set("categoria", val)
    def set_es_rectificativa(self, val: bool): self._set("es_rectificativa", val)

    def set_cuenta_proveedor(self, cta: str, sub: str = ""):
        self._set("cuenta_proveedor", cta)
        self._set("subcuenta_proveedor", sub)

    def set_cuenta_gasto(self, cta: str, sub: str = ""):
        self._set("cuenta_gasto", cta)
        self._set("subcuenta_gasto", sub)

    def set_triggers(self, triggers: List[str]):
        self._set("triggers", list(triggers))

    def set_zona(self, key: str, coords: Any):
        self._zonas[key] = coords

    def set_regla(self, id_regla: Optional[int], nombre: str):
        self._id_regla_aplicada = id_regla
        self._set("nombre_regla", nombre)

    # ── Aplicar bloque set_* de motor determinista ─────────────────────────────

    def apply_rule_set(self, resultado: dict):
        """
        Aplica el bloque 'set' devuelto por el motor directamente al estado.
        Emite regla_aplicada al final.
        """
        if resultado.get("set_cuenta_proveedor"):
            self.set_cuenta_proveedor(
                resultado["set_cuenta_proveedor"],
                resultado.get("set_subcuenta_proveedor", ""))
        if resultado.get("set_cuenta_gasto"):
            self.set_cuenta_gasto(
                resultado["set_cuenta_gasto"],
                resultado.get("set_subcuenta_gasto", ""))
        if resultado.get("set_serie"):
            self.set_serie(resultado["set_serie"], "regla")
        if resultado.get("set_categoria"):
            self.set_categoria(resultado["set_categoria"])
        if resultado.get("set_tipo_factura"):
            self.set_tipo_factura(resultado["set_tipo_factura"])
        nombre = resultado.get("nombre_regla", "")
        rid    = resultado.get("id_regla")
        self.set_regla(rid, nombre)
        if _HAS_QT:
            try:
                self.regla_aplicada.emit(resultado)
            except Exception:
                pass

    # ── Getters ────────────────────────────────────────────────────────────────

    @property
    def proveedor_id(self) -> Optional[int]:   return self._proveedor_id
    @property
    def proveedor_nombre(self) -> str:          return self._proveedor_nombre
    @property
    def numero_factura(self) -> str:            return self._numero_factura
    @property
    def numero_origen(self) -> str:             return self._numero_origen
    @property
    def serie(self) -> str:                     return self._serie
    @property
    def serie_origen(self) -> str:              return self._serie_origen
    @property
    def cif(self) -> str:                       return self._cif
    @property
    def razon_social(self) -> str:              return self._razon_social
    @property
    def base_imponible(self) -> str:            return self._base_imponible
    @property
    def iva(self) -> str:                       return self._iva
    @property
    def total(self) -> str:                     return self._total
    @property
    def tipo_factura(self) -> str:              return self._tipo_factura
    @property
    def categoria(self) -> str:                 return self._categoria
    @property
    def es_rectificativa(self) -> bool:         return self._es_rectificativa
    @property
    def cuenta_proveedor(self) -> str:          return self._cuenta_proveedor
    @property
    def subcuenta_proveedor(self) -> str:       return self._subcuenta_proveedor
    @property
    def cuenta_gasto(self) -> str:              return self._cuenta_gasto
    @property
    def subcuenta_gasto(self) -> str:           return self._subcuenta_gasto
    @property
    def id_regla_aplicada(self) -> Optional[int]: return self._id_regla_aplicada
    @property
    def nombre_regla(self) -> str:              return self._nombre_regla
    @property
    def triggers(self) -> List[str]:            return list(self._triggers)
    @property
    def zonas(self) -> Dict[str, Any]:          return dict(self._zonas)

    def to_dict(self) -> dict:
        """Exporta todos los campos como dict para persistir en BD."""
        return {
            "proveedor_id":        self._proveedor_id,
            "nombre_proveedor":    self._proveedor_nombre,
            "numero_factura":      self._numero_factura,
            "serie_factura":       self._serie,
            "cif_nif":             self._cif,
            "razon_social":        self._razon_social,
            "base_imponible":      self._base_imponible,
            "iva":                 self._iva,
            "total":               self._total,
            "tipo_factura":        self._tipo_factura,
            "categoria":           self._categoria,
            "es_rectificativa":    1 if self._es_rectificativa else 0,
            "cuenta_proveedor":    self._cuenta_proveedor,
            "subcuenta_proveedor": self._subcuenta_proveedor,
            "cuenta_gasto":        self._cuenta_gasto,
            "subcuenta_gasto":     self._subcuenta_gasto,
            "id_regla_aplicada":   self._id_regla_aplicada,
            "nombre_regla":        self._nombre_regla,
        }

    def load_from_dict(self, d: dict):
        """Carga todos los campos desde un dict (sin emitir señales individuales)."""
        self._proveedor_id = d.get("proveedor_id") or d.get("id_proveedor")
        self._proveedor_nombre = d.get("nombre_proveedor") or d.get("nombre", "")
        self._numero_factura = str(d.get("numero_factura", "") or "")
        self._serie = str(d.get("serie_factura") or d.get("serie", "") or "")
        self._cif = str(d.get("cif_nif") or d.get("cif_proveedor", "") or "")
        self._razon_social = str(d.get("razon_social", "") or "")
        self._base_imponible = str(d.get("base_imponible") or d.get("base_amount", "") or "")
        self._iva = str(d.get("iva") or d.get("vat_amount", "") or "")
        self._total = str(d.get("total") or d.get("total_amount", "") or "")
        self._tipo_factura = str(d.get("tipo_factura", "") or "")
        self._categoria = str(d.get("categoria", "") or "")
        self._es_rectificativa = bool(d.get("es_rectificativa", False))
        self._cuenta_proveedor = str(d.get("cuenta_proveedor", "") or "")
        self._subcuenta_proveedor = str(d.get("subcuenta_proveedor", "") or "")
        self._cuenta_gasto = str(d.get("cuenta_gasto", "") or "")
        self._subcuenta_gasto = str(d.get("subcuenta_gasto", "") or "")
        self._id_regla_aplicada = d.get("id_regla_aplicada")
        self._nombre_regla = str(d.get("nombre_regla") or d.get("trigger_aplicado", "") or "")
        # Emit batch update
        if _HAS_QT:
            try:
                self.changed.emit("__all__", None)
            except Exception:
                pass
