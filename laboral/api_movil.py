# -*- coding: utf-8 -*-
"""
API REST local para la app móvil de fichaje.
Implementada con http.server (stdlib) — sin dependencias externas.
La app móvil se conecta a http://IP_LOCAL:8765/api/v1/...

Endpoints:
  POST /api/v1/auth          → autenticar empleado, devuelve token
  POST /api/v1/fichaje       → registrar entrada/salida/pausa
  GET  /api/v1/fichajes      → obtener fichajes del empleado autenticado
  GET  /api/v1/documentos    → documentos del portal
  POST /api/v1/firma         → firmar un documento
  GET  /api/v1/nominas       → nóminas del empleado
  GET  /api/v1/status        → estado del servidor

Uso:
    from laboral.api_movil import ApiMovilServer
    server = ApiMovilServer(db_laboral=db, port=8765)
    server.start()   # inicia en hilo background
    server.stop()
"""
from __future__ import annotations
import json
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse, parse_qs

from core.logging_config import get_logger

log = get_logger("laboral.api_movil")

_CONTENT_JSON = "application/json; charset=utf-8"
_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def _json_resp(handler, code: int, data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", _CONTENT_JSON)
    handler.send_header("Content-Length", len(body))
    for k, v in _CORS_HEADERS.items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except Exception:
        return {}


def _get_token(handler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


class _RequestHandler(BaseHTTPRequestHandler):
    """Manejador de peticiones de la API móvil."""

    db = None  # Inyectado por ApiMovilServer

    def log_message(self, fmt, *args):
        log.debug("API [%s] %s", self.address_string(), fmt % args)

    def do_OPTIONS(self):
        self.send_response(200)
        for k, v in _CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "/api/v1/status":
            _json_resp(self, 200, {"status": "ok", "version": "1.0",
                                    "timestamp": datetime.now().isoformat()})
        elif path == "/api/v1/fichajes":
            self._handle_get_fichajes(params)
        elif path == "/api/v1/documentos":
            self._handle_get_documentos(params)
        elif path == "/api/v1/nominas":
            self._handle_get_nominas(params)
        else:
            _json_resp(self, 404, {"error": "Endpoint no encontrado"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "/api/v1/auth":
            self._handle_auth()
        elif path == "/api/v1/fichaje":
            self._handle_fichaje()
        elif path == "/api/v1/firma":
            self._handle_firma()
        else:
            _json_resp(self, 404, {"error": "Endpoint no encontrado"})

    # ── Auth ───────────────────────────────────────────────────────────────────

    def _handle_auth(self):
        body = _read_body(self)
        nif  = body.get("nif", "").strip().upper()
        pin  = body.get("pin", "").strip()

        if not nif:
            _json_resp(self, 400, {"error": "NIF requerido"}); return

        # Buscar empleado por NIF
        try:
            empleados = self.db.obtener_empleados(solo_activos=True)
            emp = next((e for e in empleados
                        if (e.get("nif") or "").upper() == nif), None)
        except Exception as e:
            log.error("Error buscando empleado: %s", e)
            _json_resp(self, 500, {"error": "Error interno"}); return

        if not emp:
            _json_resp(self, 401, {"error": "Empleado no encontrado"}); return

        # Generar token
        try:
            dispositivo = body.get("dispositivo", "app_movil")
            token = self.db.generar_token_empleado(emp["id"], dispositivo)
            _json_resp(self, 200, {
                "token":         token,
                "empleado_id":   emp["id"],
                "nombre":        f"{emp['nombre']} {emp['apellidos']}",
            })
        except Exception as e:
            log.error("Error generando token: %s", e)
            _json_resp(self, 500, {"error": "Error generando token"})

    # ── Fichaje ────────────────────────────────────────────────────────────────

    def _handle_fichaje(self):
        token = _get_token(self)
        if not token:
            _json_resp(self, 401, {"error": "Token requerido"}); return

        body = _read_body(self)
        tipo = body.get("tipo", "entrada")
        if tipo not in ("entrada", "salida", "pausa", "vuelta_pausa"):
            _json_resp(self, 400, {"error": "Tipo inválido"}); return

        # Verificar token
        try:
            self.db.cursor.execute(
                "SELECT * FROM laboral_api_tokens WHERE token=? AND activo=1",
                (token,))
            cols = [d[0] for d in self.db.cursor.description]
            row  = self.db.cursor.fetchone()
        except Exception:
            _json_resp(self, 500, {"error": "Error interno"}); return

        if not row:
            _json_resp(self, 401, {"error": "Token inválido o expirado"}); return

        tok_data  = dict(zip(cols, row))
        emp_id    = tok_data["empleado_id"]
        ahora     = datetime.now()

        datos_fichaje = {
            "empleado_id":  emp_id,
            "tipo_fichaje": tipo,
            "fecha":        ahora.strftime("%Y-%m-%d"),
            "hora":         ahora.strftime("%H:%M"),
            "latitud":      body.get("latitud"),
            "longitud":     body.get("longitud"),
            "dispositivo":  body.get("dispositivo", ""),
            "token_id":     tok_data["id"],
        }

        try:
            fid = self.db.registrar_fichaje_movil(datos_fichaje)
            # Actualizar último uso del token
            self.db.cursor.execute(
                "UPDATE laboral_api_tokens SET ultimo_uso=CURRENT_TIMESTAMP WHERE id=?",
                (tok_data["id"],))
            self.db.conn.commit()
            _json_resp(self, 200, {
                "ok":          True,
                "fichaje_id":  fid,
                "tipo":        tipo,
                "hora":        ahora.strftime("%H:%M"),
                "fecha":       ahora.strftime("%d/%m/%Y"),
            })
        except Exception as e:
            log.error("Error registrando fichaje móvil: %s", e)
            _json_resp(self, 500, {"error": str(e)})

    # ── Fichajes del empleado ─────────────────────────────────────────────────

    def _handle_get_fichajes(self, params):
        token = _get_token(self)
        emp_id = self._verificar_token(token)
        if not emp_id:
            _json_resp(self, 401, {"error": "No autorizado"}); return

        fecha_desde = params.get("desde", [date.today().isoformat()])[0]
        fecha_hasta = params.get("hasta", [date.today().isoformat()])[0]

        try:
            fichajes = self.db.obtener_fichajes(
                empleado_id=emp_id,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )
            _json_resp(self, 200, {"fichajes": fichajes})
        except Exception as e:
            _json_resp(self, 500, {"error": str(e)})

    # ── Documentos ────────────────────────────────────────────────────────────

    def _handle_get_documentos(self, params):
        token = _get_token(self)
        emp_id = self._verificar_token(token)
        if not emp_id:
            _json_resp(self, 401, {"error": "No autorizado"}); return

        tipo = params.get("tipo", [None])[0]
        try:
            docs = self.db.obtener_documentos_portal(
                empleado_id=emp_id, tipo=tipo)
            # No devolver rutas internas por seguridad
            docs_safe = [{k: v for k, v in d.items() if k != "ruta"}
                         for d in docs]
            _json_resp(self, 200, {"documentos": docs_safe})
        except Exception as e:
            _json_resp(self, 500, {"error": str(e)})

    # ── Nóminas ───────────────────────────────────────────────────────────────

    def _handle_get_nominas(self, params):
        token = _get_token(self)
        emp_id = self._verificar_token(token)
        if not emp_id:
            _json_resp(self, 401, {"error": "No autorizado"}); return

        anio = int(params.get("anio", [datetime.now().year])[0])
        try:
            nominas = self.db.obtener_nominas(empleado_id=emp_id, anio=anio)
            # Solo campos seguros
            campos = ["id","anio","mes","liquido","devengos_total",
                      "deducciones_total","estado","enviada_email"]
            nominas_safe = [{k: n.get(k) for k in campos} for n in nominas]
            _json_resp(self, 200, {"nominas": nominas_safe})
        except Exception as e:
            _json_resp(self, 500, {"error": str(e)})

    # ── Firma digital ─────────────────────────────────────────────────────────

    def _handle_firma(self):
        token = _get_token(self)
        emp_id = self._verificar_token(token)
        if not emp_id:
            _json_resp(self, 401, {"error": "No autorizado"}); return

        body = _read_body(self)
        doc_id = body.get("documento_id")
        if not doc_id:
            _json_resp(self, 400, {"error": "documento_id requerido"}); return

        try:
            import hashlib
            firma_data = f"{emp_id}:{doc_id}:{datetime.now().isoformat()}"
            firma_hash = hashlib.sha256(firma_data.encode()).hexdigest()

            self.db._create_api_movil()
            self.db.cursor.execute("""
                INSERT INTO laboral_firmas_digitales
                (empleado_id, documento_id, firma_hash, ip_origen, dispositivo)
                VALUES (?, ?, ?, ?, ?)
            """, (emp_id, doc_id, firma_hash,
                  self.client_address[0],
                  body.get("dispositivo", "")))
            self.db.conn.commit()
            _json_resp(self, 200, {
                "ok":          True,
                "firma_hash":  firma_hash,
                "fecha_firma": datetime.now().isoformat(),
            })
        except Exception as e:
            log.error("Error registrando firma: %s", e)
            _json_resp(self, 500, {"error": str(e)})

    # ── Helper token ──────────────────────────────────────────────────────────

    def _verificar_token(self, token: str) -> Optional[int]:
        if not token:
            return None
        try:
            self.db.cursor.execute(
                "SELECT empleado_id FROM laboral_api_tokens "
                "WHERE token=? AND activo=1", (token,))
            row = self.db.cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None


class ApiMovilServer:
    """
    Servidor HTTP local para la app móvil de fichaje.
    Corre en un hilo background sin bloquear la UI de PyQt.
    """

    def __init__(self, db_laboral=None, port: int = 8765, host: str = "0.0.0.0"):
        if db_laboral is None:
            from laboral.db_laboral import LaboralDB
            db_laboral = LaboralDB()

        self._db    = db_laboral
        self._port  = port
        self._host  = host
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

        # Inyectar la BD en el handler
        _RequestHandler.db = db_laboral

    def start(self) -> bool:
        """Inicia el servidor en un hilo background. Devuelve True si OK."""
        if self._server:
            log.warning("El servidor API ya está en ejecución")
            return False
        try:
            self._server = HTTPServer((self._host, self._port), _RequestHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="ApiMovilThread",
            )
            self._thread.start()
            log.info("API móvil iniciada en http://%s:%d", self._host, self._port)
            return True
        except Exception as e:
            log.error("Error iniciando API móvil: %s", e)
            self._server = None
            return False

    def stop(self) -> None:
        """Detiene el servidor."""
        if self._server:
            self._server.shutdown()
            self._server = None
            log.info("API móvil detenida")

    @property
    def url(self) -> str:
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
        return f"http://{ip}:{self._port}"

    @property
    def running(self) -> bool:
        return self._server is not None
