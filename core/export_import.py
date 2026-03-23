# -*- coding: utf-8 -*-
"""
core/export_import.py — B: Motor de exportación/importación selectiva.
- Paquete ZIP con manifest.json + data/*.json
- Cifrado opcional AES-256 (usando pyzipper si disponible, o zipfile estándar)
- Importación con dry-run, merge/overwrite/skip, rollback transaccional
"""
from __future__ import annotations
import json
import hashlib
import io
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_VERSION    = "15.0"
SCHEMA_VERSION = "1.0"

# ── Normalización de nombres ───────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"\s+", "", "".join(c for c in s if unicodedata.category(c) != "Mn"))


# ── Exportación ───────────────────────────────────────────────────────────────

class Exporter:
    """
    Extrae datos de la BD según selección y los empaqueta en un ZIP.
    Componentes: proveedores, reglas, correo, ia, visual, carpetas, alertas, usuarios.
    """

    COMPONENTS = [
        "proveedores", "reglas", "correo", "ia",
        "visual", "carpetas", "alertas", "usuarios",
    ]

    def __init__(self, db):
        self.db = db

    def collect(self, components: List[str]) -> Dict[str, Any]:
        """Recoge datos para los componentes pedidos. Devuelve dict {comp: datos}."""
        data = {}
        for comp in components:
            fn = getattr(self, f"_collect_{comp}", None)
            if fn:
                try: data[comp] = fn()
                except Exception as exc:
                    data[comp] = {"__error__": str(exc)}
        return data

    def _collect_proveedores(self):
        rows = self.db.obtener_todos_proveedores()
        return {"items": rows, "count": len(rows)}

    def _collect_reglas(self):
        rows = self.db.obtener_todas_reglas_con_proveedor()
        plain = []
        for r in rows:
            plain.append({k: v for k, v in r.__dict__.items()}
                         if hasattr(r, '__dict__') else dict(r))
        return {"items": plain, "count": len(plain)}

    def _collect_correo(self):
        rows = self.db.obtener_cuentas_gmail()
        # Redactar contraseña — solo exportar si usuario quiere credenciales
        safe = []
        for r in (rows or []):
            row = dict(r)
            row["password"] = "__REDACTED__"
            safe.append(row)
        return {"items": safe, "count": len(safe), "note": "passwords redacted"}

    def _collect_ia(self):
        out = {}
        for motor in ("gemini", "ollama", "copilot"):
            try:
                cfg = self.db.get_ia_config(motor)
                # Redact keys
                safe = {k: ("__REDACTED__" if "key" in k.lower() or "secret" in k.lower() else v)
                        for k, v in cfg.items()}
                out[motor] = safe
            except Exception:
                pass
        out["motor_default"] = self.db.get_config_ui("visor_ia_motor", "gemini")
        return out

    def _collect_visual(self):
        keys = [
            "ui_tema", "ui_high_contrast", "logo_path", "fondo_path", "empresa_nombre",
            "wm_color", "wm_opacidad", "wm_campos", "serie_default",
        ]
        return {k: self.db.get_config_ui(k, "") for k in keys}

    def _collect_carpetas(self):
        keys = ["carpeta_facturas", "carpeta_informes", "carpeta_escaner",
                "carpeta_temp", "storage_root"]
        return {k: self.db.get_config_ui(k, "") for k in keys}

    def _collect_alertas(self):
        try:
            rows = self.db._get_all("SELECT * FROM alertas_config")
            return {"items": [dict(zip([d[0] for d in rows[0].description], r)) if hasattr(rows[0], 'description') else dict(r) for r in rows], "count": len(rows)}
        except Exception:
            try:
                rows = self.db._get_all("SELECT * FROM alertas_config")
                return {"items": [dict(r) for r in rows], "count": len(rows)}
            except Exception as e:
                return {"items": [], "count": 0, "error": str(e)}

    def _collect_usuarios(self):
        try:
            rows = self.db._get_all("SELECT id, usuario, rol, email FROM usuarios")
            return {"items": [dict(r) for r in rows], "count": len(rows)}
        except Exception as e:
            return {"items": [], "count": 0, "error": str(e)}

    def build_zip(self, data: Dict[str, Any], password: str = "") -> bytes:
        """
        Construye el ZIP exportado (con o sin cifrado AES-256).
        Retorna bytes del ZIP.
        """
        # Manifest
        manifest = {
            "app_version":    APP_VERSION,
            "schema_version": SCHEMA_VERSION,
            "fecha":          datetime.now().isoformat(),
            "componentes":    list(data.keys()),
            "checksum":       {},
        }
        # Build JSON files in memory
        files: Dict[str, bytes] = {}
        for comp, payload in data.items():
            raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode()
            files[f"data/{comp}.json"] = raw
            manifest["checksum"][comp] = hashlib.sha256(raw).hexdigest()

        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        files["manifest.json"] = manifest_bytes

        if password:
            return self._build_encrypted_zip(files, password)
        else:
            return self._build_plain_zip(files)

    def _build_plain_zip(self, files: Dict[str, bytes]) -> bytes:
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def _build_encrypted_zip(self, files: Dict[str, bytes], password: str) -> bytes:
        """AES-256 via pyzipper; fallback to unencrypted with warning comment."""
        try:
            import pyzipper  # type: ignore
            buf = io.BytesIO()
            with pyzipper.AESZipFile(buf, "w",
                                     compression=pyzipper.ZIP_DEFLATED,
                                     encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(password.encode())
                for name, content in files.items():
                    zf.writestr(name, content)
            return buf.getvalue()
        except ImportError:
            # Fallback: plain ZIP with note
            files["_ENCRYPTION_NOTE.txt"] = (
                b"pyzipper not installed - exported WITHOUT encryption.\n"
                b"Install with: pip install pyzipper --break-system-packages\n"
            )
            return self._build_plain_zip(files)

    def summary(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Resumen de conteos por componente."""
        out = {}
        for comp, payload in data.items():
            if isinstance(payload, dict):
                out[comp] = payload.get("count", len(payload.get("items", [])))
            else:
                out[comp] = 0
        return out


# ── Importación ───────────────────────────────────────────────────────────────

class Importer:
    """
    Importa datos desde un paquete ZIP de exportación.
    Soporta dry-run, merge/overwrite/skip, rollback.
    """

    def __init__(self, db):
        self.db = db

    def read_zip(self, zip_bytes: bytes, password: str = "") -> Tuple[dict, dict]:
        """
        Lee el ZIP y devuelve (manifest, data_by_component).
        Raises ValueError si el manifest no es válido o la versión no es compatible.
        """
        try:
            content = self._open_zip(zip_bytes, password)
        except Exception as exc:
            raise ValueError(f"No se pudo abrir el paquete: {exc}")

        if "manifest.json" not in content:
            raise ValueError("Paquete inválido: falta manifest.json")

        manifest = json.loads(content["manifest.json"])
        self._validate_manifest(manifest)

        data = {}
        for name, raw in content.items():
            if name.startswith("data/") and name.endswith(".json"):
                comp = name[5:-5]
                data[comp] = json.loads(raw)

        return manifest, data

    def _open_zip(self, zip_bytes: bytes, password: str) -> Dict[str, bytes]:
        """Opens zip (plain or AES-encrypted). Returns {filename: bytes}."""
        buf = io.BytesIO(zip_bytes)
        content = {}
        if password:
            try:
                import pyzipper  # type: ignore
                with pyzipper.AESZipFile(buf) as zf:
                    zf.setpassword(password.encode())
                    for name in zf.namelist():
                        content[name] = zf.read(name)
                return content
            except ImportError:
                pass  # fall through to plain
        import zipfile
        with zipfile.ZipFile(buf) as zf:
            for name in zf.namelist():
                content[name] = zf.read(name)
        return content

    def _validate_manifest(self, manifest: dict):
        """Valida versiones y compatibilidad. Raises ValueError si incompatible."""
        sv = manifest.get("schema_version", "")
        av = manifest.get("app_version", "")
        # Schema version: si major difiere, bloqueamos
        if sv and sv.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(
                f"Schema incompatible: paquete={sv}, app={SCHEMA_VERSION}. "
                "No es posible importar sin migración manual."
            )

    def preview(self, data: dict) -> dict:
        """
        Calcula preview: para cada componente, cuántos ítems hay en el paquete
        y cuántos ya existen en la BD (por clave natural).
        """
        preview = {}
        for comp, payload in data.items():
            items = payload.get("items", []) if isinstance(payload, dict) else []
            existing = self._count_existing(comp, items)
            preview[comp] = {
                "en_paquete":  len(items),
                "ya_existen":  existing,
                "nuevos":      len(items) - existing,
            }
        return preview

    def _count_existing(self, comp: str, items: list) -> int:
        if comp == "proveedores":
            existing_cifs = {
                (r.get("cif_nif") or "").strip().upper()
                for r in (self.db.obtener_todos_proveedores() or [])
                if r.get("cif_nif")
            }
            return sum(1 for i in items if (i.get("cif_nif") or "").strip().upper() in existing_cifs)
        return 0

    def dry_run(self, data: dict, strategies: Dict[str, str]) -> dict:
        """
        Simula la importación.
        strategies: {comp: 'merge'|'overwrite'|'skip'}
        Devuelve {comp: {crear, actualizar, saltar, error}} SIN tocar la BD.
        """
        result = {}
        for comp, payload in data.items():
            strategy = strategies.get(comp, "merge")
            if strategy == "skip":
                items = payload.get("items", []) if isinstance(payload, dict) else []
                result[comp] = {"crear": 0, "actualizar": 0, "saltar": len(items), "error": 0}
                continue
            fn = getattr(self, f"_dryrun_{comp}", None)
            if fn:
                result[comp] = fn(payload, strategy)
            else:
                items = payload.get("items", []) if isinstance(payload, dict) else []
                result[comp] = {"crear": len(items), "actualizar": 0, "saltar": 0, "error": 0}
        return result

    def _dryrun_proveedores(self, payload: dict, strategy: str) -> dict:
        items = payload.get("items", [])
        existing_cifs = {
            (r.get("cif_nif") or "").strip().upper()
            for r in (self.db.obtener_todos_proveedores() or [])
            if r.get("cif_nif")
        }
        existing_names = {
            _norm(r.get("nombre", ""))
            for r in (self.db.obtener_todos_proveedores() or [])
        }
        crear = actualizar = saltar = 0
        for item in items:
            cif  = (item.get("cif_nif") or "").strip().upper()
            name = _norm(item.get("nombre", ""))
            if cif in existing_cifs or name in existing_names:
                if strategy == "overwrite": actualizar += 1
                else: actualizar += 1  # merge también actualiza
            else:
                crear += 1
        return {"crear": crear, "actualizar": actualizar, "saltar": saltar, "error": 0}

    def execute(self, data: dict, strategies: Dict[str, str],
                import_credentials: bool = False) -> Tuple[dict, List[str]]:
        """
        Ejecuta la importación en transacción atómica.
        Retorna (resultado_por_comp, log_lines).
        Rollback si cualquier componente crítico falla.
        """
        log_lines: List[str] = []
        result:    Dict[str, dict] = {}
        conn = self.db.conn

        try:
            conn.execute("BEGIN")
            for comp, payload in data.items():
                strategy = strategies.get(comp, "merge")
                if strategy == "skip":
                    log_lines.append(f"[{comp}] Omitido por estrategia.")
                    items = payload.get("items", []) if isinstance(payload, dict) else []
                    result[comp] = {"crear": 0, "actualizar": 0, "saltar": len(items), "error": 0}
                    continue
                fn = getattr(self, f"_import_{comp}", None)
                if fn:
                    try:
                        res, logs = fn(payload, strategy, import_credentials)
                        result[comp] = res
                        log_lines.extend(logs)
                    except Exception as exc:
                        log_lines.append(f"[{comp}] ERROR: {exc}")
                        result[comp] = {"crear": 0, "actualizar": 0, "saltar": 0, "error": 1}
                else:
                    log_lines.append(f"[{comp}] Sin importador disponible.")
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            log_lines.append(f"ROLLBACK: {exc}")
            raise

        return result, log_lines

    # ── Importadores por componente ───────────────────────────────────────────

    def _import_proveedores(self, payload: dict, strategy: str,
                            creds: bool) -> Tuple[dict, List[str]]:
        items = payload.get("items", [])
        logs = []; crear = actualizar = saltar = 0
        existing = {_norm(r.get("nombre", "")): r
                    for r in (self.db.obtener_todos_proveedores() or [])}
        existing_cif = {(r.get("cif_nif") or "").strip().upper(): r
                        for r in (self.db.obtener_todos_proveedores() or [])
                        if r.get("cif_nif")}

        for item in items:
            cif  = (item.get("cif_nif") or "").strip().upper()
            name = _norm(item.get("nombre", ""))
            match = existing_cif.get(cif) or existing.get(name)
            if match:
                if strategy == "skip":
                    saltar += 1
                    continue
                # merge/overwrite: actualizar campos
                try:
                    updates = {k: v for k, v in item.items()
                               if k not in ("id",) and v is not None}
                    self.db.actualizar_proveedor(match["id"], **updates)
                    actualizar += 1
                    logs.append(f"  [prov] Actualizado: {item.get('nombre')}")
                except Exception as exc:
                    logs.append(f"  [prov] Error actualizar {item.get('nombre')}: {exc}")
            else:
                try:
                    item_clean = {k: v for k, v in item.items() if k != "id"}
                    self.db.cursor.execute("""
                        INSERT OR IGNORE INTO proveedores
                        (nombre, numero_proveedor, cuenta_gasto, categoria,
                         razon_social, cif_nif, cuenta_proveedor, subcuenta_proveedor)
                        VALUES (?,?,?,?,?,?,?,?)""", (
                        item_clean.get("nombre",""),
                        item_clean.get("numero_proveedor",""),
                        item_clean.get("cuenta_gasto",""),
                        item_clean.get("categoria",""),
                        item_clean.get("razon_social",""),
                        item_clean.get("cif_nif",""),
                        item_clean.get("cuenta_proveedor","400000"),
                        item_clean.get("subcuenta_proveedor",""),
                    ))
                    crear += 1
                    logs.append(f"  [prov] Creado: {item.get('nombre')}")
                except Exception as exc:
                    logs.append(f"  [prov] Error crear {item.get('nombre')}: {exc}")

        return {"crear": crear, "actualizar": actualizar, "saltar": saltar, "error": 0}, logs

    def _import_reglas(self, payload: dict, strategy: str,
                       creds: bool) -> Tuple[dict, List[str]]:
        items = payload.get("items", [])
        logs = []; crear = actualizar = 0
        for item in items:
            try:
                # Reglas se identifican por (proveedor_id, trigger)
                pid     = item.get("proveedor_id") or item.get("vendor_id")
                trigger = item.get("trigger", "")
                existing = None
                if pid:
                    existing = self.db._get_one(
                        "SELECT id FROM reglas_proveedor WHERE proveedor_id=? AND trigger=?",
                        (pid, trigger))
                if existing and strategy != "skip":
                    self.db.actualizar_regla_proveedor(existing["id"], {
                        "cuenta_gasto": item.get("account") or item.get("cuenta_gasto",""),
                        "categoria":    item.get("category") or item.get("categoria",""),
                        "serie":        item.get("serie",""),
                        "prioridad":    item.get("priority") or item.get("prioridad",50),
                    })
                    actualizar += 1
                elif not existing:
                    self.db.cursor.execute("""
                        INSERT OR IGNORE INTO reglas_proveedor
                        (proveedor_id, trigger, cuenta_gasto, categoria, serie, prioridad, activa)
                        VALUES (?,?,?,?,?,?,1)""", (
                        pid, trigger,
                        item.get("account") or item.get("cuenta_gasto",""),
                        item.get("category") or item.get("categoria",""),
                        item.get("serie",""),
                        item.get("priority") or item.get("prioridad",50),
                    ))
                    crear += 1
            except Exception as exc:
                logs.append(f"  [regla] Error: {exc}")
        return {"crear": crear, "actualizar": actualizar, "saltar": 0, "error": 0}, logs

    def _import_correo(self, payload: dict, strategy: str,
                       creds: bool) -> Tuple[dict, List[str]]:
        items = payload.get("items", [])
        logs = []; crear = 0
        for item in items:
            if not creds:
                item = dict(item)
                item["password"] = ""  # clear redacted/empty passwords
            try:
                self.db.cursor.execute("""
                    INSERT OR IGNORE INTO cuentas_gmail
                    (email, password, host, port, use_ssl, folder, activa)
                    VALUES (?,?,?,?,?,?,?)""", (
                    item.get("email",""), item.get("password",""),
                    item.get("host","imap.gmail.com"), item.get("port",993),
                    item.get("use_ssl",1), item.get("folder","INBOX"),
                    item.get("activa",1),
                ))
                crear += 1
                if not creds:
                    logs.append(f"  [correo] {item.get('email')} importada (contraseña vacía — introducir manualmente)")
            except Exception as exc:
                logs.append(f"  [correo] Error: {exc}")
        return {"crear": crear, "actualizar": 0, "saltar": 0, "error": 0}, logs

    def _import_ia(self, payload: dict, strategy: str,
                   creds: bool) -> Tuple[dict, List[str]]:
        logs = []
        if not creds:
            logs.append("  [ia] Credenciales no importadas (opción desmarcada).")
            return {"crear": 0, "actualizar": 0, "saltar": 1, "error": 0}, logs
        for motor in ("gemini", "ollama", "copilot"):
            cfg = payload.get(motor)
            if cfg:
                try:
                    self.db.set_ia_config(motor, cfg)
                    logs.append(f"  [ia] Config {motor} importada.")
                except Exception as exc:
                    logs.append(f"  [ia] Error {motor}: {exc}")
        default = payload.get("motor_default","")
        if default:
            self.db.set_config_ui("visor_ia_motor", default)
        return {"crear": 1, "actualizar": 0, "saltar": 0, "error": 0}, logs

    def _import_visual(self, payload: dict, strategy: str,
                       creds: bool) -> Tuple[dict, List[str]]:
        logs = []
        for k, v in payload.items():
            try: self.db.set_config_ui(k, str(v))
            except Exception: pass
        logs.append(f"  [visual] {len(payload)} ajustes visuales importados.")
        return {"crear": len(payload), "actualizar": 0, "saltar": 0, "error": 0}, logs

    def _import_carpetas(self, payload: dict, strategy: str,
                         creds: bool) -> Tuple[dict, List[str]]:
        logs = []
        for k, v in payload.items():
            try: self.db.set_config_ui(k, str(v))
            except Exception: pass
        logs.append(f"  [carpetas] {len(payload)} rutas importadas.")
        return {"crear": len(payload), "actualizar": 0, "saltar": 0, "error": 0}, logs

    def _import_alertas(self, payload: dict, strategy: str,
                        creds: bool) -> Tuple[dict, List[str]]:
        items = payload.get("items", [])
        logs = [f"  [alertas] {len(items)} alertas (importación básica)."]
        crear = 0
        for item in items:
            try:
                self.db.cursor.execute(
                    "INSERT OR IGNORE INTO alertas_config (tipo, mensaje, activa) VALUES (?,?,?)",
                    (item.get("tipo",""), item.get("mensaje",""), item.get("activa",1)))
                crear += 1
            except Exception as exc:
                logs.append(f"    Error: {exc}")
        return {"crear": crear, "actualizar": 0, "saltar": 0, "error": 0}, logs
