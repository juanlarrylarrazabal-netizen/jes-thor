# -*- coding: utf-8 -*-
"""
Cliente IMAP universal — JES⚡THOR V1
Correcciones:
- Solo marca como leídos los correos de los que se descargan archivos NUEVOS
- Los correos sin adjuntos o con archivos ya existentes NO se marcan como leídos
"""
from __future__ import annotations

import email
import email.header
import email.utils
import hashlib
import imaplib
import os
import re
import time
from email.message import Message
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from core.logging_config import get_logger
from core.exceptions import AuthError, IngestError, AttachmentError

log = get_logger("ingest.imap")


# ── Utilidades de fecha IMAP ──────────────────────────────────────────────────

_IMAP_MONTHS = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def _to_imap_date(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    date_str = date_str.strip()
    if re.match(r"\d{1,2}-[A-Za-z]{3}-\d{4}", date_str):
        return date_str
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        y, mo, d = m.groups()
        return f"{int(d)}-{_IMAP_MONTHS.get(mo, 'Jan')}-{y}"
    m = re.match(r"(\d{1,2})/(\d{2})/(\d{4})", date_str)
    if m:
        d, mo, y = m.groups()
        return f"{int(d)}-{_IMAP_MONTHS.get(mo.zfill(2), 'Jan')}-{y}"
    return None


# ── Utilidades de correo ──────────────────────────────────────────────────────

def decode_header_value(raw: str) -> str:
    parts = email.header.decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded).strip()


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:200] or "adjunto"


def detect_imap_host(email_address: str, known_hosts: dict) -> Tuple[str, int, bool]:
    domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
    if domain in known_hosts:
        h = known_hosts[domain]
        return h.get("host", ""), int(h.get("port", 993)), bool(h.get("ssl", True))
    return f"imap.{domain}", 993, True


# ── Funciones de matching ─────────────────────────────────────────────────────

def extract_from_addresses(msg: Message) -> List[str]:
    addresses: List[str] = []
    for header_name in ("From", "Sender", "Reply-To", "Return-Path"):
        raw = msg.get(header_name, "")
        if not raw:
            continue
        decoded = decode_header_value(raw)
        parsed = email.utils.getaddresses([decoded])
        for _name, addr in parsed:
            addr = addr.strip().lower()
            if addr and "@" in addr:
                addresses.append(addr)
                domain = addr.split("@")[-1]
                if domain not in addresses:
                    addresses.append(domain)
        full_lower = decoded.lower().strip()
        if full_lower:
            addresses.append(full_lower)
        if header_name == "From" and addresses:
            break
    return addresses


def match_subject(subject: str, subject_filters: List[str]) -> bool:
    if not subject_filters:
        return True
    subject_low = subject.lower().strip()
    return any(kw.lower().strip() in subject_low for kw in subject_filters if kw.strip())


def match_sender(sender_strings: List[str], sender_filters: List[str]) -> bool:
    if not sender_filters or not sender_strings:
        return False
    filters_low = [sf.lower().strip() for sf in sender_filters if sf.strip()]
    for sender_str in sender_strings:
        for sf in filters_low:
            if sf in sender_str:
                return True
    return False


# ── Clase principal ────────────────────────────────────────────────────────────

class ImapClient:
    """
    Descarga adjuntos de una cuenta de correo IMAP.
    Solo marca como leídos los correos de los que realmente se descargan archivos.
    """

    ACCEPTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
    SUBJECT_KEYWORDS    = ["factura", "invoice", "abono", "receipt", "albarán", "albaran"]

    SENDER_FILTERS: List[str] = []
    DEBUG_MODE: bool = False

    def __init__(
        self,
        email_addr:          str,
        password:            str,
        host:                str = "",
        port:                int = 993,
        use_ssl:             bool = True,
        folder:              str = "INBOX",
        known_hosts:         Optional[dict] = None,
        subject_keywords:    Optional[List[str]] = None,
        sender_filters:      Optional[List[str]] = None,
        debug_mode:          bool = False,
        accepted_extensions: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        self.email_addr = email_addr
        self.password   = password
        self.folder     = folder

        if not host:
            known = known_hosts or {}
            host, port, use_ssl = detect_imap_host(email_addr, known)

        self.host    = host
        self.port    = port
        self.use_ssl = use_ssl

        if subject_keywords is not None:
            self.SUBJECT_KEYWORDS = subject_keywords

        self.SENDER_FILTERS = [s.lower().strip() for s in (sender_filters or []) if s.strip()]
        self.DEBUG_MODE = bool(debug_mode)

        # Cargar extensiones permitidas desde BD
        if accepted_extensions is not None:
            self.ACCEPTED_EXTENSIONS = set(accepted_extensions)
        else:
            try:
                from database.manager import DatabaseManager
                db = DatabaseManager()
                exts_str = db.get_config_ui("descarga_extensiones", "pdf")
                exts = []
                if "pdf" in exts_str:
                    exts.extend([".pdf"])
                if "excel" in exts_str:
                    exts.extend([".xlsx", ".xls"])
                if exts:
                    self.ACCEPTED_EXTENSIONS = set(exts)
                    log.info(f"Extensiones permitidas: {self.ACCEPTED_EXTENSIONS}")
            except Exception as e:
                log.warning(f"No se pudieron cargar extensiones: {e}")

        self._conn: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None

        log.debug(
            "ImapClient creado: addr=%s host=%s sender_filters=%s debug=%s",
            email_addr, host, self.SENDER_FILTERS, self.DEBUG_MODE
        )

    # ── Conexión ──────────────────────────────────────────────────────────────

    def connect(self) -> None:
        try:
            log.info("Conectando a %s:%s (ssl=%s) como %s",
                     self.host, self.port, self.use_ssl, self.email_addr)
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port)
                self._conn.starttls()
            self._conn.login(self.email_addr, self.password)
            log.info("✅ Autenticación exitosa: %s", self.email_addr)
        except imaplib.IMAP4.error as exc:
            raise AuthError(f"No se pudo autenticar en {self.host}: {exc}") from exc
        except OSError as exc:
            raise IngestError(f"Error de red al conectar a {self.host}:{self.port}: {exc}") from exc

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "ImapClient":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ── Búsqueda y descarga ────────────────────────────────────────────────────

    def search_invoice_uids(
        self,
        date_from: Optional[str] = None,
        date_to:   Optional[str] = None,
        only_unseen: bool = False,
    ) -> List[bytes]:
        """
        Busca UIDs de mensajes.
        Usa readonly=True para no marcar como leídos automáticamente.
        """
        if not self._conn:
            raise IngestError("No conectado. Llama connect() primero.")
        
        log.info(f"Seleccionando carpeta: {self.folder} (modo readonly)")
        # IMPORTANTE: readonly=True para no marcar como leídos automáticamente
        result, data = self._conn.select(self.folder, readonly=True)
        if result != 'OK':
            log.error(f"Error al seleccionar carpeta {self.folder}: {result}")
            return []
        
        # Obtener número total de mensajes para diagnóstico
        try:
            _, data = self._conn.uid('search', None, 'ALL')
            total_msgs = len(data[0].split()) if data[0] else 0
            log.info(f"Total mensajes en carpeta: {total_msgs}")
        except Exception as e:
            log.error(f"Error contando mensajes: {e}")

        criteria = []
        if only_unseen:
            criteria.append("UNSEEN")
            log.info("Filtro: solo no leídos")
        
        if date_from:
            imap_date = _to_imap_date(date_from)
            if imap_date:
                criteria.append(f"SINCE {imap_date}")
                log.info(f"Filtro SINCE: {imap_date}")
        
        if date_to:
            try:
                date_obj = datetime.strptime(date_to, "%Y-%m-%d")
                next_day = date_obj + timedelta(days=1)
                imap_date = next_day.strftime("%d-%b-%Y")
                criteria.append(f"BEFORE {imap_date}")
                log.info(f"Filtro BEFORE: {imap_date}")
            except Exception as e:
                log.warning("No se pudo parsear date_to '%s' como %%Y-%%m-%%d, intentando formato IMAP: %s", date_to, e)
                imap_date = _to_imap_date(date_to)
                if imap_date:
                    criteria.append(f"BEFORE {imap_date}")
                    log.info(f"Filtro BEFORE: {imap_date}")

        # FIX-REMITENTE: si hay exactamente un filtro de remitente, añadirlo
        # como criterio FROM en la consulta IMAP para reducir mensajes descargados.
        # Si hay varios remitentes, el filtro se hace en post-proceso (IMAP no
        # soporta OR de FROM nativamente en todos los servidores).
        if len(self.SENDER_FILTERS) == 1:
            sender_imap = self.SENDER_FILTERS[0]
            criteria.append(f'FROM "{sender_imap}"')
            log.info("Filtro remitente activo (IMAP FROM): %s", sender_imap)
        elif self.SENDER_FILTERS:
            log.info(
                "Filtro remitente activo (post-proceso, %d remitentes): %s",
                len(self.SENDER_FILTERS), self.SENDER_FILTERS
            )

        search_criterion = " ".join(criteria) if criteria else "ALL"
        log.info(f"Criterio de búsqueda final: '{search_criterion}'")

        try:
            _, data = self._conn.uid("search", None, search_criterion)
            all_uids = data[0].split() if data[0] else []
            log.info(f"UIDs encontrados con criterio '{search_criterion}': {len(all_uids)}")
            
            if len(all_uids) == 0 and criteria:
                log.warning("No se encontraron mensajes con el criterio. Probando con ALL...")
                _, data_all = self._conn.uid("search", None, "ALL")
                total_all = len(data_all[0].split()) if data_all[0] else 0
                log.info(f"Total mensajes en carpeta (sin filtros): {total_all}")
                
        except Exception as e:
            log.error(f"Error en búsqueda IMAP: {e}")
            _, data = self._conn.uid("search", None, "ALL")
            all_uids = data[0].split() if data[0] else []
            log.info(f"Fallback a ALL: {len(all_uids)} UIDs")

        return all_uids

    def fetch_attachments(
        self,
        uids:           List[bytes],
        dest_dir:       Path,
        limit:          int = 50,
        already_hashes: Optional[set] = None,
        progress_cb:    Optional[Callable[[str], None]] = None,
        known_msg_ids:  Optional[set] = None,
    ) -> List[Dict]:
        """
        Descarga adjuntos de los UIDs dados, filtrando por extensiones permitidas.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        already_hashes = already_hashes or set()
        known_msg_ids  = known_msg_ids or set()
        results: List[Dict] = []
        processed = 0

        log.info(f"Iniciando fetch de {len(uids)} UIDs (límite: {limit})")

        for uid in uids:
            if processed >= limit:
                log.info(f"Límite de {limit} alcanzado")
                break
            try:
                items = self._fetch_one(uid, dest_dir, already_hashes, known_msg_ids)
                if items:
                    results.extend(items)
                    processed += 1
                    if progress_cb:
                        names = [i["nombre"] for i in items]
                        progress_cb(f"Descargado: {', '.join(names)}")
            except Exception as exc:
                log.warning("Error al procesar UID %s: %s", uid, exc)

        log.info("Descarga finalizada: %d adjuntos desde %s", len(results), self.email_addr)
        return results

    def _fetch_one(
        self,
        uid:            bytes,
        dest_dir:       Path,
        already_hashes: set,
        known_msg_ids:  Optional[set] = None,
    ) -> List[Dict]:
        """
        Descarga adjuntos de un único mensaje.
        Solo marca como leído si se descargaron archivos NUEVOS.
        """
        _, msg_data = self._conn.uid("fetch", uid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            log.warning(f"UID {uid}: sin datos")
            return []

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_header_value(msg.get("Subject", ""))
        date    = decode_header_value(msg.get("Date", ""))
        msg_id  = msg.get("Message-ID", "")

        sender_addrs   = extract_from_addresses(msg)
        sender_display = decode_header_value(msg.get("From", ""))

        ya_descargado = bool(known_msg_ids and msg_id and msg_id in known_msg_ids)

        m_subj   = match_subject(subject, self.SUBJECT_KEYWORDS)
        m_sender = match_sender(sender_addrs, self.SENDER_FILTERS)

        # FIX-REMITENTE: si hay filtros de remitente activos, un correo SOLO
        # se descarga si cumple el filtro de remitente (independientemente del asunto).
        # Sin filtro de remitente → descargar si coincide asunto.
        if self.SENDER_FILTERS:
            descarga = m_sender  # el remitente es requisito obligatorio
            if not m_sender:
                log.debug(
                    "Ignorado uid=%s: remitente '%s' no está en filtro %s",
                    uid.decode() if isinstance(uid, bytes) else uid,
                    sender_display[:60], self.SENDER_FILTERS
                )
        else:
            descarga = m_subj  # sin filtro de remitente: bastan palabras clave

        if self.DEBUG_MODE:
            motivo = []
            if m_subj:   motivo.append("asunto")
            if m_sender: motivo.append("remitente")
            log.info(
                "DEBUG IMAP | uid=%s | asunto='%s' | remitente='%s' | "
                "match_asunto=%s | match_remitente=%s | descarga=%s | "
                "ya_descargado=%s | motivo=%s",
                uid.decode() if isinstance(uid, bytes) else uid,
                subject[:80], sender_display[:80],
                m_subj, m_sender, descarga, ya_descargado,
                "+".join(motivo) if motivo else "—"
            )
        elif not descarga:
            log.debug(
                "Ignorado uid=%s | asunto='%s' | remitente='%s'",
                uid.decode() if isinstance(uid, bytes) else uid,
                subject[:60], sender_display[:40]
            )

        if not descarga:
            return []

        motivo_str = ("asunto+remitente" if (m_subj and m_sender)
                      else "asunto" if m_subj else "remitente")
        log.info(
            "Procesando uid=%s | motivo=%s | ya_descargado=%s | asunto='%s'",
            uid.decode() if isinstance(uid, bytes) else uid,
            motivo_str, ya_descargado, subject[:80]
        )

        results: List[Dict] = []
        nuevos_descargados = False

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                ct = part.get_content_type()
                if ct not in ("application/pdf", "image/jpeg", "image/png"):
                    continue

            filename = part.get_filename()
            if not filename:
                ct = part.get_content_type()
                ext_map = {
                    "application/pdf": ".pdf",
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                }
                ext = ext_map.get(ct, "")
                if not ext:
                    continue
                filename = f"adjunto_{uid.decode() if isinstance(uid, bytes) else uid}{ext}"
            else:
                filename = decode_header_value(filename)

            ext = Path(filename).suffix.lower()
            
            # Filtro por extensiones permitidas
            if ext not in self.ACCEPTED_EXTENSIONS:
                log.debug(f"Extensión no permitida: {filename}")
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            file_hash = hashlib.sha256(payload).hexdigest()
            log.debug(f"Procesando adjunto: {filename} (hash: {file_hash[:8]})")

            if file_hash in already_hashes:
                log.debug("Adjunto ya descargado en esta sesión (hash): %s", filename)
                ruta_existente = _find_existing_by_hash(dest_dir, file_hash)
                if ruta_existente:
                    results.append({
                        "ruta":            str(ruta_existente),
                        "nombre":          ruta_existente.name,
                        "remitente":       sender_display,
                        "asunto":          subject,
                        "fecha_correo":    date,
                        "message_id":      msg_id,
                        "hash":            file_hash,
                        "motivo_descarga": motivo_str,
                        "ya_descargado":   True,
                    })
                continue
            already_hashes.add(file_hash)

            safe_name = safe_filename(filename)
            dest_path = dest_dir / safe_name

            if dest_path.exists():
                try:
                    existing_hash = hashlib.sha256(dest_path.read_bytes()).hexdigest()
                    if existing_hash == file_hash:
                        log.info("Archivo ya existe (mismo hash): %s", dest_path.name)
                        results.append({
                            "ruta":            str(dest_path),
                            "nombre":          dest_path.name,
                            "remitente":       sender_display,
                            "asunto":          subject,
                            "fecha_correo":    date,
                            "message_id":      msg_id,
                            "hash":            file_hash,
                            "motivo_descarga": motivo_str,
                            "ya_descargado":   True,
                        })
                        continue
                except Exception:
                    pass
                counter = 1
                stem = Path(safe_name).stem
                while dest_path.exists():
                    dest_path = dest_dir / f"{stem}_{counter}{ext}"
                    counter += 1
                log.debug(f"Archivo existente, renombrado a: {dest_path.name}")

            dest_path.write_bytes(payload)
            log.info("✅ Adjunto NUEVO guardado: %s (%d bytes)", dest_path.name, len(payload))
            nuevos_descargados = True

            results.append({
                "ruta":            str(dest_path),
                "nombre":          dest_path.name,
                "remitente":       sender_display,
                "asunto":          subject,
                "fecha_correo":    date,
                "message_id":      msg_id,
                "hash":            file_hash,
                "motivo_descarga": motivo_str,
                "ya_descargado":   False,
            })

        # --- CAMBIO CLAVE: Solo marcar como leído si se descargaron archivos NUEVOS ---
        if nuevos_descargados:
            try:
                self._conn.uid("store", uid, "+FLAGS", "\\Seen")
                log.info(f"✅ Marcado como leído: {uid} (se descargaron archivos nuevos)")
            except Exception as e:
                log.warning(f"No se pudo marcar como leído {uid}: {e}")
        else:
            log.info(f"⏺️ Correo {uid} NO marcado como leído (sin archivos nuevos)")

        return results


def _find_existing_by_hash(directory: Path, file_hash: str) -> Optional[Path]:
    """Busca en el directorio un archivo con el hash dado."""
    try:
        for f in directory.iterdir():
            if f.is_file():
                try:
                    h = hashlib.sha256(f.read_bytes()).hexdigest()
                    if h == file_hash:
                        return f
                except Exception:
                    continue
    except Exception:
        pass
    return None


# ── Gestor multi-cuenta ────────────────────────────────────────────────────────

class MultiAccountDownloader:
    """Descarga adjuntos de múltiples cuentas IMAP en secuencia."""

    def __init__(self, accounts: List[Dict], config: Optional[dict] = None) -> None:
        self.accounts = accounts
        self.config   = config or {}
        self.total_messages_checked = 0

    def download_all(
        self,
        dest_dir:    Path,
        limit:       int = 50,
        progress_cb: Optional[Callable[[str], None]] = None,
        date_from:   Optional[str] = None,
        date_to:     Optional[str] = None,
        only_unseen: bool = False,
    ) -> List[Dict]:
        """
        Descarga de todas las cuentas.
        """
        all_results: List[Dict] = []
        
        log.info("=" * 60)
        log.info("INICIANDO DESCARGA MULTI-CUENTA")
        log.info(f"Parámetros: date_from={date_from}, date_to={date_to}, only_unseen={only_unseen}, limit={limit}")
        log.info(f"Cuentas a procesar: {len(self.accounts)}")
        log.info("=" * 60)
        
        known_hosts  = self.config.get("known_hosts", {})
        subject_kw   = self.config.get("subject_keywords", ImapClient.SUBJECT_KEYWORDS)
        sender_flt   = self.config.get("sender_filters", [])
        debug_mode   = bool(self.config.get("debug_mode", False))
        max_retries  = int(self.config.get("max_retries", 3))
        backoff      = float(self.config.get("retry_backoff_s", 2.0))

        # Cargar extensiones permitidas
        try:
            from database.manager import DatabaseManager
            db = DatabaseManager()
            exts_str = db.get_config_ui("descarga_extensiones", "pdf")
            accepted_ext = []
            if "pdf" in exts_str:
                accepted_ext.extend([".pdf"])
            if "excel" in exts_str:
                accepted_ext.extend([".xlsx", ".xls"])
            log.info(f"Extensiones permitidas desde configuración: {accepted_ext}")
        except Exception:
            accepted_ext = [".pdf"]
            log.warning("No se pudieron cargar extensiones, usando solo PDF")

        # Obtener mensajes ya conocidos
        try:
            from database.manager import DatabaseManager
            db = DatabaseManager()
            known_msg_ids = set()
            for row in db.obtener_historial_correos(limit=5000):
                if row.get("message_id"):
                    known_msg_ids.add(row["message_id"])
            log.info(f"Mensajes ya conocidos en BD: {len(known_msg_ids)}")
        except Exception:
            db = None
            known_msg_ids = set()
            log.warning("No se pudo obtener historial de mensajes")

        # Conjunto de Message-IDs ya descargados en ESTA sesión (multicuenta)
        # Evita descargar el mismo correo de varias cuentas (p.ej. alias/reenvíos)
        session_msg_ids: set = set()

        for idx, acc in enumerate(self.accounts, 1):
            email_addr = acc.get("email", "")
            password   = acc.get("password", "")
            host       = acc.get("host", "")
            port       = int(acc.get("port", 993))
            use_ssl    = bool(acc.get("use_ssl", True))
            folder     = acc.get("folder", "INBOX")

            log.info(f"[{idx}/{len(self.accounts)}] Procesando cuenta: {email_addr}")

            if not email_addr or not password:
                log.warning(f"Cuenta {email_addr} sin email/contraseña, saltando.")
                continue

            client = ImapClient(
                email_addr=email_addr,
                password=password,
                host=host,
                port=port,
                use_ssl=use_ssl,
                folder=folder,
                known_hosts=known_hosts,
                subject_keywords=subject_kw,
                sender_filters=sender_flt,
                debug_mode=debug_mode,
                accepted_extensions=accepted_ext,
            )

            last_exc: Optional[Exception] = None
            for attempt in range(1, max_retries + 1):
                try:
                    with client:
                        uids = client.search_invoice_uids(
                            date_from=date_from,
                            date_to=date_to,
                            only_unseen=only_unseen,
                        )
                        self.total_messages_checked += len(uids)
                        log.info(f"Cuenta {email_addr}: {len(uids)} UIDs encontrados")
                        
                        if uids:
                            # Combinar known_msg_ids de BD + session_msg_ids para dedup multicuenta
                            combined_known = known_msg_ids | session_msg_ids
                            results = client.fetch_attachments(
                                uids[:limit], dest_dir, limit,
                                progress_cb=progress_cb,
                                known_msg_ids=combined_known,
                            )
                            log.info(f"Cuenta {email_addr}: {len(results)} adjuntos procesados")

                            if db and results:
                                for item in results:
                                    mid = item.get("message_id", "")
                                    if mid and mid not in known_msg_ids:
                                        db.registrar_mensaje_correo(
                                            message_id=mid,
                                            cuenta=email_addr,
                                            asunto=item.get("asunto", ""),
                                            remitente=item.get("remitente", ""),
                                            fecha_correo=item.get("fecha_correo", ""),
                                            num_adjuntos=1,
                                        )
                                        known_msg_ids.add(mid)
                                    # Registrar en dedup de sesión para las siguientes cuentas
                                    if mid:
                                        session_msg_ids.add(mid)
                            all_results.extend(results)
                        else:
                            log.info(f"Cuenta {email_addr}: no hay UIDs para procesar")
                            
                    last_exc = None
                    break
                    
                except (AuthError, IngestError) as exc:
                    last_exc = exc
                    wait = backoff ** attempt
                    log.warning(
                        "Intento %d/%d falló para %s: %s. Esperando %.1fs",
                        attempt, max_retries, email_addr, exc, wait
                    )
                    if attempt < max_retries:
                        time.sleep(wait)

            if last_exc:
                log.error("❌ Todos los intentos fallaron para %s: %s", email_addr, last_exc)

        log.info("=" * 60)
        log.info(f"DESCARGA COMPLETADA: {len(all_results)} adjuntos totales")
        log.info("=" * 60)
        
        return all_results