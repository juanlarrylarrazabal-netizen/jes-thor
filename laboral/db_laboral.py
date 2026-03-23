# -*- coding: utf-8 -*-
"""
Capa de acceso a datos del módulo laboral.
Extiende el DatabaseManager existente SIN modificarlo: añade tablas nuevas
mediante CREATE TABLE IF NOT EXISTS y métodos propios en esta clase separada.

Uso:
    from laboral.db_laboral import LaboralDB
    db = LaboralDB()          # reutiliza la misma conexión singleton
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.logging_config import get_logger

log = get_logger("laboral.db")


class LaboralDB:
    """
    Wrapper de acceso a datos del módulo laboral.
    Recibe la conexión del DatabaseManager ya inicializado (o crea la suya propia).
    Crea las tablas laboral_* si no existen.
    """

    def __init__(self, db=None):
        if db is None:
            from database.manager import DatabaseManager
            db = DatabaseManager()
        self._db = db
        self.conn   = db.conn
        self.cursor = db.cursor
        self._migrate()

    # ── Migraciones ────────────────────────────────────────────────────────────

    def _migrate(self) -> None:
        self._create_empleados()
        self._create_nominas()
        self._create_nomina_lineas()
        self._create_fichajes()
        self._create_portal_docs()
        self._create_portal_mensajes()
        self._create_portal_anuncios()
        self._create_dispositivos()
        self._create_api_movil()
        self._migrate_empleados_v8()
        self._create_conceptos_nomina()
        self._repair_calendario_v8()   # repara tabla si tiene UNIQUE roto
        self._create_calendario_laboral()
        self.conn.commit()
        log.info("Módulo laboral: tablas verificadas/creadas")

    def _repair_calendario_v8(self) -> None:
        """
        Repara la tabla laboral_calendario si fue creada con una restricción
        UNIQUE que usa COALESCE (no soportada por SQLite en constraints).
        Detecta el problema inspeccionando el SQL de creación y, si existe,
        recrea la tabla correctamente conservando los datos existentes.
        """
        try:
            self.cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='laboral_calendario'")
            row = self.cursor.fetchone()
            if row and "COALESCE" in (row[0] or "").upper():
                log.warning("Reparando laboral_calendario: eliminando UNIQUE con COALESCE...")
                # Guardar datos existentes si los hay
                try:
                    self.cursor.execute("SELECT * FROM laboral_calendario")
                    cols_info = [d[0] for d in self.cursor.description]
                    filas = self.cursor.fetchall()
                except Exception:
                    cols_info, filas = [], []
                # Borrar tabla rota
                self.cursor.execute("DROP TABLE IF EXISTS laboral_calendario")
                self.conn.commit()
                log.info("Tabla laboral_calendario eliminada para recreación limpia (%d filas preservadas)", len(filas))
                # Recrear (lo hará _create_calendario_laboral a continuación)
                # Restaurar datos si los había
                self._create_calendario_laboral()
                if filas and cols_info:
                    cols_comunes = [c for c in cols_info if c != "id"]
                    placeholders = ",".join("?" * len(cols_comunes))
                    col_idx = {c: i for i, c in enumerate(cols_info)}
                    for fila in filas:
                        vals = [fila[col_idx[c]] for c in cols_comunes]
                        self.cursor.execute(
                            f"INSERT INTO laboral_calendario ({','.join(cols_comunes)}) "
                            f"VALUES ({placeholders})", vals)
                    self.conn.commit()
                    log.info("Datos de laboral_calendario restaurados: %d filas", len(filas))
        except Exception as e:
            log.warning("_repair_calendario_v8: %s (ignorando)", e)

    def _create_empleados(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_empleados (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                -- Datos personales
                nombre              TEXT NOT NULL,
                apellidos           TEXT NOT NULL,
                nif                 TEXT UNIQUE,
                direccion           TEXT,
                telefono            TEXT,
                email               TEXT,
                -- Datos laborales
                numero_ss           TEXT,
                fecha_incorporacion DATE,
                categoria           TEXT,
                convenio            TEXT,
                fecha_contrato      DATE,
                estado              TEXT DEFAULT 'activo'
                                    CHECK(estado IN ('activo','baja','excedencia','vacaciones','eliminado')),
                fecha_baja          DATE,
                fecha_eliminacion   TIMESTAMP,  -- soft delete timestamp
                -- Contacto de emergencia
                contacto_nombre     TEXT,
                contacto_telefono   TEXT,
                contacto_email      TEXT,
                -- RGPD
                rgpd_aceptado       INTEGER DEFAULT 0,
                rgpd_fecha          DATE,
                -- Información adicional
                incidencias         TEXT,
                dias_vacaciones     INTEGER DEFAULT 22,
                dias_vacaciones_usados INTEGER DEFAULT 0,
                -- Metadatos
                fecha_creacion      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notas               TEXT,
                -- Campos ampliados V8
                fecha_nacimiento    DATE,
                fecha_alta_empresa  DATE,
                iban                TEXT,
                departamento        TEXT,
                centro_trabajo      TEXT
            )""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_bajas_medicas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER NOT NULL REFERENCES laboral_empleados(id) ON DELETE CASCADE,
                fecha_inicio    DATE NOT NULL,
                fecha_fin       DATE,
                motivo          TEXT,
                tipo            TEXT DEFAULT 'IT'
                                CHECK(tipo IN ('IT','AT','EP','MAT','PAT')),
                documento_path  TEXT,
                fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_vacaciones (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER NOT NULL REFERENCES laboral_empleados(id) ON DELETE CASCADE,
                fecha_inicio    DATE NOT NULL,
                fecha_fin       DATE NOT NULL,
                dias            INTEGER,
                estado          TEXT DEFAULT 'pendiente'
                                CHECK(estado IN ('pendiente','aprobada','denegada','cancelada')),
                observaciones   TEXT,
                fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    def _create_nominas(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_nominas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER REFERENCES laboral_empleados(id) ON DELETE SET NULL,
                anio            INTEGER NOT NULL,
                mes             INTEGER NOT NULL CHECK(mes BETWEEN 1 AND 12),
                -- Importes principales
                salario_base    REAL DEFAULT 0,
                complementos    REAL DEFAULT 0,
                horas_extra     REAL DEFAULT 0,
                devengos_total  REAL DEFAULT 0,
                -- Deducciones
                ss_empleado     REAL DEFAULT 0,
                irpf            REAL DEFAULT 0,
                otras_deduc     REAL DEFAULT 0,
                deducciones_total REAL DEFAULT 0,
                -- Totales
                liquido         REAL DEFAULT 0,
                -- Costes empresa
                ss_empresa      REAL DEFAULT 0,
                coste_empresa   REAL DEFAULT 0,
                -- Fichero
                pdf_path        TEXT,
                pdf_hash        TEXT,
                -- Estado
                estado          TEXT DEFAULT 'pendiente'
                                CHECK(estado IN ('pendiente','procesada','enviada','error')),
                enviada_email   INTEGER DEFAULT 0,
                fecha_envio     TIMESTAMP,
                -- Metadatos
                origen_pdf      TEXT,
                fecha_procesado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notas           TEXT,
                UNIQUE(empleado_id, anio, mes)
            )""")

    def _create_nomina_lineas(self) -> None:
        """Líneas detalle de cada nómina (devengos y deducciones individuales)."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_nomina_lineas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nomina_id   INTEGER NOT NULL REFERENCES laboral_nominas(id) ON DELETE CASCADE,
                tipo        TEXT NOT NULL CHECK(tipo IN ('devengo','deduccion')),
                concepto    TEXT NOT NULL,
                importe     REAL DEFAULT 0,
                orden       INTEGER DEFAULT 0
            )""")

    def _create_fichajes(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_fichajes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER REFERENCES laboral_empleados(id) ON DELETE SET NULL,
                fecha           DATE NOT NULL,
                hora_entrada    TEXT,
                hora_salida     TEXT,
                minutos_trabajados INTEGER,
                tipo            TEXT DEFAULT 'normal'
                                CHECK(tipo IN ('normal','festivo','nocturno','extra')),
                dispositivo     TEXT,
                origen          TEXT DEFAULT 'manual'
                                CHECK(origen IN ('manual','zkteco_csv','zkteco_api','excel')),
                observaciones   TEXT,
                fecha_importacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_zkteco_config (
                id      INTEGER PRIMARY KEY CHECK(id=1),
                ip      TEXT,
                puerto  INTEGER DEFAULT 4370,
                usuario TEXT DEFAULT 'admin',
                clave   TEXT,
                activo  INTEGER DEFAULT 0
            )""")
        # Insertar fila config si no existe
        self.cursor.execute(
            "INSERT OR IGNORE INTO laboral_zkteco_config(id) VALUES(1)")

    def _create_portal_docs(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_portal_documentos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER REFERENCES laboral_empleados(id) ON DELETE CASCADE,
                tipo        TEXT NOT NULL
                            CHECK(tipo IN ('contrato','nomina','baja','vacaciones',
                                           'protocolo','otro')),
                titulo      TEXT NOT NULL,
                descripcion TEXT,
                ruta        TEXT,
                visible     INTEGER DEFAULT 1,
                fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    def _create_portal_mensajes(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_portal_mensajes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER REFERENCES laboral_empleados(id),
                tipo        TEXT DEFAULT 'sugerencia'
                            CHECK(tipo IN ('sugerencia','denuncia','consulta')),
                asunto      TEXT,
                cuerpo      TEXT,
                anonimo     INTEGER DEFAULT 0,
                leido       INTEGER DEFAULT 0,
                respuesta   TEXT,
                fecha       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    def _create_portal_anuncios(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_portal_anuncios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo      TEXT NOT NULL,
                cuerpo      TEXT,
                tipo        TEXT DEFAULT 'anuncio'
                            CHECK(tipo IN ('anuncio','urgente','protocolo')),
                activo      INTEGER DEFAULT 1,
                fecha_inicio DATE,
                fecha_fin    DATE,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    # ── CRUD Empleados ─────────────────────────────────────────────────────────

    def insertar_empleado(self, datos: dict) -> int:
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_empleados ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        eid = self.cursor.lastrowid
        log.info("Empleado creado: id=%d nombre=%s %s", eid,
                 datos.get('nombre',''), datos.get('apellidos',''))
        return eid

    def actualizar_empleado(self, empleado_id: int, datos: dict) -> None:
        sets = ", ".join(f"{k}=?" for k in datos)
        vals = list(datos.values()) + [empleado_id]
        self.cursor.execute(
            f"UPDATE laboral_empleados SET {sets} WHERE id=?", vals)
        self.conn.commit()

    def obtener_empleados(self, solo_activos: bool = False) -> List[Dict]:
        sql = "SELECT * FROM laboral_empleados"
        if solo_activos:
            sql += " WHERE estado='activo'"
        sql += " ORDER BY apellidos, nombre"
        self.cursor.execute(sql)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def obtener_empleado(self, empleado_id: int) -> Optional[Dict]:
        self.cursor.execute(
            "SELECT * FROM laboral_empleados WHERE id=?", (empleado_id,))
        cols = [d[0] for d in self.cursor.description]
        r = self.cursor.fetchone()
        return dict(zip(cols, r)) if r else None

    def buscar_empleado_por_nombre(self, texto: str) -> Optional[Dict]:
        """Búsqueda aproximada por nombre+apellidos para matching de nóminas."""
        texto_norm = texto.lower().strip()
        for emp in self.obtener_empleados():
            nombre_completo = f"{emp['nombre']} {emp['apellidos']}".lower()
            apellidos_nombre = f"{emp['apellidos']} {emp['nombre']}".lower()
            if (texto_norm in nombre_completo or
                    texto_norm in apellidos_nombre or
                    nombre_completo in texto_norm or
                    apellidos_nombre in texto_norm):
                return emp
        return None

    def eliminar_empleado(self, empleado_id: int, definitivo: bool = False) -> None:
        """
        Elimina un empleado.
        definitivo=False (recomendado): soft delete → estado='eliminado'
        definitivo=True: borrado físico (no recomendable, pierde historial)
        """
        if definitivo:
            self.cursor.execute(
                "DELETE FROM laboral_empleados WHERE id=?", (empleado_id,))
            log.warning("Empleado %d eliminado definitivamente", empleado_id)
        else:
            self.cursor.execute(
                "UPDATE laboral_empleados SET estado='eliminado', "
                "fecha_eliminacion=CURRENT_TIMESTAMP WHERE id=?",
                (empleado_id,))
            log.info("Empleado %d marcado como eliminado (soft delete)", empleado_id)
        self.conn.commit()

    def reactivar_empleado(self, empleado_id: int) -> None:
        """Reactiva un empleado en baja o eliminado → estado='activo'."""
        self.cursor.execute(
            "UPDATE laboral_empleados SET estado='activo', "
            "fecha_baja=NULL, fecha_eliminacion=NULL WHERE id=?",
            (empleado_id,))
        self.conn.commit()
        log.info("Empleado %d reactivado", empleado_id)

    def obtener_empleados_todos(self) -> List[Dict]:
        """Devuelve TODOS los empleados incluidos los eliminados (para gestión admin)."""
        self.cursor.execute(
            "SELECT * FROM laboral_empleados ORDER BY estado, apellidos, nombre")
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    # ── CRUD Dispositivos ──────────────────────────────────────────────────────

    def _create_dispositivos(self) -> None:
        """Crea la tabla de dispositivos corporativos si no existe."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_dispositivos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id         INTEGER REFERENCES laboral_empleados(id) ON DELETE SET NULL,
                tipo_dispositivo    TEXT DEFAULT 'otro'
                                    CHECK(tipo_dispositivo IN
                                         ('telefono','tablet','portatil','otro')),
                marca               TEXT,
                modelo              TEXT,
                imei                TEXT,
                numero_serie        TEXT,
                extension           TEXT,
                telefono_asociado   TEXT,
                pin                 TEXT,
                puk                 TEXT,
                fecha_entrega       DATE,
                fecha_devolucion    DATE,
                estado              TEXT DEFAULT 'activo'
                                    CHECK(estado IN ('activo','sustituido','devuelto','perdido')),
                observaciones       TEXT,
                fecha_creacion      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        self.conn.commit()

    def insertar_dispositivo(self, datos: dict) -> int:
        self._create_dispositivos()
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_dispositivos ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        did = self.cursor.lastrowid
        log.info("Dispositivo creado: id=%d tipo=%s emp=%s",
                 did, datos.get('tipo_dispositivo'), datos.get('empleado_id'))
        return did

    def actualizar_dispositivo(self, dispositivo_id: int, datos: dict) -> None:
        self._create_dispositivos()
        sets = ", ".join(f"{k}=?" for k in datos)
        vals = list(datos.values()) + [dispositivo_id]
        self.cursor.execute(
            f"UPDATE laboral_dispositivos SET {sets} WHERE id=?", vals)
        self.conn.commit()

    def obtener_dispositivos(self, empleado_id: int = None,
                              estado: str = None) -> List[Dict]:
        self._create_dispositivos()
        conds, params = [], []
        if empleado_id:
            conds.append("d.empleado_id=?"); params.append(empleado_id)
        if estado:
            conds.append("d.estado=?"); params.append(estado)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT d.*, e.nombre||' '||e.apellidos as nombre_empleado
            FROM laboral_dispositivos d
            LEFT JOIN laboral_empleados e ON d.empleado_id=e.id
            {where}
            ORDER BY d.fecha_entrega DESC
        """
        self.cursor.execute(sql, params)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    # ── API Móvil: tabla de tokens y fichajes pendientes ───────────────────────

    def _create_api_movil(self) -> None:
        """Crea tablas para la futura app móvil de fichaje."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_api_tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER NOT NULL REFERENCES laboral_empleados(id),
                token           TEXT NOT NULL UNIQUE,
                dispositivo_desc TEXT,
                activo          INTEGER DEFAULT 1,
                fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultimo_uso      TIMESTAMP
            )""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_fichajes_movil (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER REFERENCES laboral_empleados(id),
                tipo_fichaje    TEXT DEFAULT 'entrada'
                                CHECK(tipo_fichaje IN
                                     ('entrada','salida','pausa','vuelta_pausa')),
                fecha           DATE NOT NULL,
                hora            TEXT NOT NULL,
                latitud         REAL,
                longitud        REAL,
                dispositivo     TEXT,
                token_id        INTEGER REFERENCES laboral_api_tokens(id),
                sincronizado    INTEGER DEFAULT 0,
                fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        # Tabla de firmas digitales para portal
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_firmas_digitales (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id     INTEGER NOT NULL REFERENCES laboral_empleados(id),
                documento_id    INTEGER REFERENCES laboral_portal_documentos(id),
                tipo_documento  TEXT,
                firma_hash      TEXT,
                ip_origen       TEXT,
                dispositivo     TEXT,
                fecha_firma     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valida          INTEGER DEFAULT 1
            )""")
        self.conn.commit()
        log.info("Tablas API móvil y firmas creadas/verificadas")

    def generar_token_empleado(self, empleado_id: int,
                                dispositivo_desc: str = "") -> str:
        """Genera un token de acceso para la app móvil de un empleado."""
        import secrets
        self._create_api_movil()
        token = secrets.token_urlsafe(32)
        self.cursor.execute("""
            INSERT INTO laboral_api_tokens
            (empleado_id, token, dispositivo_desc)
            VALUES (?, ?, ?)
        """, (empleado_id, token, dispositivo_desc))
        self.conn.commit()
        log.info("Token móvil generado para empleado %d", empleado_id)
        return token

    def registrar_fichaje_movil(self, datos: dict) -> int:
        """Registra un fichaje recibido desde la app móvil."""
        self._create_api_movil()
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_fichajes_movil ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()

        # Sincronizar automáticamente con la tabla principal de fichajes
        fid = self.cursor.lastrowid
        self._sincronizar_fichaje_movil(fid, datos)
        return fid

    def _sincronizar_fichaje_movil(self, fichaje_movil_id: int, datos: dict) -> None:
        """
        Convierte un fichaje móvil (entrada/salida/pausa/vuelta_pausa) al
        formato de laboral_fichajes, igual que los de ZKTeco.
        Solo entrada y salida se mapean directamente.
        """
        tipo = datos.get("tipo_fichaje", "entrada")
        emp_id = datos.get("empleado_id")
        fecha  = datos.get("fecha")
        hora   = datos.get("hora")

        if tipo == "entrada":
            self.insertar_fichaje({
                "empleado_id":  emp_id,
                "fecha":        fecha,
                "hora_entrada": hora,
                "origen":       "manual",
                "observaciones": "App móvil",
            })
        elif tipo == "salida":
            # Buscar fichaje del día y añadir salida
            fichajes = self.obtener_fichajes(
                empleado_id=emp_id, fecha_desde=fecha, fecha_hasta=fecha)
            f = next((f for f in fichajes if f.get("hora_entrada")), None)
            if f:
                from datetime import datetime
                try:
                    h1 = datetime.strptime(f["hora_entrada"], "%H:%M")
                    h2 = datetime.strptime(hora, "%H:%M")
                    mins = max(0, int((h2 - h1).total_seconds() / 60))
                except Exception:
                    mins = 0
                self.cursor.execute(
                    "UPDATE laboral_fichajes SET hora_salida=?, "
                    "minutos_trabajados=? WHERE id=?",
                    (hora, mins, f["id"]))
                self.conn.commit()

        # Marcar como sincronizado
        self.cursor.execute(
            "UPDATE laboral_fichajes_movil SET sincronizado=1 WHERE id=?",
            (fichaje_movil_id,))
        self.conn.commit()

    def insertar_nomina(self, datos: dict) -> int:
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT OR REPLACE INTO laboral_nominas ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_nominas(self, empleado_id: int = None,
                        anio: int = None, mes: int = None) -> List[Dict]:
        conds, params = [], []
        if empleado_id:
            conds.append("n.empleado_id=?"); params.append(empleado_id)
        if anio:
            conds.append("n.anio=?"); params.append(anio)
        if mes:
            conds.append("n.mes=?"); params.append(mes)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT n.*, e.nombre||' '||e.apellidos as nombre_empleado, e.email
            FROM laboral_nominas n
            LEFT JOIN laboral_empleados e ON n.empleado_id=e.id
            {where}
            ORDER BY n.anio DESC, n.mes DESC
        """
        self.cursor.execute(sql, params)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def marcar_nomina_enviada(self, nomina_id: int) -> None:
        self.cursor.execute(
            "UPDATE laboral_nominas SET enviada_email=1, estado='enviada', "
            "fecha_envio=CURRENT_TIMESTAMP WHERE id=?", (nomina_id,))
        self.conn.commit()

    # ── CRUD Fichajes ──────────────────────────────────────────────────────────

    def insertar_fichaje(self, datos: dict) -> int:
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT OR IGNORE INTO laboral_fichajes ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_fichajes(self, empleado_id: int = None,
                         fecha_desde: str = None, fecha_hasta: str = None) -> List[Dict]:
        conds, params = [], []
        if empleado_id:
            conds.append("f.empleado_id=?"); params.append(empleado_id)
        if fecha_desde:
            conds.append("f.fecha>=?"); params.append(fecha_desde)
        if fecha_hasta:
            conds.append("f.fecha<=?"); params.append(fecha_hasta)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
            SELECT f.*, e.nombre||' '||e.apellidos as nombre_empleado
            FROM laboral_fichajes f
            LEFT JOIN laboral_empleados e ON f.empleado_id=e.id
            {where}
            ORDER BY f.fecha DESC, f.hora_entrada
        """
        self.cursor.execute(sql, params)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def resumen_horas_mes(self, empleado_id: int, anio: int, mes: int) -> dict:
        self.cursor.execute("""
            SELECT COUNT(*) as dias_trabajados,
                   SUM(minutos_trabajados) as total_minutos,
                   SUM(CASE WHEN hora_entrada > '09:15' THEN 1 ELSE 0 END) as retrasos,
                   SUM(CASE WHEN minutos_trabajados < 420 THEN 1 ELSE 0 END) as jornadas_incompletas
            FROM laboral_fichajes
            WHERE empleado_id=?
              AND strftime('%Y',fecha)=?
              AND strftime('%m',fecha)=?
        """, (empleado_id, str(anio), f"{mes:02d}"))
        cols = [d[0] for d in self.cursor.description]
        r = self.cursor.fetchone()
        return dict(zip(cols, r)) if r else {}

    # ── Config ZKTeco ──────────────────────────────────────────────────────────

    def get_zkteco_config(self) -> dict:
        self.cursor.execute("SELECT * FROM laboral_zkteco_config WHERE id=1")
        cols = [d[0] for d in self.cursor.description]
        r = self.cursor.fetchone()
        return dict(zip(cols, r)) if r else {}

    def set_zkteco_config(self, ip: str, puerto: int, usuario: str,
                          clave: str, activo: bool) -> None:
        self.cursor.execute("""
            UPDATE laboral_zkteco_config
            SET ip=?, puerto=?, usuario=?, clave=?, activo=?
            WHERE id=1
        """, (ip, puerto, usuario, clave, 1 if activo else 0))
        self.conn.commit()

    # ── Portal ─────────────────────────────────────────────────────────────────

    def insertar_documento_portal(self, datos: dict) -> int:
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_portal_documentos ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_documentos_portal(self, empleado_id: int = None,
                                   tipo: str = None) -> List[Dict]:
        conds, params = [], []
        if empleado_id:
            conds.append("empleado_id=?"); params.append(empleado_id)
        if tipo:
            conds.append("tipo=?"); params.append(tipo)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        self.cursor.execute(
            f"SELECT * FROM laboral_portal_documentos {where} ORDER BY fecha_subida DESC",
            params)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def insertar_mensaje_portal(self, datos: dict) -> int:
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_portal_mensajes ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_anuncios_activos(self) -> List[Dict]:
        hoy = date.today().isoformat()
        self.cursor.execute("""
            SELECT * FROM laboral_portal_anuncios
            WHERE activo=1
              AND (fecha_inicio IS NULL OR fecha_inicio <= ?)
              AND (fecha_fin   IS NULL OR fecha_fin   >= ?)
            ORDER BY tipo DESC, fecha_creacion DESC
        """, (hoy, hoy))
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    # ── Migración V8: nuevos campos empleados ─────────────────────────────────

    def _migrate_empleados_v8(self) -> None:
        """Añade columnas V8 a laboral_empleados si no existen."""
        def _add(col, defn):
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(laboral_empleados)").fetchall()}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE laboral_empleados ADD COLUMN {col} {defn}")
                log.info("V8: columna añadida laboral_empleados.%s", col)
        _add("fecha_nacimiento",  "DATE")
        _add("fecha_alta_empresa","DATE")
        _add("iban",              "TEXT")
        _add("departamento",      "TEXT")
        _add("centro_trabajo",    "TEXT")
        _add("fecha_eliminacion", "TIMESTAMP")
        self.conn.commit()

    # ── Conceptos de nómina y reglas contables ────────────────────────────────

    def _create_conceptos_nomina(self) -> None:
        """Tabla de conceptos de nómina con reparto contable (similar a facturas)."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_conceptos_nomina (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo      TEXT NOT NULL UNIQUE,
                descripcion TEXT NOT NULL,
                tipo        TEXT DEFAULT 'devengo'
                            CHECK(tipo IN ('devengo','deduccion','empresa')),
                activo      INTEGER DEFAULT 1
            )""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_concepto_cuentas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                concepto_id INTEGER NOT NULL REFERENCES laboral_conceptos_nomina(id) ON DELETE CASCADE,
                cuenta      TEXT NOT NULL,
                subcuenta   TEXT DEFAULT '',
                porcentaje  REAL DEFAULT 100.0,
                descripcion TEXT
            )""")

        # Insertar conceptos comunes de nómina si no existen
        conceptos_base = [
            ("640", "Salario base",          "devengo"),
            ("641", "Complementos salariales","devengo"),
            ("642", "Horas extraordinarias",  "devengo"),
            ("640SS", "Seg. Social empresa",  "empresa"),
            ("465", "Retenciones IRPF",       "deduccion"),
            ("476", "Seg. Social empleado",   "deduccion"),
        ]
        for cod, desc, tipo in conceptos_base:
            self.cursor.execute(
                "INSERT OR IGNORE INTO laboral_conceptos_nomina(codigo,descripcion,tipo) VALUES(?,?,?)",
                (cod, desc, tipo))
        self.conn.commit()

    def obtener_conceptos_nomina(self, tipo: str = None) -> List[Dict]:
        cond  = "WHERE activo=1" + (f" AND tipo='{tipo}'" if tipo else "")
        self.cursor.execute(f"SELECT * FROM laboral_conceptos_nomina {cond} ORDER BY codigo")
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def obtener_cuentas_concepto(self, concepto_id: int) -> List[Dict]:
        self.cursor.execute(
            "SELECT * FROM laboral_concepto_cuentas WHERE concepto_id=? ORDER BY porcentaje DESC",
            (concepto_id,))
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def guardar_cuentas_concepto(self, concepto_id: int, cuentas: List[Dict]) -> None:
        """Reemplaza el reparto contable de un concepto."""
        self.cursor.execute(
            "DELETE FROM laboral_concepto_cuentas WHERE concepto_id=?", (concepto_id,))
        for c in cuentas:
            self.cursor.execute(
                "INSERT INTO laboral_concepto_cuentas(concepto_id,cuenta,subcuenta,porcentaje,descripcion) "
                "VALUES(?,?,?,?,?)",
                (concepto_id, c.get("cuenta",""), c.get("subcuenta",""),
                 c.get("porcentaje", 100.0), c.get("descripcion","")))
        self.conn.commit()

    def calcular_reparto_concepto(self, concepto_id: int, importe: float) -> List[Dict]:
        """Calcula los importes proporcionales por cuenta para un concepto."""
        cuentas = self.obtener_cuentas_concepto(concepto_id)
        resultado = []
        for c in cuentas:
            pct    = float(c.get("porcentaje", 100.0))
            imp    = round(importe * pct / 100, 2)
            resultado.append({**c, "importe_calculado": imp})
        return resultado

    # ── Calendario laboral ────────────────────────────────────────────────────

    def _create_calendario_laboral(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS laboral_calendario (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha           DATE NOT NULL,
                tipo_dia        TEXT DEFAULT 'laborable'
                                CHECK(tipo_dia IN ('laborable','festivo','festivo_local','vacacion')),
                horas_jornada   REAL DEFAULT 8.0,
                centro_trabajo  TEXT DEFAULT '',
                empleado_id     INTEGER REFERENCES laboral_empleados(id) ON DELETE CASCADE,
                descripcion     TEXT
            )""")
        self.conn.commit()

    def insertar_dia_calendario(self, datos: dict) -> int:
        # Borrar día existente con misma fecha/centro/empleado antes de insertar
        fecha      = datos.get("fecha", "")
        centro     = datos.get("centro_trabajo", "")
        emp_id     = datos.get("empleado_id")
        if emp_id:
            self.cursor.execute(
                "DELETE FROM laboral_calendario WHERE fecha=? AND centro_trabajo=? AND empleado_id=?",
                (fecha, centro, emp_id))
        else:
            self.cursor.execute(
                "DELETE FROM laboral_calendario WHERE fecha=? AND centro_trabajo=? AND empleado_id IS NULL",
                (fecha, centro))
        cols = [c for c in datos if datos[c] is not None]
        vals = [datos[c] for c in cols]
        sql  = (f"INSERT INTO laboral_calendario ({','.join(cols)}) "
                f"VALUES ({','.join('?'*len(cols))})")
        self.cursor.execute(sql, vals)
        self.conn.commit()
        return self.cursor.lastrowid

    def obtener_calendario(self, anio: int, mes: int,
                            centro: str = None,
                            empleado_id: int = None) -> List[Dict]:
        conds  = ["strftime('%Y',fecha)=?", "strftime('%m',fecha)=?"]
        params = [str(anio), f"{mes:02d}"]
        if centro is not None:
            conds.append("centro_trabajo=?"); params.append(centro)
        if empleado_id is not None:
            conds.append("(empleado_id IS NULL OR empleado_id=?)"); params.append(empleado_id)
        else:
            conds.append("empleado_id IS NULL")
        where = " AND ".join(conds)
        self.cursor.execute(
            f"SELECT * FROM laboral_calendario WHERE {where} ORDER BY fecha",
            params)
        cols = [d[0] for d in self.cursor.description]
        return [dict(zip(cols, r)) for r in self.cursor.fetchall()]

    def calcular_horas_mes(self, empleado_id: int, anio: int, mes: int) -> dict:
        """
        Cruza fichajes con calendario para calcular horas trabajadas,
        teóricas, extra y faltantes.
        """
        from calendar import monthrange
        _, dias_mes = monthrange(anio, mes)
        fecha_desde = f"{anio}-{mes:02d}-01"
        fecha_hasta = f"{anio}-{mes:02d}-{dias_mes}"

        fichajes   = self.obtener_fichajes(
            empleado_id=empleado_id,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        calendario = self.obtener_calendario(anio, mes, empleado_id=empleado_id)
        cal_map    = {c["fecha"]: c for c in calendario}

        total_trabajados = 0
        total_teoricos   = 0
        horas_extra      = 0
        horas_faltantes  = 0
        ausencias        = 0

        for d in range(1, dias_mes + 1):
            from datetime import date
            fecha_d = f"{anio}-{mes:02d}-{d:02d}"
            dia_sem = date(anio, mes, d).weekday()
            cal_dia = cal_map.get(fecha_d)

            # Horas teóricas del día
            if cal_dia:
                tipo = cal_dia.get("tipo_dia", "laborable")
                horas_teoricas_dia = 0 if tipo in ("festivo","festivo_local") else float(cal_dia.get("horas_jornada", 8))
            elif dia_sem >= 5:
                horas_teoricas_dia = 0  # fin de semana
            else:
                horas_teoricas_dia = 8  # default

            total_teoricos += horas_teoricas_dia

            # Horas reales (desde fichajes)
            f_dia = next((f for f in fichajes if f["fecha"] == fecha_d), None)
            if horas_teoricas_dia > 0 and not f_dia:
                ausencias += 1
            mins = (f_dia.get("minutos_trabajados") or 0) if f_dia else 0
            horas_dia = mins / 60

            if horas_teoricas_dia > 0:
                diff = horas_dia - horas_teoricas_dia
                if diff > 0:
                    horas_extra += diff
                elif diff < 0:
                    horas_faltantes += abs(diff)

            total_trabajados += horas_dia

        return {
            "horas_trabajadas":  round(total_trabajados, 2),
            "horas_teoricas":    round(total_teoricos, 2),
            "horas_extra":       round(horas_extra, 2),
            "horas_faltantes":   round(horas_faltantes, 2),
            "ausencias":         ausencias,
        }
