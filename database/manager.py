# -*- coding: utf-8 -*-
"""
DatabaseManager — Capa de acceso a SQLite.
"""
from __future__ import annotations
import sqlite3
import hashlib
import hmac
import os
import threading
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from core.logging_config import get_logger

log = get_logger("database")


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, db_path: Optional[str] = None) -> "DatabaseManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._db_path = db_path
                    cls._instance = instance
        return cls._instance

    def __init__(self, db_path: Optional[str] = None) -> None:
        if DatabaseManager._initialized:
            return
        with DatabaseManager._lock:
            if DatabaseManager._initialized:
                return
            if db_path is None:
                try:
                    from core.config_loader import get_config
                    db_path = str(get_config().db_path)
                except Exception:
                    db_path = "./facturas.db"

            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db_path = db_path
            self.conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row

            # Detectar si la DB está en unidad de red (UNC o letra de unidad de red)
            # En red: WAL no es compatible → usar modo DELETE para evitar bloqueos
            _on_network = self._is_network_path(db_path)
            if _on_network:
                log.warning("DB en unidad de red detectada (%s). Usando journal_mode=DELETE.", db_path)
                try:
                    self.conn.execute("PRAGMA journal_mode=DELETE")
                except Exception as e:
                    log.error("Error configurando journal_mode=DELETE: %s", e)
            else:
                try:
                    self.conn.execute("PRAGMA journal_mode=WAL")
                except Exception as e:
                    log.warning("WAL no disponible, usando modo por defecto: %s", e)

            self.conn.execute("PRAGMA busy_timeout=30000")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.cursor = self.conn.cursor()
            self._migrate()
            DatabaseManager._initialized = True
            log.info("Base de datos inicializada: %s (red=%s)", db_path, _on_network)

    # ── Métodos auxiliares ───────────────────────────────────────────────────

    def _get_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        self.cursor.execute(sql, params)
        return self.cursor.fetchone()

    def _get_all(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    @staticmethod
    def _hash_pbkdf2(password: str, salt: str = None):
        if salt is None:
            salt = os.urandom(32).hex()
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                   bytes.fromhex(salt), 260000)
        return key.hex(), salt

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def _is_network_path(path: str) -> bool:
        """
        Detecta si la ruta apunta a una unidad de red (UNC o letra de unidad mapeada).
        En Windows, comprueba si la letra de unidad es de red.
        En Linux/Mac, comprueba rutas UNC (\\...) o montajes en /mnt/... con heurística simple.
        """
        import platform
        try:
            p = str(path).replace("/", "\\")
            # Rutas UNC: \\servidor\recurso
            if p.startswith("\\\\"):
                return True
            if platform.system() == "Windows":
                import ctypes
                drive = os.path.splitdrive(p)[0]
                if drive:
                    DRIVE_REMOTE = 4
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
                    return drive_type == DRIVE_REMOTE
        except Exception:
            pass
        return False

    def _insert_user_pbkdf2(self, usuario: str, password: str, nombre: str, rol: str) -> None:
        ph, salt = self._hash_pbkdf2(password)
        self.cursor.execute(
            "INSERT OR IGNORE INTO usuarios (usuario,password_hash,salt,nombre_completo,rol) VALUES (?,?,?,?,?)",
            (usuario, ph, salt, nombre, rol))

    # ── Migraciones ───────────────────────────────────────────────────────────

    def _migrate(self) -> None:
        """Ejecuta todas las migraciones necesarias."""
        self._create_proveedores()
        self._create_empresa()
        self._create_reglas()
        self._create_plantillas_ocr()
        self._create_cuentas_gmail()
        self._create_historial()
        self._create_tipos_factura()
        self._create_series_factura()
        self._create_usuarios()
        self._create_config_ui()
        self._create_filtros()
        self._create_categorias()
        self._create_facturas_procesadas_v10()
        self._create_email_mensajes_v10()
        self._create_patrones_proveedor()
        self._migrate_historial_v10()
        self._migrate_usuarios_v14()
        self._create_alertas_v14()
        self._create_auditoria_v14()
        self._migrate_cont_automatica_fecha()
        self._migrate_retencion_reparto()  # V15: retención + reparto cuentas
        self.conn.commit()

    def _create_proveedores(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS proveedores (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre            TEXT UNIQUE NOT NULL,
                numero_proveedor  TEXT NOT NULL,
                cuenta_gasto      TEXT NOT NULL,
                categoria         TEXT NOT NULL,
                razon_social      TEXT,
                cif_nif           TEXT,
                direccion         TEXT,
                email             TEXT,
                iban              TEXT,
                cuenta_variable   INTEGER DEFAULT NULL,
                fecha_creacion    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cuenta_proveedor  TEXT DEFAULT '400000',
                subcuenta_proveedor TEXT,
                subcuenta_gasto   TEXT,
                serie             TEXT DEFAULT '',
                tipo_factura      TEXT DEFAULT ''
            )""")

    def _create_empresa(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS empresa_cliente (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                razon_social  TEXT,
                cif           TEXT,
                direccion     TEXT,
                codigo_postal TEXT,
                email         TEXT
            )""")

    def _create_reglas(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reglas_proveedor (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor_id            INTEGER,
                serie                   TEXT NOT NULL DEFAULT '',
                cuenta_gasto            TEXT NOT NULL DEFAULT '',
                categoria               TEXT NOT NULL DEFAULT '',
                prioridad               INTEGER DEFAULT 1,
                rule_type               TEXT DEFAULT 'determinista',
                activa                  INTEGER DEFAULT 1,
                nombre_regla            TEXT DEFAULT '',
                match_cif               TEXT DEFAULT '',
                match_tipo_factura      TEXT DEFAULT '',
                match_serie             TEXT DEFAULT '',
                match_categoria         TEXT DEFAULT '',
                set_cuenta_proveedor    TEXT DEFAULT '',
                set_subcuenta_proveedor TEXT DEFAULT '',
                set_cuenta_gasto        TEXT DEFAULT '',
                set_subcuenta_gasto     TEXT DEFAULT '',
                set_serie               TEXT DEFAULT '',
                set_categoria           TEXT DEFAULT '',
                set_tipo_factura        TEXT DEFAULT '',
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )""")
        # Migración: añadir rule_type y activa si la tabla ya existe sin esas columnas
        for col_def in [
            ("rule_type", "TEXT DEFAULT 'keyword'"),
            ("activa",    "INTEGER DEFAULT 1"),
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE reglas_proveedor ADD COLUMN {col_def[0]} {col_def[1]}")
            except sqlite3.OperationalError:
                pass
        # Tabla de memoria IA por factura/regla
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS ia_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_pdf    TEXT,
                prov_id     INTEGER,
                tipo        TEXT DEFAULT '',
                memo_json   TEXT NOT NULL,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(hash_pdf, prov_id, tipo)
            )""")

    def _create_plantillas_ocr(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS plantillas_ocr (
                proveedor_id   INTEGER,
                plantilla_json TEXT,
                dpi            INTEGER,
                campo          TEXT NOT NULL,
                pagina         INTEGER DEFAULT 0,
                PRIMARY KEY (proveedor_id, campo),
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE CASCADE
            )""")

    def _create_cuentas_gmail(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS cuentas_gmail (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT UNIQUE NOT NULL,
                password     TEXT NOT NULL,
                host         TEXT DEFAULT 'imap.gmail.com',
                port         INTEGER DEFAULT 993,
                use_ssl      INTEGER DEFAULT 1,
                folder       TEXT DEFAULT 'INBOX',
                activa       INTEGER DEFAULT 1,
                es_principal INTEGER DEFAULT 0,
                seleccionada INTEGER DEFAULT 0
            )""")
        # Migración: añadir columnas host/port/folder si existen DBs antiguas
        for col, definition in [
            ("host",   "TEXT DEFAULT 'imap.gmail.com'"),
            ("port",   "INTEGER DEFAULT 993"),
            ("use_ssl","INTEGER DEFAULT 1"),
            ("folder", "TEXT DEFAULT 'INBOX'"),
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE cuentas_gmail ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass

    def _create_historial(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_procesado (
                hash_pdf         TEXT PRIMARY KEY,
                nombre_archivo   TEXT,
                fecha_procesado  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                nombre_proveedor TEXT,
                numero_proveedor TEXT,
                cuenta_gasto     TEXT,
                serie_factura    TEXT,
                tipo_factura     TEXT,
                numero_factura   TEXT,
                proveedor_id     INTEGER,
                ruta_archivo_final TEXT,
                impresa          INTEGER DEFAULT 0,
                impresa_en       TIMESTAMP,
                id_regla_aplicada INTEGER,
                es_rectificativa INTEGER DEFAULT 0,
                numero_factura_manual TEXT
            )""")

    def _create_tipos_factura(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tipos_factura (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre       TEXT UNIQUE NOT NULL,
                abreviatura  TEXT UNIQUE NOT NULL,
                orden        INTEGER DEFAULT 0
            )""")
        # Tipos por defecto
        defaults = [
            ("Factura",          "FACT"),
            ("Factura Rectif.",  "RECT"),
            ("Albarán",          "ALB"),
            ("Nota de Cargo",    "NC"),
            ("Nota de Abono",    "NA"),
            ("Presupuesto",      "PRES"),
        ]
        for nombre, abrev in defaults:
            self.cursor.execute(
                "INSERT OR IGNORE INTO tipos_factura (nombre, abreviatura) VALUES (?,?)",
                (nombre, abrev))

    def _create_series_factura(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS series_factura (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre      TEXT UNIQUE NOT NULL,
                descripcion TEXT DEFAULT ''
            )""")

    def _create_usuarios(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario           TEXT UNIQUE NOT NULL,
                password_hash     TEXT NOT NULL,
                salt              TEXT NOT NULL DEFAULT '',
                nombre_completo   TEXT NOT NULL,
                email             TEXT DEFAULT '',
                rol               TEXT DEFAULT 'usuario_basico',
                activo            INTEGER DEFAULT 1,
                fecha_creacion    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultima_sesion     TIMESTAMP,
                intentos_fallidos INTEGER DEFAULT 0,
                bloqueado_hasta   TIMESTAMP
            )""")
        if not self._get_one("SELECT id FROM usuarios WHERE usuario='JESUS'"):
            self._insert_user_pbkdf2("JESUS", "admin1977", "Administrador del Sistema", "super_admin")

    def _migrate_usuarios_v14(self) -> None:
        cols = {r[1] for r in self._get_all("PRAGMA table_info(usuarios)")}
        migrations = [
            ("salt",              "ALTER TABLE usuarios ADD COLUMN salt TEXT NOT NULL DEFAULT ''"),
            ("email",             "ALTER TABLE usuarios ADD COLUMN email TEXT DEFAULT ''"),
            ("ultima_sesion",     "ALTER TABLE usuarios ADD COLUMN ultima_sesion TIMESTAMP"),
            ("intentos_fallidos", "ALTER TABLE usuarios ADD COLUMN intentos_fallidos INTEGER DEFAULT 0"),
            ("bloqueado_hasta",   "ALTER TABLE usuarios ADD COLUMN bloqueado_hasta TIMESTAMP"),
        ]
        for col, sql in migrations:
            if col not in cols:
                try:
                    self.cursor.execute(sql)
                except Exception:
                    pass
        self.cursor.execute(
            "UPDATE usuarios SET rol='super_admin' WHERE usuario='JESUS' AND rol='admin'")

    def _create_config_ui(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_ui (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )""")

    def _create_filtros(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS filtros_descarga (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                palabra TEXT UNIQUE NOT NULL
            )""")
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS estado_filtros (
                id     INTEGER PRIMARY KEY,
                activo INTEGER
            )""")
        self.cursor.execute(
            "INSERT OR IGNORE INTO estado_filtros (id, activo) VALUES (1, 0)")

    # ── TABLA DE CATEGORÍAS ───────────────────────────────────────────
    def _create_categorias(self) -> None:
        """Crea la tabla de categorías personalizables."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT DEFAULT '',
                orden INTEGER DEFAULT 0,
                activa INTEGER DEFAULT 1,
                color TEXT DEFAULT '#718096',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insertar categorías por defecto si la tabla está vacía
        self.cursor.execute("SELECT COUNT(*) FROM categorias")
        if self.cursor.fetchone()[0] == 0:
            categorias_default = [
                ("COMERCIAL Y POSTVENTA EXTERNAS", "Facturas de comerciales y postventa", 1, "#4299E1"),
                ("COMUNES EXTERNOS", "Gastos comunes con externos", 2, "#48BB78"),
                ("GESTORÍA", "Gastos de gestoría", 3, "#ED8936"),
                ("SEAT", "Facturas de SEAT", 4, "#9F7AEA"),
                ("COMBUSTIBLE", "Gastos de combustible", 5, "#F56565"),
                ("COMUNICACIONES", "Teléfono, internet, etc.", 6, "#38B2AC"),
                ("MANTENIMIENTO", "Mantenimiento y reparaciones", 7, "#ECC94B"),
                ("SEGUROS", "Seguros", 8, "#667EEA"),
                ("SUMINISTROS", "Luz, agua, etc.", 9, "#FC8181"),
                ("VARIOS", "Otros gastos", 10, "#A0AEC0"),
            ]
            for nombre, desc, orden, color in categorias_default:
                self.cursor.execute(
                    "INSERT INTO categorias (nombre, descripcion, orden, color) VALUES (?,?,?,?)",
                    (nombre, desc, orden, color)
                )
            log.info("Categorías por defecto insertadas")

    def obtener_categorias(self, solo_activas: bool = True) -> List[Dict]:
        """Obtiene todas las categorías."""
        sql = "SELECT * FROM categorias"
        if solo_activas:
            sql += " WHERE activa = 1"
        sql += " ORDER BY orden, nombre"
        return [dict(r) for r in self._get_all(sql)]

    def obtener_categoria(self, categoria_id: int) -> Optional[Dict]:
        """Obtiene una categoría por ID."""
        row = self._get_one("SELECT * FROM categorias WHERE id=?", (categoria_id,))
        return dict(row) if row else None

    def guardar_categoria(self, datos: dict) -> int:
        """Guarda o actualiza una categoría."""
        if datos.get("id"):
            self.cursor.execute(
                """UPDATE categorias 
                   SET nombre=?, descripcion=?, orden=?, activa=?, color=?
                   WHERE id=?""",
                (datos["nombre"], datos.get("descripcion", ""),
                 datos.get("orden", 0), datos.get("activa", 1),
                 datos.get("color", "#718096"), datos["id"])
            )
            self.conn.commit()
            return datos["id"]
        else:
            self.cursor.execute(
                """INSERT INTO categorias (nombre, descripcion, orden, activa, color)
                   VALUES (?,?,?,?,?)""",
                (datos["nombre"], datos.get("descripcion", ""),
                 datos.get("orden", 0), datos.get("activa", 1),
                 datos.get("color", "#718096"))
            )
            self.conn.commit()
            return self.cursor.lastrowid

    def eliminar_categoria(self, categoria_id: int) -> bool:
        """Elimina una categoría (solo si no está en uso)."""
        nombre_cat = self._get_one("SELECT nombre FROM categorias WHERE id=?", (categoria_id,))
        if not nombre_cat:
            return False
        facturas = self._get_one(
            "SELECT COUNT(*) FROM facturas_procesadas_v10 WHERE categoria=?",
            (nombre_cat[0],)
        )
        if facturas and facturas[0] > 0:
            return False
        self.cursor.execute("DELETE FROM categorias WHERE id=?", (categoria_id,))
        self.conn.commit()
        return True

    # ── TABLA DE PATRONES ────────────────────────────────────
    def _create_patrones_proveedor(self) -> None:
        """Crea la tabla de patrones para reconocimiento silencioso."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS patrones_proveedor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor_id INTEGER NOT NULL,
                patron TEXT NOT NULL,
                tipo TEXT DEFAULT 'texto',
                confianza REAL DEFAULT 0.7,
                veces_usado INTEGER DEFAULT 0,
                ultimo_uso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE CASCADE
            )
        """)
        # Crear índice para búsquedas rápidas
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_patrones_proveedor 
            ON patrones_proveedor(proveedor_id, confianza)
        """)
        self.conn.commit()

    def guardar_patron_proveedor(self, proveedor_id: int, patron: str, 
                                   tipo: str = "texto", confianza: float = 0.7) -> int:
        """Guarda un patrón de texto asociado a un proveedor."""
        self.cursor.execute("""
            INSERT INTO patrones_proveedor (proveedor_id, patron, tipo, confianza, veces_usado, ultimo_uso)
            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        """, (proveedor_id, patron, tipo, confianza))
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_patrones_proveedor(self, proveedor_id: Optional[int] = None) -> List[Dict]:
        """Obtiene todos los patrones, opcionalmente filtrados por proveedor."""
        if proveedor_id:
            rows = self._get_all(
                "SELECT * FROM patrones_proveedor WHERE proveedor_id = ? ORDER BY confianza DESC",
                (proveedor_id,)
            )
        else:
            rows = self._get_all(
                "SELECT * FROM patrones_proveedor ORDER BY confianza DESC"
            )
        return [dict(r) for r in rows]

    def incrementar_uso_patron(self, patron_id: int) -> None:
        """Incrementa el contador de uso de un patrón y actualiza su confianza."""
        self.cursor.execute("""
            UPDATE patrones_proveedor 
            SET veces_usado = veces_usado + 1, 
                ultimo_uso = CURRENT_TIMESTAMP,
                confianza = MIN(1.0, confianza + 0.05)
            WHERE id = ?
        """, (patron_id,))
        self.conn.commit()

    def buscar_proveedor_por_patron(self, texto: str) -> Optional[int]:
        """
        Busca un proveedor cuyo patrón aparezca en el texto.
        Devuelve el ID del proveedor con mayor confianza que coincida.
        """
        texto_low = texto.lower()
        mejor_prov = None
        mejor_conf = 0.0
        
        for p in self.obtener_patrones_proveedor():
            if p["tipo"] == "texto" and p["patron"].lower() in texto_low:
                if p["confianza"] > mejor_conf:
                    mejor_conf = p["confianza"]
                    mejor_prov = p["proveedor_id"]
            elif p["tipo"] == "regex":
                import re
                try:
                    if re.search(p["patron"], texto, re.IGNORECASE):
                        if p["confianza"] > mejor_conf:
                            mejor_conf = p["confianza"]
                            mejor_prov = p["proveedor_id"]
                except re.error:
                    continue
        
        if mejor_prov:
            # Incrementar uso del patrón encontrado
            self.cursor.execute(
                "UPDATE patrones_proveedor SET veces_usado = veces_usado + 1 WHERE proveedor_id = ?",
                (mejor_prov,)
            )
            self.conn.commit()
            return mejor_prov
        return None

    # ── V10: Facturas procesadas con datos financieros ────────────────────────

    def _create_facturas_procesadas_v10(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS facturas_procesadas_v10 (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                id_proveedor            INTEGER,
                fecha                   TEXT,
                ruta_pdf                TEXT,
                base_imponible          REAL DEFAULT 0,
                iva                     REAL DEFAULT 0,
                total                   REAL DEFAULT 0,
                tipo_factura            TEXT,
                cuenta_gasto            TEXT,
                categoria               TEXT,
                numero_factura          TEXT,
                procesada_desde_correo  INTEGER DEFAULT 0,
                numero_proveedor        TEXT,
                origen_correo           TEXT,
                id_mensaje_unico        TEXT,
                hash_pdf                TEXT UNIQUE,
                fecha_procesado         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                nombre_proveedor        TEXT,
                cif_proveedor           TEXT,
                ruta_archivo_final      TEXT,
                serie_factura           TEXT DEFAULT '',
                cuenta_proveedor         TEXT DEFAULT '400000',
                subcuenta_proveedor      TEXT DEFAULT '',
                subcuenta_gasto          TEXT DEFAULT '',
                id_regla_aplicada        INTEGER,
                es_rectificativa         INTEGER DEFAULT 0,
                numero_factura_manual    TEXT,
                nombre_regla             TEXT DEFAULT '',
                razon_social_prov        TEXT DEFAULT '',
                impresa                   INTEGER DEFAULT 0,
                impresa_en                TIMESTAMP,
                FOREIGN KEY (id_proveedor) REFERENCES proveedores(id)
            )""")

    def _create_email_mensajes_v10(self) -> None:
        """Registro de mensajes de correo descargados para evitar duplicados."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_mensajes_v10 (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      TEXT UNIQUE NOT NULL,
                cuenta_email    TEXT,
                asunto          TEXT,
                remitente       TEXT,
                fecha_correo    TEXT,
                fecha_descarga  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                num_adjuntos    INTEGER DEFAULT 0,
                procesado       INTEGER DEFAULT 0
            )""")

    def _migrate_historial_v10(self) -> None:
        """Añade columnas nuevas a tablas existentes (migraciones acumulativas)."""
        def _add_col(table, col, defn):
            cols = {r[1] for r in self._get_all(f"PRAGMA table_info({table})")}
            if col not in cols:
                try: self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                except Exception: pass

        # historial_procesado
        _add_col("historial_procesado",  "ruta_archivo_final",    "TEXT")
        _add_col("historial_procesado",  "impresa",               "INTEGER DEFAULT 0")
        _add_col("historial_procesado",  "impresa_en",            "TIMESTAMP")
        _add_col("historial_procesado",  "id_regla_aplicada",     "INTEGER")
        _add_col("historial_procesado",  "es_rectificativa",      "INTEGER DEFAULT 0")
        _add_col("historial_procesado",  "numero_factura_manual", "TEXT")

        # facturas_procesadas_v10
        _add_col("facturas_procesadas_v10", "ruta_archivo_final",    "TEXT")
        _add_col("facturas_procesadas_v10", "serie_factura",         "TEXT DEFAULT ''")
        _add_col("facturas_procesadas_v10", "cuenta_proveedor",      "TEXT DEFAULT '400000'")
        _add_col("facturas_procesadas_v10", "subcuenta_proveedor",   "TEXT DEFAULT ''")
        _add_col("facturas_procesadas_v10", "subcuenta_gasto",       "TEXT DEFAULT ''")
        _add_col("facturas_procesadas_v10", "impresa",               "INTEGER DEFAULT 0")
        _add_col("facturas_procesadas_v10", "impresa_en",            "TIMESTAMP")
        _add_col("facturas_procesadas_v10", "id_regla_aplicada",     "INTEGER")
        _add_col("facturas_procesadas_v10", "es_rectificativa",      "INTEGER DEFAULT 0")
        _add_col("facturas_procesadas_v10", "numero_factura_manual", "TEXT")
        _add_col("facturas_procesadas_v10", "nombre_regla",          "TEXT DEFAULT ''")
        _add_col("facturas_procesadas_v10", "razon_social_prov",     "TEXT DEFAULT ''")

        # proveedores — nuevos campos obligatorios V2
        _add_col("proveedores", "cuenta_proveedor",    "TEXT DEFAULT '400000'")
        _add_col("proveedores", "subcuenta_proveedor", "TEXT DEFAULT ''")
        _add_col("proveedores", "subcuenta_gasto",     "TEXT DEFAULT ''")
        _add_col("proveedores", "serie",               "TEXT DEFAULT ''")
        _add_col("proveedores", "tipo_factura",        "TEXT DEFAULT ''")

        # reglas_proveedor — nuevos campos deterministas
        _add_col("reglas_proveedor", "subcuenta_gasto",        "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "activa",                 "INTEGER DEFAULT 1")
        _add_col("reglas_proveedor", "rule_type",              "TEXT DEFAULT 'determinista'")
        _add_col("reglas_proveedor", "nombre_regla",           "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "match_cif",              "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "match_tipo_factura",     "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "match_serie",            "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "match_categoria",        "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_cuenta_proveedor",   "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_subcuenta_proveedor","TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_cuenta_gasto",       "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_subcuenta_gasto",    "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_serie",              "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_categoria",          "TEXT DEFAULT ''")
        _add_col("reglas_proveedor", "set_tipo_factura",       "TEXT DEFAULT ''")

        self.conn.commit()

    # ── Alertas V14 ──────────────────────────────────────────────────────────

    def _create_alertas_v14(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS alertas_config (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre    TEXT NOT NULL,
                tipo      TEXT NOT NULL,
                condicion TEXT NOT NULL,
                valor     REAL NOT NULL,
                periodo   TEXT DEFAULT 'mensual',
                activa    INTEGER DEFAULT 1,
                emails    TEXT DEFAULT '',
                creada    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS alertas_disparadas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                alerta_id       INTEGER REFERENCES alertas_config(id),
                fecha           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                detalle         TEXT,
                factura_ref     TEXT,
                email_enviado_a TEXT,
                leida           INTEGER DEFAULT 0
            )""")
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS smtp_config (
                id         INTEGER PRIMARY KEY CHECK (id=1),
                host       TEXT DEFAULT '',
                port       INTEGER DEFAULT 587,
                ssl        INTEGER DEFAULT 1,
                usuario    TEXT DEFAULT '',
                password   TEXT DEFAULT '',
                from_email TEXT DEFAULT ''
            )""")
        self.cursor.execute("INSERT OR IGNORE INTO smtp_config (id) VALUES (1)")

    def obtener_alertas_config(self) -> List[Dict]:
        """Obtiene todas las alertas configuradas."""
        return [dict(r) for r in self._get_all("SELECT * FROM alertas_config ORDER BY id")]

    def guardar_alerta_config(self, datos: dict) -> int:
        """Guarda o actualiza una alerta."""
        if datos.get("id"):
            self.cursor.execute(
                """UPDATE alertas_config SET nombre=?,tipo=?,condicion=?,valor=?,
                   periodo=?,activa=?,emails=? WHERE id=?""",
                (datos["nombre"], datos["tipo"], datos["condicion"], datos["valor"],
                 datos.get("periodo","mensual"), int(datos.get("activa",1)),
                 datos.get("emails",""), datos["id"]))
            self.conn.commit()
            return datos["id"]
        else:
            self.cursor.execute(
                """INSERT INTO alertas_config (nombre,tipo,condicion,valor,periodo,activa,emails)
                   VALUES (?,?,?,?,?,?,?)""",
                (datos["nombre"], datos["tipo"], datos["condicion"], datos["valor"],
                 datos.get("periodo","mensual"), int(datos.get("activa",1)),
                 datos.get("emails","")))
            self.conn.commit()
            return self.cursor.lastrowid

    def eliminar_alerta_config(self, aid: int) -> None:
        """Elimina una alerta."""
        self.cursor.execute("DELETE FROM alertas_config WHERE id=?", (aid,))
        self.conn.commit()

    def registrar_alerta_disparada(self, alerta_id: int, detalle: str,
                                    factura_ref: str = "", email_a: str = "") -> None:
        """Registra una alerta que se ha disparado."""
        self.cursor.execute(
            """INSERT INTO alertas_disparadas (alerta_id,detalle,factura_ref,email_enviado_a)
               VALUES (?,?,?,?)""", (alerta_id, detalle, factura_ref, email_a))
        self.conn.commit()

    def obtener_historial_alertas(self, limite: int = 200) -> List[Dict]:
        """Obtiene el historial de alertas disparadas."""
        return [dict(r) for r in self._get_all(
            """SELECT ad.*,ac.nombre alerta_nombre,ac.tipo alerta_tipo
               FROM alertas_disparadas ad
               LEFT JOIN alertas_config ac ON ad.alerta_id=ac.id
               ORDER BY ad.fecha DESC LIMIT ?""", (limite,))]

    def get_smtp_config(self) -> Dict:
        """Obtiene la configuración SMTP."""
        row = self._get_one("SELECT * FROM smtp_config WHERE id=1")
        return dict(row) if row else {}

    # ── Helpers de suma mensual (usados por alertas) ──────────────────────────

    def _suma_mes_proveedor(self, nombre_proveedor: str, mes: str) -> float:
        """Suma base_imponible del mes dado para un proveedor (por nombre)."""
        row = self._get_one(
            """SELECT COALESCE(SUM(base_imponible),0) as total
               FROM facturas_v10
               WHERE strftime('%Y-%m', fecha) = ?
                 AND (nombre_proveedor = ? OR razon_social_prov = ?)
                 AND (es_rectificativa IS NULL OR es_rectificativa = 0)""",
            (mes, nombre_proveedor, nombre_proveedor))
        return float(row["total"]) if row else 0.0

    def _suma_mes_categoria(self, categoria: str, mes: str) -> float:
        """Suma base_imponible del mes dado para una categoría."""
        row = self._get_one(
            """SELECT COALESCE(SUM(base_imponible),0) as total
               FROM facturas_v10
               WHERE strftime('%Y-%m', fecha) = ?
                 AND categoria = ?
                 AND (es_rectificativa IS NULL OR es_rectificativa = 0)""",
            (mes, categoria))
        return float(row["total"]) if row else 0.0

    def _suma_mes_total(self, mes: str) -> float:
        """Suma base_imponible total del mes dado."""
        row = self._get_one(
            """SELECT COALESCE(SUM(base_imponible),0) as total
               FROM facturas_v10
               WHERE strftime('%Y-%m', fecha) = ?
                 AND (es_rectificativa IS NULL OR es_rectificativa = 0)""",
            (mes,))
        return float(row["total"]) if row else 0.0

    def _suma_factura_proveedor(self, nombre_proveedor: str, total_factura: float) -> bool:
        """True si el importe de la factura supera umbral (usado en alerta por_factura)."""
        return True  # el umbral se compara externamente

    def verificar_alertas_factura(self, factura: dict) -> list:
        """
        Comprueba todas las alertas activas contra una factura recién procesada.
        Devuelve lista de dicts {alerta, detalle} para las que se disparan.
        """
        from datetime import datetime
        disparadas = []
        try:
            alertas = self.obtener_alertas_config()
            activas = [a for a in alertas if a.get("activa")]
            if not activas:
                return []

            mes = datetime.now().strftime("%Y-%m")
            nombre_prov  = factura.get("nombre_proveedor", "")
            categoria    = factura.get("categoria", "")
            base         = float(factura.get("base_imponible", 0) or 0)
            num_factura  = str(factura.get("numero_factura", ""))

            for a in activas:
                t       = a["tipo"]
                umbral  = float(a["valor"])
                cond    = a.get("condicion", "")
                dispara = False
                detalle = ""

                if t == "factura_proveedor":
                    if cond.lower() in nombre_prov.lower() and base > umbral:
                        dispara = True
                        detalle = (f"Factura {num_factura} de '{nombre_prov}': "
                                   f"{base:.2f}€ > {umbral:.2f}€")

                elif t == "factura_categoria":
                    if cond.lower() in categoria.lower() and base > umbral:
                        dispara = True
                        detalle = (f"Factura {num_factura} cat '{categoria}': "
                                   f"{base:.2f}€ > {umbral:.2f}€")

                elif t == "mensual_proveedor":
                    tot = self._suma_mes_proveedor(cond, mes)
                    if tot > umbral:
                        dispara = True
                        detalle = (f"Proveedor '{cond}' mes {mes}: "
                                   f"{tot:.2f}€ > {umbral:.2f}€")

                elif t == "mensual_categoria":
                    tot = self._suma_mes_categoria(cond, mes)
                    if tot > umbral:
                        dispara = True
                        detalle = (f"Categoría '{cond}' mes {mes}: "
                                   f"{tot:.2f}€ > {umbral:.2f}€")

                elif t == "mensual_total":
                    tot = self._suma_mes_total(mes)
                    if tot > umbral:
                        dispara = True
                        detalle = (f"Gasto total mes {mes}: "
                                   f"{tot:.2f}€ > {umbral:.2f}€")

                if dispara:
                    disparadas.append({"alerta": a, "detalle": detalle})

        except Exception as exc:
            import logging
            logging.getLogger("database").warning("verificar_alertas_factura error: %s", exc)
        return disparadas

    def set_smtp_config(self, host, port, ssl, usuario, password, from_email) -> None:
        """Guarda la configuración SMTP."""
        self.cursor.execute(
            """UPDATE smtp_config SET host=?,port=?,ssl=?,usuario=?,password=?,from_email=?
               WHERE id=1""", (host, port, int(ssl), usuario, password, from_email))
        self.conn.commit()

    # ── Auditoría V14 ─────────────────────────────────────────────────────────

    def _create_auditoria_v14(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                accion     TEXT NOT NULL,
                modulo     TEXT DEFAULT '',
                detalle    TEXT DEFAULT '',
                fecha      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    def _migrate_cont_automatica_fecha(self):
        """Añade columnas nuevas si no existen (migración incremental)."""
        def _add_col(table, col, defn):
            cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")

        _add_col("reglas_proveedor",        "cont_automatica",       "INTEGER DEFAULT 0")
        _add_col("facturas_procesadas_v10", "cont_automatica",       "INTEGER DEFAULT 0")
        _add_col("facturas_procesadas_v10", "fecha_factura",          "TEXT DEFAULT ''")
        _add_col("facturas_procesadas_v10", "fecha_contabilizacion",  "TEXT DEFAULT ''")

    def _migrate_retencion_reparto(self):
        """V15: columnas de retención IRPF y reparto de gasto entre cuentas."""
        def _add_col(table, col, defn):
            cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                log.info("Migración V15: columna añadida %s.%s", table, col)

        # En facturas procesadas: guardar retención e importes por cuenta
        _add_col("facturas_procesadas_v10", "retencion_pct",       "REAL DEFAULT 0")
        _add_col("facturas_procesadas_v10", "retencion_importe",    "REAL DEFAULT 0")
        _add_col("facturas_procesadas_v10", "reparto_cuentas_json", "TEXT DEFAULT ''")
        # V15.1: tipo_iva (0=exento, 4, 10, 21) — 21 por defecto para compat.
        _add_col("facturas_procesadas_v10", "tipo_iva",             "INTEGER DEFAULT 21")

        # En reglas: permitir definir retención y reparto por defecto
        _add_col("reglas_proveedor", "set_retencion_pct",    "REAL DEFAULT 0")
        _add_col("reglas_proveedor", "reparto_cuentas_json", "TEXT DEFAULT ''")
        # V15.1: tipo IVA por defecto para el proveedor (21 = general)
        _add_col("reglas_proveedor", "set_tipo_iva",         "INTEGER DEFAULT 21")


    def registrar_auditoria(self, usuario_id: int, accion: str,
                             modulo: str = "", detalle: str = "") -> None:
        try:
            self.cursor.execute(
                "INSERT INTO auditoria (usuario_id,accion,modulo,detalle) VALUES (?,?,?,?)",
                (usuario_id, accion, modulo, detalle))
            self.conn.commit()
        except Exception:
            pass

    def obtener_auditoria(self, limite: int = 500) -> List[Dict]:
        return [dict(r) for r in self._get_all(
            """SELECT a.*,u.usuario,u.nombre_completo
               FROM auditoria a LEFT JOIN usuarios u ON a.usuario_id=u.id
               ORDER BY a.fecha DESC LIMIT ?""", (limite,))]

    # ── Autenticación ──────────────────────────────────────────────────────────

    def verificar_login(self, usuario: str, password: str) -> Optional[Dict]:
        usu = usuario.upper()
        row = self._get_one("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usu,))
        if not row:
            return None
        u = dict(row)
        # Comprobar bloqueo
        if u.get("bloqueado_hasta"):
            try:
                bl = datetime.fromisoformat(str(u["bloqueado_hasta"]))
                if datetime.now() < bl:
                    mins = int((bl - datetime.now()).total_seconds() / 60) + 1
                    raise PermissionError(f"Cuenta bloqueada {mins} min.")
                else:
                    self.cursor.execute(
                        "UPDATE usuarios SET intentos_fallidos=0,bloqueado_hasta=NULL WHERE usuario=?", (usu,))
            except (ValueError, TypeError):
                pass
        # Verificar password
        salt = u.get("salt", "")
        if salt:
            ph, _ = self._hash_pbkdf2(password, salt)
            ok = hmac.compare_digest(ph, u["password_hash"])
        else:
            ok = hmac.compare_digest(self._hash_password(password), u["password_hash"])
            if ok:
                new_ph, new_salt = self._hash_pbkdf2(password)
                self.cursor.execute(
                    "UPDATE usuarios SET password_hash=?,salt=? WHERE usuario=?",
                    (new_ph, new_salt, usu))
        if ok:
            self.cursor.execute(
                "UPDATE usuarios SET intentos_fallidos=0,bloqueado_hasta=NULL,ultima_sesion=? WHERE usuario=?",
                (datetime.now().isoformat(), usu))
            self.conn.commit()
            self.registrar_auditoria(u["id"], "LOGIN_OK", "autenticacion", "login exitoso")
            return {"id": u["id"], "usuario": u["usuario"],
                    "nombre_completo": u["nombre_completo"], "rol": u["rol"],
                    "email": u.get("email", "")}
        else:
            intentos = (u.get("intentos_fallidos") or 0) + 1
            bloq = None
            if intentos >= 5:
                bloq = (datetime.now() + timedelta(minutes=15)).isoformat()
            self.cursor.execute(
                "UPDATE usuarios SET intentos_fallidos=?,bloqueado_hasta=? WHERE usuario=?",
                (intentos, bloq, usu))
            self.conn.commit()
            self.registrar_auditoria(u["id"], "LOGIN_FAIL", "autenticacion",
                                     f"intento fallido #{intentos}")
            return None

    # ── Proveedores ────────────────────────────────────────────────────────────

    def obtener_todos_proveedores(self) -> List[Dict]:
        return [dict(r) for r in self._get_all(
            "SELECT * FROM proveedores ORDER BY nombre")]

    def buscar_proveedor_en_texto(self, texto: str) -> Optional[sqlite3.Row]:
        """Busca el primer proveedor cuyo nombre aparece en el texto del PDF."""
        texto_low = texto.lower()
        for row in self._get_all("SELECT * FROM proveedores ORDER BY LENGTH(nombre) DESC"):
            if row["nombre"].lower() in texto_low:
                return row
        return None

    def insertar_proveedor(self, datos: dict) -> int:
        fields = ["nombre", "numero_proveedor", "cuenta_gasto", "categoria",
                  "razon_social", "cif_nif", "direccion", "email", "iban",
                  "cuenta_proveedor", "subcuenta_proveedor", "subcuenta_gasto",
                  "serie", "tipo_factura"]
        cols = [f for f in fields if f in datos]
        vals = [datos[f] for f in cols]
        sql = f"INSERT INTO proveedores ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})"
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_estado_variable(self, proveedor_id: int) -> int:
        row = self._get_one("SELECT cuenta_variable FROM proveedores WHERE id=?", (proveedor_id,))
        return int(row["cuenta_variable"]) if row and row["cuenta_variable"] is not None else 1

    def marcar_proveedor_variable(self, prov_id: int, es_variable: bool) -> None:
        """Marca/desmarca un proveedor como variable."""
        self.cursor.execute(
            "UPDATE proveedores SET cuenta_variable=? WHERE id=?",
            (1 if es_variable else 0, prov_id))
        self.conn.commit()

    def actualizar_proveedor(self, prov_id: int, **kwargs) -> None:
        """Actualiza campos del proveedor."""
        allowed = {"nombre", "numero_proveedor", "cuenta_gasto", "categoria",
                   "razon_social", "cif_nif", "direccion", "email", "iban"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [prov_id]
        self.cursor.execute(f"UPDATE proveedores SET {set_clause} WHERE id=?", vals)
        self.conn.commit()

    def eliminar_proveedor(self, prov_id: int) -> None:
        """Elimina un proveedor y sus reglas."""
        self.cursor.execute("DELETE FROM reglas_proveedor WHERE proveedor_id=?", (prov_id,))
        self.cursor.execute("DELETE FROM proveedores WHERE id=?", (prov_id,))
        self.conn.commit()

    # ── Reglas ─────────────────────────────────────────────────────────────────

    def obtener_reglas_proveedor(self, proveedor_id: Optional[int]) -> List[Dict]:
        if proveedor_id:
            rows = self._get_all(
                "SELECT * FROM reglas_proveedor WHERE proveedor_id=? ORDER BY prioridad DESC",
                (proveedor_id,))
        else:
            rows = self._get_all("SELECT * FROM reglas_proveedor ORDER BY prioridad DESC")
        return [dict(r) for r in rows]

    def obtener_todas_reglas_con_proveedor(self) -> List[Dict]:
        rows = self._get_all("""
            SELECT r.*, p.nombre as nombre_proveedor, p.numero_proveedor,
                   p.cuenta_gasto, p.categoria, p.cif_nif, p.razon_social
            FROM reglas_proveedor r
            JOIN proveedores p ON r.proveedor_id = p.id
            ORDER BY r.prioridad DESC
        """)
        return [dict(r) for r in rows]

    def obtener_todas_reglas_deterministas(self) -> List[Dict]:
        """Devuelve todas las reglas con sus campos match_* y set_*."""
        rows = self._get_all("""
            SELECT r.*, p.nombre as nombre_proveedor, p.numero_proveedor,
                   p.cif_nif, p.razon_social,
                   p.cuenta_gasto as cuenta_gasto_prov, p.categoria as categoria_prov
            FROM reglas_proveedor r
            JOIN proveedores p ON r.proveedor_id = p.id
            WHERE (r.activa IS NULL OR r.activa = 1)
            ORDER BY r.prioridad DESC
        """)
        return [dict(r) for r in rows]

    def guardar_regla_determinista(self, datos: dict) -> int:
        campos_validos = {
            "proveedor_id", "nombre_regla", "prioridad", "activa", "rule_type",
            "match_cif", "match_tipo_factura", "match_serie", "match_categoria",
            "set_cuenta_proveedor", "set_subcuenta_proveedor",
            "set_cuenta_gasto", "set_subcuenta_gasto",
            "set_serie", "set_categoria", "set_tipo_factura",
            "serie", "cuenta_gasto", "categoria",
            "cont_automatica",
        }
        rid = datos.pop("id", None)
        d = {k: v for k, v in datos.items() if k in campos_validos}
        if "serie" not in d:
            d["serie"] = d.get("nombre_regla", "")
        if "cuenta_gasto" not in d:
            d["cuenta_gasto"] = d.get("set_cuenta_gasto", "")
        if "categoria" not in d:
            d["categoria"] = d.get("set_categoria", "")
        if rid:
            sets = ", ".join(f"{k}=?" for k in d)
            self.cursor.execute(
                f"UPDATE reglas_proveedor SET {sets} WHERE id=?",
                list(d.values()) + [rid])
            self.conn.commit()
            return rid
        else:
            cols = list(d.keys())
            self.cursor.execute(
                f"INSERT INTO reglas_proveedor ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                list(d.values()))
            self.conn.commit()
            return self.cursor.lastrowid

    def guardar_regla_manual(self, proveedor_id: int, palabra: str,
                              cuenta: str, categoria: str) -> None:
        self.cursor.execute("""
            INSERT OR REPLACE INTO reglas_proveedor (proveedor_id, serie, cuenta_gasto, categoria)
            VALUES (?,?,?,?)""", (proveedor_id, palabra, cuenta, categoria))
        self.conn.commit()

    def buscar_regla_por_disparador(self, proveedor_id: int, texto: str) -> Optional[Dict]:
        reglas = self.obtener_reglas_proveedor(proveedor_id)
        texto_low = texto.lower()
        for r in sorted(reglas, key=lambda x: x.get("prioridad", 1), reverse=True):
            trigger = str(r.get("serie", "")).lower()
            if trigger and trigger in texto_low:
                return r
        return None

    def eliminar_regla_proveedor(self, regla_id: int) -> None:
        self.cursor.execute("DELETE FROM reglas_proveedor WHERE id=?", (regla_id,))
        self.conn.commit()

    def actualizar_regla_proveedor(self, regla_id: int, datos: dict) -> None:
        campos_validos = {"serie", "cuenta_gasto", "categoria", "prioridad", "activa", "rule_type"}
        sets = []; vals = []
        for k, v in datos.items():
            if k in campos_validos:
                sets.append(f"{k}=?"); vals.append(v)
        if not sets: return
        vals.append(regla_id)
        self.cursor.execute(f"UPDATE reglas_proveedor SET {', '.join(sets)} WHERE id=?", vals)
        self.conn.commit()

    def duplicar_regla_proveedor(self, regla_id: int) -> int:
        r = self._get_one("SELECT * FROM reglas_proveedor WHERE id=?", (regla_id,))
        if not r: return -1
        self.cursor.execute("""
            INSERT INTO reglas_proveedor (proveedor_id, serie, cuenta_gasto, categoria, prioridad, activa)
            VALUES (?,?,?,?,?,1)""",
            (r["proveedor_id"], r["serie"] + " (copia)", r["cuenta_gasto"],
             r["categoria"], r.get("prioridad", 1)))
        self.conn.commit()
        return self.cursor.lastrowid

    def toggle_regla_proveedor(self, regla_id: int) -> int:
        r = self._get_one("SELECT activa FROM reglas_proveedor WHERE id=?", (regla_id,))
        if not r: return 0
        nuevo = 0 if r["activa"] else 1
        self.cursor.execute("UPDATE reglas_proveedor SET activa=? WHERE id=?", (nuevo, regla_id))
        self.conn.commit()
        return nuevo

    # ── Plantillas OCR ────────────────────────────────────────────────────────

    def guardar_plantilla_ocr(self, proveedor_id: int, campo: str,
                               plantilla_json: str, dpi: int = 300, pagina: int = 0) -> None:
        self.cursor.execute("""
            INSERT OR REPLACE INTO plantillas_ocr (proveedor_id, campo, plantilla_json, dpi, pagina)
            VALUES (?,?,?,?,?)""", (proveedor_id, campo, plantilla_json, dpi, pagina))
        self.conn.commit()

    def obtener_plantillas_ocr(self, proveedor_id: int) -> Dict[str, Any]:
        rows = self._get_all(
            "SELECT campo, plantilla_json, dpi, pagina FROM plantillas_ocr WHERE proveedor_id=?",
            (proveedor_id,))
        result = {}
        for r in rows:
            try:
                result[r["campo"]] = {
                    "coords": json.loads(r["plantilla_json"]),
                    "dpi": r["dpi"], "pagina": r["pagina"]
                }
            except Exception:
                pass
        return result

    # ── Historial / Deduplicación ──────────────────────────────────────────────

    def factura_ya_procesada(self, hash_pdf: str) -> bool:
        return self._get_one(
            "SELECT 1 FROM historial_procesado WHERE hash_pdf=?", (hash_pdf,)) is not None

    def get_historial(self, limit: int = 500) -> List[Dict]:
        """Devuelve el historial de facturas procesadas."""
        rows = self._get_all("""
            SELECT fecha_procesado, nombre_archivo, nombre_proveedor,
                   numero_proveedor, cuenta_gasto, tipo_factura, numero_factura,
                   ruta_archivo_final, hash_pdf
            FROM historial_procesado
            ORDER BY fecha_procesado DESC
            LIMIT ?""", (limit,))
        return [dict(r) for r in rows]

    def obtener_info_factura_procesada(self, hash_pdf: str) -> Optional[Dict]:
        row = self._get_one(
            "SELECT * FROM historial_procesado WHERE hash_pdf=?", (hash_pdf,))
        return dict(row) if row else None

    def registrar_procesado(self, hash_pdf: str, nombre_archivo: str,
                             datos: Optional[dict] = None) -> None:
        d = datos or {}
        self.cursor.execute("""
            INSERT OR REPLACE INTO historial_procesado
            (hash_pdf, nombre_archivo, nombre_proveedor, numero_proveedor,
             cuenta_gasto, serie_factura, tipo_factura, numero_factura,
             proveedor_id, ruta_archivo_final, es_rectificativa, numero_factura_manual)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (hash_pdf, nombre_archivo,
             d.get("nombre_proveedor"), d.get("numero_proveedor"),
             d.get("cuenta_gasto"), d.get("serie_factura"),
             d.get("tipo_factura"), d.get("numero_factura"),
             d.get("proveedor_id"), d.get("ruta_archivo_final"),
             d.get("es_rectificativa", 0), d.get("numero_factura_manual", "")))
        self.conn.commit()

    def actualizar_ruta_archivo(self, hash_pdf: str, nueva_ruta: str) -> bool:
        try:
            self.cursor.execute(
                "UPDATE historial_procesado SET ruta_archivo_final=? WHERE hash_pdf=?",
                (nueva_ruta, hash_pdf))
            self.cursor.execute(
                "UPDATE facturas_procesadas_v10 SET ruta_pdf=?, ruta_archivo_final=? WHERE hash_pdf=?",
                (nueva_ruta, nueva_ruta, hash_pdf))
            self.conn.commit()
            return True
        except Exception as exc:
            log.error("Error actualizando ruta: %s", exc)
            return False

    def marcar_factura_impresa(self, hash_pdf: str) -> None:
        """Marca una factura como impresa."""
        self.cursor.execute("""
            UPDATE historial_procesado SET impresa=1, impresa_en=CURRENT_TIMESTAMP
            WHERE hash_pdf=?""", (hash_pdf,))
        self.conn.commit()

    # ── V10: Registro financiero de facturas ──────────────────────────────────

    def registrar_factura_v10(self, datos: dict) -> int:
        """Guarda una factura procesada con datos financieros completos."""
        cols = [
            "id_proveedor", "fecha", "ruta_pdf", "ruta_archivo_final",
            "base_imponible", "iva", "total",
            "tipo_factura", "cuenta_gasto", "categoria", "numero_factura",
            "procesada_desde_correo", "numero_proveedor", "origen_correo",
            "id_mensaje_unico", "hash_pdf", "nombre_proveedor", "cif_proveedor",
            "id_regla_aplicada", "es_rectificativa", "numero_factura_manual",
            "subcuenta_gasto", "serie_factura", "cuenta_proveedor",
            "subcuenta_proveedor", "impresa", "impresa_en",
            "nombre_regla", "razon_social_prov",
            "cont_automatica", "fecha_factura", "fecha_contabilizacion",
        ]
        existing = [c for c in cols if c in datos]
        vals = [datos[c] for c in existing]
        placeholders = ",".join("?" * len(existing))
        sql = f"INSERT OR REPLACE INTO facturas_procesadas_v10 ({','.join(existing)}) VALUES ({placeholders})"
        try:
            self.cursor.execute(sql, vals)
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as exc:
            log.error("Error registrando factura V10: %s", exc)
            return -1

    def obtener_facturas_rango(self, fecha_desde: str = None, fecha_hasta: str = None,
                                proveedor_id: int = None, categoria: str = None,
                                tipo_factura: str = None) -> List[Dict]:
        """Obtiene facturas con filtros avanzados."""
        conditions = []
        params = []
        if fecha_desde:
            conditions.append("f.fecha >= ?")
            params.append(fecha_desde)
        if fecha_hasta:
            conditions.append("f.fecha <= ?")
            params.append(fecha_hasta)
        if proveedor_id:
            conditions.append("f.id_proveedor = ?")
            params.append(proveedor_id)
        if categoria:
            conditions.append("f.categoria = ?")
            params.append(categoria)
        if tipo_factura:
            conditions.append("f.tipo_factura = ?")
            params.append(tipo_factura)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT f.id, f.id_proveedor, f.fecha, f.ruta_pdf, f.ruta_archivo_final,
                   f.base_imponible, f.iva, f.total, f.tipo_factura, f.cuenta_gasto,
                   f.subcuenta_gasto, f.categoria, f.numero_factura,
                   f.procesada_desde_correo, f.numero_proveedor, f.origen_correo,
                   f.id_mensaje_unico, f.hash_pdf, f.fecha_procesado,
                   f.nombre_proveedor, f.cif_proveedor, f.serie_factura,
                   f.cuenta_proveedor, f.subcuenta_proveedor,
                   f.id_regla_aplicada, f.es_rectificativa, f.numero_factura_manual,
                   f.nombre_regla, f.razon_social_prov, f.impresa, f.impresa_en,
                   f.fecha_factura, f.fecha_contabilizacion,
                   p.cif_nif as cif_prov, p.numero_proveedor as num_prov,
                   COALESCE(r.cont_automatica, 0) as cont_automatica
            FROM facturas_procesadas_v10 f
            LEFT JOIN proveedores p ON f.id_proveedor = p.id
            LEFT JOIN reglas_proveedor r ON f.id_regla_aplicada = r.id
            {where}
            ORDER BY f.fecha DESC, f.fecha_procesado DESC
        """
        return [dict(r) for r in self._get_all(sql, tuple(params))]

    def obtener_estadisticas_periodo(self, fecha_desde: str = None,
                                      fecha_hasta: str = None,
                                      tipo_coste: str = "todos",
                                      tipo_factura: str = None,
                                      proveedor_id: int = None,
                                      categoria: str = None) -> Dict:
        """
        Estadísticas agregadas para informes.
        Los importes de rectificativas (es_rectificativa=1) aparecen con signo negativo.
        """
        conditions = []
        params = []
        if fecha_desde:
            conditions.append("fecha >= ?"); params.append(fecha_desde)
        if fecha_hasta:
            conditions.append("fecha <= ?"); params.append(fecha_hasta)
        if tipo_coste == "gastos":
            conditions.append("cuenta_gasto LIKE '6%'")
        elif tipo_coste == "compras":
            conditions.append("(cuenta_gasto LIKE '3%' OR cuenta_gasto LIKE '4%')")
        if tipo_factura:
            conditions.append("tipo_factura = ?"); params.append(tipo_factura)
        if proveedor_id:
            conditions.append("id_proveedor = ?"); params.append(proveedor_id)
        if categoria:
            conditions.append("categoria = ?"); params.append(categoria)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # Función para aplicar signo según rectificativa
        def signo_sql(campo):
            return campo  # Ya viene con signo desde la BD

        # Totales por proveedor
        por_proveedor = [dict(r) for r in self._get_all(f"""
            SELECT nombre_proveedor,
                   MIN(cif_proveedor) as cif_proveedor,
                   MIN(cuenta_gasto) as cuenta_gasto,
                   COUNT(*) as num_facturas,
                   SUM({signo_sql('base_imponible')}) as total_base,
                   SUM({signo_sql('iva')}) as total_iva,
                   SUM({signo_sql('total')}) as total_total
            FROM facturas_procesadas_v10 {where}
            GROUP BY nombre_proveedor ORDER BY total_base DESC
        """, tuple(params))]

        # Totales por categoría
        por_categoria = [dict(r) for r in self._get_all(f"""
            SELECT categoria, COUNT(*) as num_facturas,
                   MIN(cuenta_gasto) as cuenta_gasto,
                   SUM({signo_sql('base_imponible')}) as total_base,
                   SUM({signo_sql('iva')}) as total_iva,
                   SUM({signo_sql('total')}) as total_total
            FROM facturas_procesadas_v10 {where}
            GROUP BY categoria ORDER BY total_base DESC
        """, tuple(params))]

        # Totales por tipo factura
        por_tipo = [dict(r) for r in self._get_all(f"""
            SELECT tipo_factura, COUNT(*) as num_facturas,
                   SUM({signo_sql('base_imponible')}) as total_base,
                   SUM({signo_sql('total')}) as total_total
            FROM facturas_procesadas_v10 {where}
            GROUP BY tipo_factura ORDER BY total_base DESC
        """, tuple(params))]

        # Totales por serie
        por_serie = [dict(r) for r in self._get_all(f"""
            SELECT serie_factura,
                   COUNT(*) as num_facturas,
                   SUM({signo_sql('base_imponible')}) as total_base,
                   SUM({signo_sql('iva')}) as total_iva,
                   SUM({signo_sql('total')}) as total_total
            FROM facturas_procesadas_v10 {where}
            GROUP BY serie_factura ORDER BY serie_factura
        """, tuple(params))]

        # Totales por mes
        por_mes = [dict(r) for r in self._get_all(f"""
            SELECT substr(fecha,1,7) as mes, COUNT(*) as num_facturas,
                   SUM({signo_sql('base_imponible')}) as total_base,
                   SUM({signo_sql('iva')}) as total_iva,
                   SUM({signo_sql('total')}) as total_total
            FROM facturas_procesadas_v10 {where}
            GROUP BY mes ORDER BY mes
        """, tuple(params))]

        # Log para depuración
        log.info(f"Estadísticas por mes: {por_mes}")
        log.info(f"Estadísticas por serie: {por_serie}")

        return {
            "por_proveedor": por_proveedor,
            "por_categoria": por_categoria,
            "por_tipo": por_tipo,
            "por_serie": por_serie,
            "por_mes": por_mes,
        }

    # ── Config UI ─────────────────────────────────────────────────────────────

    def get_config_ui(self, clave: str, default: str = "") -> str:
        row = self._get_one("SELECT valor FROM config_ui WHERE clave=?", (clave,))
        return row["valor"] if row else default

    def set_config_ui(self, clave: str, valor: str) -> None:
        self.cursor.execute(
            "INSERT OR REPLACE INTO config_ui (clave,valor) VALUES (?,?)", (clave, valor))
        self.conn.commit()

    # ── Filtros ───────────────────────────────────────────────────────────────

    def is_filtro_activo(self) -> bool:
        row = self._get_one("SELECT activo FROM estado_filtros WHERE id=1")
        return bool(row["activo"]) if row else False

    def toggle_filtro_global(self, estado: bool) -> None:
        self.cursor.execute("INSERT OR REPLACE INTO estado_filtros (id,activo) VALUES (1,?)",
                            (int(estado),))
        self.conn.commit()

    def obtener_palabras_filtro(self) -> List[str]:
        return [r[0] for r in self._get_all("SELECT palabra FROM filtros_descarga")]

    def añadir_palabra_filtro(self, palabra: str) -> None:
        self.cursor.execute("INSERT OR IGNORE INTO filtros_descarga (palabra) VALUES (?)", (palabra,))
        self.conn.commit()

    def eliminar_palabra_filtro(self, palabra: str) -> None:
        self.cursor.execute("DELETE FROM filtros_descarga WHERE palabra=?", (palabra,))
        self.conn.commit()

    # ── Tipos de factura ──────────────────────────────────────────────────────

    def obtener_tipos_factura(self) -> List[Dict]:
        return [dict(r) for r in self._get_all("SELECT * FROM tipos_factura ORDER BY orden, nombre")]

    def añadir_tipo_factura(self, nombre: str, abreviatura: str) -> bool:
        try:
            self.cursor.execute(
                "INSERT INTO tipos_factura (nombre, abreviatura) VALUES (?,?)", (nombre, abreviatura))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def eliminar_tipo_factura(self, tipo_id: int) -> None:
        self.cursor.execute("DELETE FROM tipos_factura WHERE id=?", (tipo_id,))
        self.conn.commit()

    # ── Series de factura ─────────────────────────────────────────────────────

    def obtener_series_factura(self) -> List[Dict]:
        return [dict(r) for r in self._get_all("SELECT * FROM series_factura ORDER BY nombre")]

    def añadir_serie_factura(self, nombre: str, descripcion: str = "") -> bool:
        try:
            self.cursor.execute(
                "INSERT INTO series_factura (nombre, descripcion) VALUES (?,?)", (nombre, descripcion))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def eliminar_serie_factura(self, serie_id: int) -> None:
        self.cursor.execute("DELETE FROM series_factura WHERE id=?", (serie_id,))
        self.conn.commit()

    # ── Empresa ────────────────────────────────────────────────────────────────

    def get_empresa_cliente(self) -> Optional[Dict]:
        row = self._get_one("SELECT * FROM empresa_cliente WHERE id=1")
        return dict(row) if row else None

    def actualizar_datos_empresa(self, razon_social: str, cif: str,
                                  direccion: str, cp: str = "", email: str = "") -> None:
        self.cursor.execute("""
            INSERT OR REPLACE INTO empresa_cliente (id, razon_social, cif, direccion, codigo_postal, email)
            VALUES (1,?,?,?,?,?)""", (razon_social, cif, direccion, cp, email))
        self.conn.commit()

    # ── Cuentas Gmail / IMAP ──────────────────────────────────────────────────

    def obtener_cuentas_gmail(self) -> List[Dict]:
        return [dict(r) for r in self._get_all("SELECT * FROM cuentas_gmail ORDER BY es_principal DESC")]

    def eliminar_cuenta_email(self, email: str) -> None:
        self.cursor.execute("DELETE FROM cuentas_gmail WHERE email=?", (email,))
        self.conn.commit()

    # ── IA Config ─────────────────────────────────────────────────────────

    def get_ia_config(self, motor: str = "gemini") -> Dict:
        prefix = f"ia_{motor}_"
        claves = [r["clave"] for r in self._get_all(
            "SELECT clave FROM config_ui WHERE clave LIKE ?", (prefix+"%",))]
        return {c.replace(prefix, ""): self.get_config_ui(c) for c in claves}

    def set_ia_config(self, motor: str, datos: dict) -> None:
        prefix = f"ia_{motor}_"
        for k, v in datos.items():
            self.set_config_ui(prefix+k, str(v))
        self.conn.commit()

    # ── Memoria IA ────────────────────────────────────────────────────────────

    def ia_memory_get(self, hash_pdf: str = None, prov_id: int = None, tipo: str = "") -> Optional[Dict]:
        import json
        if hash_pdf:
            r = self._get_one("SELECT memo_json FROM ia_memory WHERE hash_pdf=? AND tipo=?",
                              (hash_pdf, tipo))
        elif prov_id is not None:
            r = self._get_one("SELECT memo_json FROM ia_memory WHERE prov_id=? AND tipo=?",
                              (prov_id, tipo))
        else:
            return None
        if r and r["memo_json"]:
            try: return json.loads(r["memo_json"])
            except Exception: return None
        return None

    def ia_memory_set(self, memo: dict, hash_pdf: str = None,
                      prov_id: int = None, tipo: str = "") -> None:
        import json
        self.cursor.execute("""
            INSERT INTO ia_memory (hash_pdf, prov_id, tipo, memo_json, updated_at)
            VALUES (?,?,?,?, CURRENT_TIMESTAMP)
            ON CONFLICT(hash_pdf, prov_id, tipo)
            DO UPDATE SET memo_json=excluded.memo_json, updated_at=excluded.updated_at
        """, (hash_pdf, prov_id, tipo, json.dumps(memo, ensure_ascii=False)))
        self.conn.commit()

    # ── Cierre ────────────────────────────────────────────────────────────────

    def cerrar(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass