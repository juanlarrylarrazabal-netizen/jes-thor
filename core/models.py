# -*- coding: utf-8 -*-
"""
Modelos de dominio del Gestor de Facturas.
Contratos inmutables entre capas: Invoice, Vendor, Rule, ClassificationResult.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


# ── Enums ────────────────────────────────────────────────────────────────────

class InvoiceStatus(str, Enum):
    PENDING   = "pendiente"
    PROCESSED = "procesada"
    ERROR     = "error"
    DUPLICATE = "duplicado"

class RuleType(str, Enum):
    KEYWORD  = "keyword"
    REGEX    = "regex"
    CIF      = "cif"
    FALLBACK = "fallback"

class LicenseType(str, Enum):
    TRIAL = "TRIAL"
    FULL  = "FULL"
    NONE  = "NONE"


# ── Vendor (Proveedor) ────────────────────────────────────────────────────────

@dataclass
class Vendor:
    id:               int
    name:             str           # Nombre/razón social
    vendor_code:      str           # Número de proveedor (ej. "PRV-0042")
    expense_account:  str           # Cuenta contable (ej. "628000")
    category:         str           # Carpeta destino
    cif_nif:          Optional[str] = None
    address:          Optional[str] = None
    email:            Optional[str] = None
    iban:             Optional[str] = None
    is_variable:      bool = False   # Si True: la regla no aplica automáticamente
    created_at:       Optional[datetime] = None

    @property
    def display_name(self) -> str:
        return f"{self.name} [{self.vendor_code}]"


# ── Rule (Regla de clasificación) ────────────────────────────────────────────

@dataclass
class Rule:
    id:          int
    vendor_id:   int
    trigger:     str            # Texto disparador (keyword / regex) — columna 'serie' en BD
    rule_type:   RuleType       = RuleType.KEYWORD
    account:     str            = ""
    category:    str            = ""
    priority:    int            = 1
    active:      bool           = True
    description: str            = ""
    vendor_name: Optional[str]  = None  # Join desde vendor
    vendor_code: Optional[str]  = None
    serie:       str            = ""    # mismo valor que trigger (columna 'serie' en BD)
    subcuenta_gasto: str        = ""    # subcuenta contable de la regla


# ── InvoiceFields (Campos extraídos del PDF) ─────────────────────────────────

@dataclass
class InvoiceFields:
    invoice_number:   Optional[str]   = None
    issue_date:       Optional[datetime] = None
    due_date:         Optional[datetime] = None
    vendor_name:      Optional[str]   = None
    cif_nif:          Optional[str]   = None
    base_amount:      Optional[float] = None
    vat_pct:          Optional[float] = None
    vat_amount:       Optional[float] = None
    total_amount:     Optional[float] = None
    # ── Tipo de IVA ───────────────────────────────────────────────────────────
    # Valores: 21 (general), 10 (reducido), 4 (superreducido), 0 (exento)
    # Default 21 para compatibilidad con facturas existentes
    tipo_iva:         int   = 21
    # ── Retención (IRPF u otras) ──────────────────────────────────────────────
    retention_pct:    Optional[float] = None   # % retención (ej: 15.0)
    retention_amount: Optional[float] = None   # importe retenido (negativo en contab.)
    # ── Reparto de gasto entre cuentas ───────────────────────────────────────
    # Lista de {"cuenta": "600000", "pct": 70.0, "importe": 700.0}
    reparto_cuentas:  Optional[list]  = None
    plate:            Optional[str]   = None  # Matrícula
    chassis:          Optional[str]   = None  # Bastidor
    raw_text:         str = ""
    extraction_method: str = "pdf_text"  # pdf_text | ocr | manual

    @property
    def has_minimum_fields(self) -> bool:
        return bool(self.invoice_number or self.total_amount)

    @property
    def liquido_percibido(self) -> Optional[float]:
        """Total - retención = lo que realmente cobra el proveedor."""
        if self.total_amount is not None and self.retention_amount is not None:
            return round(self.total_amount - self.retention_amount, 2)
        return self.total_amount


# ── ClassificationResult ──────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    vendor:         Optional[Vendor]  = None
    rule:           Optional[Rule]    = None
    vendor_code:    str               = "S/C"
    expense_account:str               = ""
    category:       str               = "VARIOS"
    confidence:     float             = 0.0
    explanation:    str               = ""   # Por qué se asignó este proveedor
    is_fallback:    bool              = False
    # True cuando varios proveedores variables coinciden — visor pide confirmación
    needs_manual:   bool              = False
    
    # --- NUEVOS CAMPOS ---
    regla_id:              Optional[int] = None
    nombre_regla:          str = ""
    set_cuenta_prov:       str = ""
    set_subcuenta_prov:    str = ""
    set_subcuenta_gasto:   str = ""
    set_serie:             str = ""
    set_tipo_factura:      str = ""
    serie_regla:           str = ""
    numero_factura_regla:  str = ""
    candidates:            list = field(default_factory=list)
    # ---------------------

    @property
    def is_classified(self) -> bool:
        return self.vendor is not None and self.vendor_code != "S/C"


# ── Invoice (Factura completa) ─────────────────────────────────────────────────

@dataclass
class Invoice:
    id:                 Optional[int]       = None
    file_path:          str                 = ""
    file_hash:          str                 = ""
    file_name:          str                 = ""
    status:             InvoiceStatus       = InvoiceStatus.PENDING
    fields:             InvoiceFields       = field(default_factory=InvoiceFields)
    classification:     ClassificationResult = field(default_factory=ClassificationResult)
    source:             str                 = "manual"   # manual | gmail | imap
    email_subject:      str                 = ""
    email_sender:       str                 = ""
    email_date:         Optional[datetime]  = None
    processed_at:       Optional[datetime]  = None
    final_path:         str                 = ""
    is_stamped:         bool                = False
    errors:             List[str]           = field(default_factory=list)
    metadata:           Dict[str, Any]      = field(default_factory=dict)
    
    # --- CAMPOS PARA NÚMERO DE FACTURA ---
    numero_factura_manual: str = ""   # Número capturado manualmente por el usuario
    serie_manual: str = ""            # Serie capturada manualmente
    numero_factura_ia: str = ""       # Número sugerido por IA
    # ------------------------------------

    def add_error(self, msg: str) -> None:
        self.errors.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self.status = InvoiceStatus.ERROR


# ── EmailAccount ──────────────────────────────────────────────────────────────

@dataclass
class EmailAccount:
    email:       str
    password:    str
    host:        str  = "imap.gmail.com"
    port:        int  = 993
    use_ssl:     bool = True
    folder:      str  = "INBOX"
    is_primary:  bool = False
    active:      bool = True


# ── WatermarkConfig ───────────────────────────────────────────────────────────

@dataclass
class WatermarkConfig:
    template:   str   = "Prv: {vendor_code} | Cta: {expense_account}"
    x:          float = 50.0       # posición x (puntos PDF, 0=izq)
    y:          float = 50.0       # posición y desde abajo
    font_size:  int   = 10
    opacity:    float = 0.80
    color_r:    float = 1.0        # rojo
    color_g:    float = 0.0
    color_b:    float = 0.0
    all_pages:  bool  = False      # Si True, estampa todas las páginas
    stamp_marker: str = "__GESTPRO__"  # Marca de idempotencia en metadata

    def format_text(self, vendor_code: str, expense_account: str) -> str:
        return self.template.format(
            vendor_code=vendor_code,
            expense_account=expense_account
        )