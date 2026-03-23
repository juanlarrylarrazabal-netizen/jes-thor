# -*- coding: utf-8 -*-
"""
Procesador de nóminas.
Flujo:
  1. Recibe un PDF (puede contener N nóminas, una por empleado)
  2. Extrae texto por página con el OCR existente
  3. Detecta a qué empleado corresponde cada página
  4. Divide el PDF en nóminas individuales
  5. Guarda en carpeta del empleado: Empleados/Apellido_Nombre/Nominas/YYYY/MM_Mes.pdf
  6. Registra en BD
  7. Opcionalmente envía por email

Reutiliza:
  - ocr.pipeline.extract_text / ocr_pdf
  - ocr.field_extractor (para fechas e importes)
  - storage.filesystem.safe_name
  - core.logging_config
"""
from __future__ import annotations
import re
import shutil
import smtplib
import ssl
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from core.logging_config import get_logger
from storage.filesystem import safe_name

log = get_logger("laboral.nominas")

_MESES_ES = {
    1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril",
    5:"Mayo", 6:"Junio", 7:"Julio", 8:"Agosto",
    9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"
}


# ── Extracción de texto por página ─────────────────────────────────────────────

def _texto_pagina(pdf_path: str, page_index: int,
                  tesseract_path: str = None, languages: list = None) -> str:
    """Extrae texto de una sola página reutilizando el pipeline OCR existente."""
    try:
        from ocr.pipeline import extract_text
        text, _ = extract_text(
            pdf_path,
            tesseract_path=tesseract_path,
            languages=languages or ["spa"],
            ocr_threshold=50,
            ocr_enabled=True,
            page_index=page_index,
        )
        return text or ""
    except Exception as e:
        log.warning("Error extrayendo texto página %d: %s", page_index, e)
        return ""


# ── Detección de empleado en texto ─────────────────────────────────────────────

def _detectar_empleado_en_texto(texto: str, empleados: List[Dict]) -> Optional[Dict]:
    """
    Busca en el texto de la página el nombre de algún empleado de la BD.
    Devuelve el empleado encontrado o None.
    Estrategia: comparación flexible por apellidos (más únicos que nombre).
    """
    texto_norm = texto.lower()

    # Orden: primero por apellidos (más específicos), luego nombre completo
    candidatos = []
    for emp in empleados:
        apellidos = (emp.get("apellidos") or "").lower()
        nombre    = (emp.get("nombre") or "").lower()
        # Score: cuántas palabras del apellido aparecen en el texto
        palabras_apellido = [p for p in apellidos.split() if len(p) > 2]
        score = sum(1 for p in palabras_apellido if p in texto_norm)
        if score > 0:
            candidatos.append((score, len(palabras_apellido), emp))

    if not candidatos:
        return None

    # El candidato con más palabras del apellido coincidentes
    candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
    mejor_score, total_palabras, emp = candidatos[0]

    # Solo aceptar si coincide al menos la mitad de las palabras del apellido
    if total_palabras > 0 and mejor_score / total_palabras >= 0.5:
        log.info("Empleado detectado: %s %s (score=%d/%d)",
                 emp.get('nombre'), emp.get('apellidos'), mejor_score, total_palabras)
        return emp

    return None


def _detectar_anio_mes(texto: str) -> Tuple[int, int]:
    """Extrae año y mes del texto de la nómina."""
    from ocr.field_extractor import _parse_date
    fecha = _parse_date(texto)
    if fecha:
        return fecha.year, fecha.month
    # Fallback: mes actual
    hoy = datetime.now()
    return hoy.year, hoy.month


def _detectar_importes(texto: str) -> Dict[str, float]:
    """Extrae importes de la nómina usando el extractor existente."""
    try:
        from ocr.field_extractor import extract_fields
        fields = extract_fields(texto)
        return {
            "liquido":   fields.total_amount or 0.0,
            "base":      fields.base_amount  or 0.0,
            "iva":       fields.vat_amount   or 0.0,
        }
    except Exception:
        return {"liquido": 0.0, "base": 0.0, "iva": 0.0}


# ── Split de PDF por páginas ───────────────────────────────────────────────────

def _extraer_paginas_pdf(pdf_path: str, paginas: List[int],
                          destino: str) -> bool:
    """Extrae páginas específicas de un PDF y las guarda en destino."""
    try:
        import fitz
        doc_orig = fitz.open(pdf_path)
        doc_nuevo = fitz.open()
        for p in paginas:
            if 0 <= p < len(doc_orig):
                doc_nuevo.insert_pdf(doc_orig, from_page=p, to_page=p)
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        doc_nuevo.save(destino)
        doc_nuevo.close()
        doc_orig.close()
        return True
    except Exception as e:
        log.error("Error extrayendo páginas %s del PDF: %s", paginas, e)
        return False


# ── Ruta destino para nómina ───────────────────────────────────────────────────

def _ruta_nomina(carpeta_base: str, empleado: Dict,
                 anio: int, mes: int) -> Path:
    """
    Genera la ruta de destino:
    {carpeta_base}/Empleados/{Apellidos_Nombre}/Nominas/{anio}/{MM_Mes}.pdf
    """
    apellidos = safe_name(empleado.get("apellidos", "Empleado"))
    nombre    = safe_name(empleado.get("nombre", ""))
    carpeta_emp = f"{apellidos}_{nombre}".strip("_")
    mes_str = f"{mes:02d}_{_MESES_ES.get(mes, str(mes))}"
    return (Path(carpeta_base) / "Empleados" / carpeta_emp /
            "Nominas" / str(anio) / f"{mes_str}.pdf")


# ── Envío de email ─────────────────────────────────────────────────────────────

def _enviar_nomina_email(empleado: Dict, pdf_path: str,
                          anio: int, mes: int, smtp_cfg: dict) -> bool:
    """Envía la nómina por email al empleado usando la configuración SMTP de la BD."""
    email_dest = empleado.get("email", "")
    if not email_dest:
        log.warning("Empleado %s %s sin email → no se envía nómina",
                    empleado.get('nombre'), empleado.get('apellidos'))
        return False

    try:
        smtp_host = smtp_cfg.get("host", "")
        smtp_port = int(smtp_cfg.get("port", 587))
        smtp_user = smtp_cfg.get("username", "")
        smtp_pass = smtp_cfg.get("password", "")
        from_addr = smtp_cfg.get("from_addr", smtp_user)

        mes_nombre = _MESES_ES.get(mes, str(mes))
        asunto = f"Nómina {mes_nombre} {anio} — {empleado.get('nombre')} {empleado.get('apellidos')}"

        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = email_dest
        msg["Subject"] = asunto

        cuerpo = (
            f"Estimado/a {empleado.get('nombre')},\n\n"
            f"Adjuntamos su nómina correspondiente a {mes_nombre} de {anio}.\n\n"
            "Un saludo,\nDepartamento de RRHH"
        )
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with open(pdf_path, "rb") as fh:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment",
                        filename=Path(pdf_path).name)
        msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, email_dest, msg.as_string())

        log.info("Nómina enviada a %s (%s)", email_dest,
                 empleado.get('apellidos'))
        return True

    except Exception as e:
        log.error("Error enviando nómina a %s: %s",
                  empleado.get('email'), e)
        return False


# ── Procesador principal ───────────────────────────────────────────────────────

class ProcesadorNominas:
    """
    Procesa un PDF de nóminas (uno o varios empleados).
    Divide, clasifica, guarda y opcionalmente envía por email.
    """

    def __init__(self, db_laboral=None, carpeta_base: str = None,
                 tesseract_path: str = None, languages: list = None,
                 enviar_email: bool = False, progress_cb=None):
        if db_laboral is None:
            from laboral.db_laboral import LaboralDB
            db_laboral = LaboralDB()
        self.db           = db_laboral
        self.tesseract    = tesseract_path
        self.languages    = languages or ["spa"]
        self.enviar_email = enviar_email
        self.progress_cb  = progress_cb or (lambda msg: None)

        if carpeta_base is None:
            try:
                carpeta_base = self.db._db.get_config_ui(
                    "carpeta_empleados", "./Empleados")
            except Exception:
                carpeta_base = "./Empleados"
        self.carpeta_base = carpeta_base

    def _smtp_config(self) -> dict:
        """Lee config SMTP desde la BD (tabla smtp_config existente)."""
        try:
            self.db.cursor.execute("SELECT * FROM smtp_config LIMIT 1")
            cols = [d[0] for d in self.db.cursor.description]
            r = self.db.cursor.fetchone()
            return dict(zip(cols, r)) if r else {}
        except Exception:
            return {}

    def procesar_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Procesa un PDF completo de nóminas.
        Devuelve lista de resultados por página/empleado.
        """
        resultados = []
        empleados  = self.db.obtener_empleados(solo_activos=True)

        if not empleados:
            log.warning("No hay empleados activos en la BD laboral")
            return []

        try:
            import fitz
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
        except Exception as e:
            log.error("No se pudo abrir el PDF de nóminas: %s", e)
            return []

        self.progress_cb(f"PDF de nóminas: {total_pages} páginas")

        # Agrupar páginas por empleado
        grupos: Dict[int, List[int]] = {}   # empleado_id → [página, ...]
        paginas_sin_empleado = []

        for page_idx in range(total_pages):
            self.progress_cb(f"Analizando página {page_idx + 1}/{total_pages}...")
            texto = _texto_pagina(pdf_path, page_idx,
                                  self.tesseract, self.languages)
            emp = _detectar_empleado_en_texto(texto, empleados)
            if emp:
                grupos.setdefault(emp["id"], []).append(page_idx)
                # Detectar año/mes de la primera página del grupo
                if emp["id"] not in getattr(self, "_anio_mes_cache", {}):
                    if not hasattr(self, "_anio_mes_cache"):
                        self._anio_mes_cache = {}
                    anio, mes = _detectar_anio_mes(texto)
                    importes  = _detectar_importes(texto)
                    self._anio_mes_cache[emp["id"]] = (anio, mes, importes)
            else:
                paginas_sin_empleado.append(page_idx)
                log.debug("Página %d: empleado no detectado", page_idx + 1)

        if paginas_sin_empleado:
            log.warning("Páginas sin empleado detectado: %s", paginas_sin_empleado)

        # Procesar cada grupo
        smtp_cfg = self._smtp_config() if self.enviar_email else {}

        for emp_id, paginas in grupos.items():
            emp = next((e for e in empleados if e["id"] == emp_id), None)
            if not emp:
                continue

            anio, mes, importes = getattr(
                self, "_anio_mes_cache", {}).get(emp_id, (datetime.now().year, datetime.now().month, {}))

            ruta_destino = str(_ruta_nomina(self.carpeta_base, emp, anio, mes))
            self.progress_cb(f"Guardando nómina de {emp['nombre']} {emp['apellidos']}...")

            ok = _extraer_paginas_pdf(pdf_path, paginas, ruta_destino)

            if ok:
                from storage.filesystem import compute_sha256
                pdf_hash = compute_sha256(ruta_destino)

                # Registrar en BD
                nomina_id = self.db.insertar_nomina({
                    "empleado_id": emp_id,
                    "anio":        anio,
                    "mes":         mes,
                    "liquido":     importes.get("liquido", 0),
                    "salario_base": importes.get("base", 0),
                    "pdf_path":    ruta_destino,
                    "pdf_hash":    pdf_hash,
                    "origen_pdf":  str(pdf_path),
                    "estado":      "procesada",
                })

                # Registrar en portal de documentos
                self.db.insertar_documento_portal({
                    "empleado_id": emp_id,
                    "tipo":       "nomina",
                    "titulo":     f"Nómina {_MESES_ES.get(mes, mes)} {anio}",
                    "ruta":       ruta_destino,
                })

                # Envío por email
                enviado = False
                if self.enviar_email and smtp_cfg:
                    enviado = _enviar_nomina_email(emp, ruta_destino,
                                                    anio, mes, smtp_cfg)
                    if enviado:
                        self.db.marcar_nomina_enviada(nomina_id)

                resultado = {
                    "empleado":   f"{emp['nombre']} {emp['apellidos']}",
                    "anio":       anio,
                    "mes":        mes,
                    "pdf":        ruta_destino,
                    "paginas":    paginas,
                    "liquido":    importes.get("liquido", 0),
                    "enviado":    enviado,
                    "nomina_id":  nomina_id,
                }
                resultados.append(resultado)
                log.info("Nómina procesada: %s %s → %s",
                         emp['nombre'], emp['apellidos'], ruta_destino)
            else:
                resultados.append({
                    "empleado": f"{emp['nombre']} {emp['apellidos']}",
                    "error":    "No se pudo guardar el PDF",
                    "paginas":  paginas,
                })

        # Limpiar caché
        if hasattr(self, "_anio_mes_cache"):
            del self._anio_mes_cache

        self.progress_cb(f"Procesamiento completado: {len(resultados)} nóminas")
        return resultados
