# -*- coding: utf-8 -*-
"""
Cargador y validador de configuración.
Merge de config.yaml + variables de entorno (.env).
Singleton: se carga una vez y se cachea.
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

from core.exceptions import ConfigError
from core.models import WatermarkConfig


# Directorio raíz del proyecto (donde está config.yaml)
_ROOT = Path(__file__).parent.parent


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo: override sobreescribe base sin borrar claves no presentes."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_env_file(path: Path) -> Dict[str, str]:
    """Carga un archivo .env sin dependencias externas."""
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


@lru_cache(maxsize=1)
def get_config() -> "AppConfig":
    """Devuelve la configuración global (singleton cacheado)."""
    return AppConfig.load()


class AppConfig:
    """
    Wrapper tipado sobre el diccionario YAML.
    Provee acceso conveniente con valores por defecto.
    """
    def __init__(self, raw: dict) -> None:
        self._raw = raw

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        """
        Carga config.yaml, luego sobreescribe con .env y variables de entorno.
        Orden de prioridad (mayor → menor): ENV vars > .env > config.yaml > defaults.
        """
        cfg_path = config_path or (_ROOT / "config.yaml")

        # 1. Base: defaults hardcodeados
        raw: Dict[str, Any] = _defaults()

        # 2. config.yaml
        if cfg_path.exists():
            if not _HAS_YAML:
                raise ConfigError(
                    "PyYAML no instalado. Ejecuta: pip install pyyaml"
                )
            with open(cfg_path, encoding="utf-8") as fh:
                from_yaml = yaml.safe_load(fh) or {}
            raw = _deep_merge(raw, from_yaml)
        else:
            import warnings
            warnings.warn(f"config.yaml no encontrado en {cfg_path}. Usando valores por defecto.")

        # 3. .env
        env_vars = _load_env_file(_ROOT / ".env")
        os.environ.update(env_vars)

        # 4. Variables de entorno explícitas (sobreescriben todo)
        _apply_env_overrides(raw)

        return cls(raw)

    # ── Acceso rápido a secciones ──────────────────────────────────────────────

    def get(self, *keys: str, default: Any = None) -> Any:
        """Acceso anidado: cfg.get('ocr', 'tesseract_path')"""
        node = self._raw
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    # ── Propiedades tipadas ────────────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        raw = self.get("database", "path", default="./facturas.db")
        p = Path(raw)
        return p if p.is_absolute() else _ROOT / p

    @property
    def storage_root(self) -> str:
        return self.get("storage", "root", default="./facturas_dest")

    @property
    def temp_dir(self) -> Path:
        raw = self.get("storage", "temp_dir", default="./facturas_temp")
        p = Path(raw)
        return p if p.is_absolute() else _ROOT / p

    @property
    def months(self) -> Dict[int, str]:
        raw = self.get("storage", "months", default={})
        return {int(k): v for k, v in raw.items()}

    @property
    def categories(self) -> list:
        return self.get("storage", "categories", default=["VARIOS"])

    @property
    def watermark(self) -> WatermarkConfig:
        raw = self.get("watermark", default={})
        color = raw.get("color", [1.0, 0.0, 0.0])
        return WatermarkConfig(
            template      = raw.get("template", "Prv: {vendor_code} | Cta: {expense_account}"),
            x             = float(raw.get("x", 50.0)),
            y             = float(raw.get("y", 50.0)),
            font_size     = int(raw.get("font_size", 10)),
            opacity       = float(raw.get("opacity", 0.85)),
            color_r       = float(color[0]) if isinstance(color, list) else 1.0,
            color_g       = float(color[1]) if isinstance(color, list) else 0.0,
            color_b       = float(color[2]) if isinstance(color, list) else 0.0,
            all_pages     = bool(raw.get("all_pages", False)),
            stamp_marker  = raw.get("stamp_marker", "__GESTPRO_STAMPED__"),
        )

    @property
    def log_level(self) -> str:
        return self.get("app", "log_level", default="INFO").upper()

    @property
    def ocr_enabled(self) -> bool:
        return bool(self.get("ocr", "enabled", default=True))

    @property
    def tesseract_path(self) -> Optional[str]:
        val = self.get("ocr", "tesseract_path", default=None)
        return val or os.environ.get("TESSERACT_PATH")

    @property
    def ocr_languages(self) -> list:
        return self.get("ocr", "languages", default=["spa"])

    @property
    def ocr_fallback_threshold(self) -> int:
        return int(self.get("ocr", "ocr_fallback_threshold", default=50))

    @property
    def email_config(self) -> dict:
        return self.get("email", default={})

    @property
    def known_imap_hosts(self) -> dict:
        return self.get("email", "known_hosts", default={})

    @property
    def app_name(self) -> str:
        return self.get("app", "name", default="Gestor Facturas Pro")

    @property
    def version(self) -> str:
        return self.get("app", "version", default="8.0")

    def invoice_dest_path(self, year: int, month: int, category: str) -> Path:
        """Construye la ruta destino de una factura clasificada."""
        month_name = self.months.get(month, f"{month:02d}")
        return Path(self.storage_root) / str(year) / month_name / category


# ── Defaults internos ─────────────────────────────────────────────────────────

def _defaults() -> dict:
    return {
        "app":      {"name": "Gestor Facturas Pro", "version": "8.0", "log_level": "INFO"},
        "database": {"path": "./facturas.db", "wal_mode": True, "busy_timeout_ms": 30000},
        "storage":  {"root": "./facturas_dest", "temp_dir": "./facturas_temp",
                     "months": {i: f"{i:02d}" for i in range(1, 13)}, "categories": ["VARIOS"]},
        "email":    {"default_host": "imap.gmail.com", "default_port": 993, "use_ssl": True,
                     "folder": "INBOX", "fetch_limit": 50,
                     "subject_keywords": ["factura", "invoice", "abono"],
                     "accepted_extensions": [".pdf", ".png", ".jpg", ".jpeg"],
                     "max_retries": 3, "retry_backoff_s": 2.0, "known_hosts": {}},
        "ocr":      {"enabled": True, "tesseract_path": None, "languages": ["spa"],
                     "preprocessing": {"deskew": True, "binarize": True, "min_dpi": 200, "target_dpi": 300},
                     "ocr_fallback_threshold": 50, "timeout_per_page": 30},
        "rules":    {"fallback_category": "VARIOS", "fallback_vendor_code": "S/C",
                     "fuzzy_threshold": 0.75},
        "watermark":{"template": "Prv: {vendor_code} | Cta: {expense_account}",
                     "x": 50.0, "y": 50.0, "font_size": 10, "opacity": 0.85,
                     "color": [1.0, 0.0, 0.0], "all_pages": False,
                     "stamp_marker": "__GESTPRO_STAMPED__"},
        "license":  {"trial_days": 30, "license_file": "./licencia.lic"},
    }


def _apply_env_overrides(raw: dict) -> None:
    """
    Permite sobreescribir config.yaml con variables de entorno.
    Convención: GESTOR__SECTION__KEY=value  (doble guión bajo como separador)
    Ej: GESTOR__DATABASE__PATH=/tmp/facturas.db
    """
    prefix = "GESTOR__"
    for key, val in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("__")
        node = raw
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        # Conversión automática de tipos básicos
        last = parts[-1]
        if val.lower() in ("true", "1", "yes"):
            node[last] = True
        elif val.lower() in ("false", "0", "no"):
            node[last] = False
        else:
            try:
                node[last] = int(val)
            except ValueError:
                try:
                    node[last] = float(val)
                except ValueError:
                    node[last] = val
