# -*- coding: utf-8 -*-
"""
Pipeline de clasificación completo.
CORREGIDO: Los valores de plantilla SOBREESCRIBEN a los del OCR
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from core.logging_config import get_logger, set_invoice_context, clear_invoice_context
from core.models import Invoice, InvoiceStatus, ClassificationResult
from core.exceptions import (
    PDFReadError, OCRError, WatermarkError, AlreadyStampedError, StorageError
)

log = get_logger("classify")


class InvoiceClassifier:
    def __init__(self, db=None, config=None) -> None:
        from database.manager import DatabaseManager
        self.db  = db or DatabaseManager()
        self._config = config
        self._engine = None

    @property
    def cfg(self):
        if self._config is None:
            from core.config_loader import get_config
            self._config = get_config()
        return self._config

    def invalidate_engine(self) -> None:
        """
        Fuerza la recarga del motor de reglas en el próximo process().
        Llamar tras crear o modificar reglas desde el visor para que
        el clasificador las vea sin necesidad de reiniciar la app.
        """
        self._engine = None
        log.info("Motor de reglas invalidado — se recargará en el próximo proceso")

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
            
        try:
            from rules.engine import RuleEngine
            vendors = self.db.obtener_todos_proveedores()
            rules = self.db.obtener_todas_reglas_con_proveedor()
            self._engine = RuleEngine(vendors, rules, self.db)
            log.info("Motor de reglas inicializado: %d proveedores, %d reglas", 
                     len(vendors), len(rules))
            return self._engine
        except Exception as e:
            log.error("Error inicializando motor: %s", e)
            self._engine = RuleEngine([], [], self.db)
            return self._engine

    def process(self, invoice: Invoice) -> Invoice:
        set_invoice_context(invoice.file_name or Path(invoice.file_path).name)
        try:
            invoice.numero_factura_manual = getattr(invoice, "numero_factura_manual", "")
            invoice.serie_manual = getattr(invoice, "serie_manual", "")
            invoice.tipo_factura_manual = getattr(invoice, "tipo_factura_manual", "")
            invoice.categoria_manual = getattr(invoice, "categoria_manual", "")
            invoice.cuenta_gasto_manual = getattr(invoice, "cuenta_gasto_manual", "")
            invoice.subcuenta_gasto_manual = getattr(invoice, "subcuenta_gasto_manual", "")
            invoice.cuenta_proveedor_manual = getattr(invoice, "cuenta_proveedor_manual", "")
            invoice.subcuenta_proveedor_manual = getattr(invoice, "subcuenta_proveedor_manual", "")
            invoice.numero_factura_ia = getattr(invoice, "numero_factura_ia", "")
            
            return self._process_inner(invoice)
        except Exception as exc:
            invoice.add_error(str(exc))
            log.error("Error procesando %s: %s", invoice.file_name, exc, exc_info=True)
            return invoice
        finally:
            clear_invoice_context()

    def _process_inner(self, invoice: Invoice) -> Invoice:
        from storage.filesystem import compute_sha256

        # 1. Hash y deduplicación
        if not invoice.file_hash:
            invoice.file_hash = compute_sha256(invoice.file_path)

        if self.db.factura_ya_procesada(invoice.file_hash):
            info = self.db.obtener_info_factura_procesada(invoice.file_hash)
            invoice.status = InvoiceStatus.DUPLICATE
            if info:
                invoice.final_path = (info.get("ruta_archivo_final") or
                                      info.get("nombre_archivo") or "")
            log.info("Factura duplicada: %s", invoice.file_name)
            return invoice

        # 2. Extraer texto
        from ocr.pipeline import extract_text
        text, method = extract_text(
            invoice.file_path,
            tesseract_path=self.cfg.tesseract_path,
            languages=self.cfg.ocr_languages,
            ocr_threshold=self.cfg.ocr_fallback_threshold,
            ocr_enabled=self.cfg.ocr_enabled,
        )
        invoice.fields.raw_text = text
        invoice.fields.extraction_method = method

        # 3. Extraer campos (OCR automático)
        from ocr.field_extractor import extract_fields
        fields = extract_fields(text)
        fields.raw_text = text
        fields.extraction_method = method

        # ── RESTAURAR VALORES MANUALES DEL USUARIO (prioridad máxima) ────────
        # El visor puede haber fijado valores antes de llamar a process().
        # Guardamos esos valores ANTES de sobrescribir invoice.fields con el OCR,
        # y los restauramos inmediatamente después.
        # Principio: USUARIO > REGLAS > OCR — nunca al revés.
        _pre_manual = {
            "base_amount":      getattr(invoice.fields, "base_amount",      None),
            "vat_amount":       getattr(invoice.fields, "vat_amount",       None),
            "vat_pct":          getattr(invoice.fields, "vat_pct",          None),
            "total_amount":     getattr(invoice.fields, "total_amount",     None),
            "cif_nif":          getattr(invoice.fields, "cif_nif",          None),
            "issue_date":       getattr(invoice.fields, "issue_date",       None),
            "retention_pct":    getattr(invoice.fields, "retention_pct",    None),
            "retention_amount": getattr(invoice.fields, "retention_amount", None),
            "tipo_iva":         getattr(invoice.fields, "tipo_iva",         None),
            "reparto_cuentas":  getattr(invoice.fields, "reparto_cuentas",  None),
        }
        # Indicadores de si cada campo fue fijado manualmente
        _has_manual_base = bool(getattr(invoice, "_manual_base_amount", None))
        _has_manual_iva  = bool(getattr(invoice, "_manual_vat_amount",  None))
        _has_manual_tot  = bool(getattr(invoice, "_manual_total_amount", None))
        _has_manual_cif  = bool(_pre_manual["cif_nif"])
        _has_manual_date = bool(_pre_manual["issue_date"])
        _has_manual_ret  = bool(_pre_manual["retention_pct"] or _pre_manual["retention_amount"])
        _has_manual_tipo = bool(getattr(invoice, "_tipo_iva_manual", None))
        _has_manual_rep  = bool(_pre_manual["reparto_cuentas"])

        invoice.fields = fields

        # Restaurar campos manuales que OCR no debe sobrescribir
        if _has_manual_base:
            invoice.fields.base_amount      = _pre_manual["base_amount"]
        if _has_manual_iva:
            invoice.fields.vat_amount       = _pre_manual["vat_amount"]
            if _pre_manual["vat_pct"] is not None:
                invoice.fields.vat_pct      = _pre_manual["vat_pct"]
        if _has_manual_tot:
            invoice.fields.total_amount     = _pre_manual["total_amount"]
        if _has_manual_cif:
            invoice.fields.cif_nif          = _pre_manual["cif_nif"]
        if _has_manual_date:
            invoice.fields.issue_date       = _pre_manual["issue_date"]
        if _has_manual_ret:
            invoice.fields.retention_pct    = _pre_manual["retention_pct"]
            invoice.fields.retention_amount = _pre_manual["retention_amount"]
        if _has_manual_tipo:
            invoice.fields.tipo_iva         = _pre_manual["tipo_iva"]
            invoice.fields.vat_pct          = _pre_manual["vat_pct"]
        if _has_manual_rep:
            invoice.fields.reparto_cuentas  = _pre_manual["reparto_cuentas"]

        log.debug(
            "Post-OCR restore: base=%s iva=%s tot=%s cif=%s date=%s tipo_iva=%s",
            invoice.fields.base_amount, invoice.fields.vat_amount,
            invoice.fields.total_amount, invoice.fields.cif_nif,
            invoice.fields.issue_date, invoice.fields.tipo_iva
        )
        # ─────────────────────────────────────────────────────────────────────

        # 4. Validación multipágina
        try:
            import fitz as _fitz
            _doc_check = _fitz.open(invoice.file_path)
            _num_pages = len(_doc_check)
            _doc_check.close()
        except Exception:
            _num_pages = 1

        if _num_pages > 1:
            _enriched, _issues, _needs_manual = validate_and_enrich_fields(
                pdf_path=invoice.file_path,
                fields=fields,
                tesseract_path=self.cfg.tesseract_path,
                languages=self.cfg.ocr_languages,
                ocr_enabled=self.cfg.ocr_enabled,
            )
            # Restaurar manuales tras enriquecimiento multipágina
            if _has_manual_base and _pre_manual["base_amount"]:
                _enriched.base_amount   = _pre_manual["base_amount"]
            if _has_manual_iva and _pre_manual["vat_amount"]:
                _enriched.vat_amount    = _pre_manual["vat_amount"]
            if _has_manual_tot and _pre_manual["total_amount"]:
                _enriched.total_amount  = _pre_manual["total_amount"]
            invoice.fields = _enriched
            fields = _enriched
            if _needs_manual:
                invoice.status = InvoiceStatus.PENDING
                invoice._multipage_issues = _issues
                log.info("Factura multipágina necesita revisión")
                return invoice

        # 5. Clasificar (obtener regla)
        engine = self._get_engine()
        _cif_log = getattr(fields, "cif_nif", "") or ""
        log.info("CIF detectado: %r", _cif_log)
        result = engine.classify(text, fields)
        log.info("Regla aplicada: %r (fallback=%s, needs_manual=%s)",
                 getattr(result, "nombre_regla", "?"),
                 result.is_fallback, result.needs_manual)

        # 6. APLICAR PLANTILLA OCR (SOBREESCRIBE LOS VALORES DEL OCR)
        es_rect = False
        if result and result.vendor and not result.is_fallback and not result.needs_manual:
            try:
                from ocr.template_applier import extraer_campos_con_plantilla
                log.info(f"Buscando plantilla para regla: {result.nombre_regla}")
                
                campos_plantilla = extraer_campos_con_plantilla(
                    invoice.file_path,
                    result.vendor.id,
                    nombre_regla=result.nombre_regla,
                    db=self.db
                )
                
                if campos_plantilla:
                    # Número de factura
                    if campos_plantilla.get("numero_factura") and not invoice.numero_factura_manual:
                        invoice.fields.invoice_number = campos_plantilla["numero_factura"]
                        log.info(f"Nº desde plantilla: {campos_plantilla['numero_factura']}")
                    
                    # Posiciones de marca de agua desde la plantilla
                    if campos_plantilla.get("wm_datos"):
                        invoice._wm_pos_datos = tuple(campos_plantilla["wm_datos"])
                    if campos_plantilla.get("wm_serie"):
                        invoice._wm_pos_serie = tuple(campos_plantilla["wm_serie"])

                    from core.utils import parse_es_float_safe
                    # ── BUG-FIX: respetar valores manuales del visor ──────────
                    # Si el usuario marcó zonas manualmente en el visor, esos
                    # valores llegan como _manual_*. La plantilla solo aplica
                    # si NO hay valor manual fijado explícitamente.
                    _manual_base = getattr(invoice, "_manual_base_amount", None)
                    _manual_iva  = getattr(invoice, "_manual_vat_amount",  None)
                    _manual_tot  = getattr(invoice, "_manual_total_amount", None)

                    if campos_plantilla.get("base_imponible") and not _manual_base:
                        v = parse_es_float_safe(campos_plantilla["base_imponible"])
                        if v != 0.0:
                            invoice.fields.base_amount = v
                            log.info(f"Base desde plantilla: {v}")
                    elif _manual_base:
                        log.info(f"Base MANUAL respetada: {_manual_base} (plantilla ignorada)")

                    if campos_plantilla.get("iva") and not _manual_iva:
                        v = parse_es_float_safe(campos_plantilla["iva"])
                        if v != 0.0:
                            invoice.fields.vat_amount = v
                            log.info(f"IVA desde plantilla: {v}")
                    elif _manual_iva:
                        log.info(f"IVA MANUAL respetado: {_manual_iva} (plantilla ignorada)")

                    if campos_plantilla.get("total") and not _manual_tot:
                        v = parse_es_float_safe(campos_plantilla["total"])
                        if v != 0.0:
                            invoice.fields.total_amount = v
                            log.info(f"Total desde plantilla: {v}")
                    elif _manual_tot:
                        log.info(f"Total MANUAL respetado: {_manual_tot} (plantilla ignorada)")
                    # ─────────────────────────────────────────────────────────
                    
                    # Flag rectificativa
                    if "es_rectificativa" in campos_plantilla:
                        es_rect = campos_plantilla["es_rectificativa"]
                        log.info(f"Flag rectificativa desde plantilla: {es_rect}")

                    # ── Modo Gestoría ─────────────────────────────────────────
                    # Si la plantilla fue entrenada en modo gestoría, el IVA
                    # guardado es solo el de los honorarios.
                    # Base real = Total - IVA_honorarios
                    # Usar iva_gestoria (valor guardado) o el IVA re-OCR de la zona
                    if campos_plantilla.get("es_gestoria"):
                        _iva_gest_raw = (campos_plantilla.get("iva_gestoria") or
                                         campos_plantilla.get("iva") or "")
                        _iva_gest = parse_es_float_safe(_iva_gest_raw)
                        _tot_gest = invoice.fields.total_amount or 0.0
                        if _iva_gest > 0 and _tot_gest > 0:
                            _base_gest = round(_tot_gest - _iva_gest, 2)
                            invoice.fields.vat_amount   = _iva_gest
                            invoice.fields.base_amount  = _base_gest
                            log.info("Gestoría (plantilla): base=%s (total=%s - iva=%s)",
                                     _base_gest, _tot_gest, _iva_gest)
                    # ─────────────────────────────────────────────────────────
                        
            except Exception as e:
                log.error(f"Error aplicando plantilla: {e}")

        # 7. Si es fallback o necesita manual, marcar PENDING
        if result.is_fallback:
            invoice.status = InvoiceStatus.PENDING
            log.info("Sin regla para este proveedor → PENDING")
            return invoice
            
        if result.needs_manual:
            invoice.status = InvoiceStatus.PENDING
            log.info("Necesita revisión manual → PENDING")
            return invoice

        # 8. Rectificativa: solo desde la plantilla OCR o la regla, nunca por detección automática.
        # La detección automática por texto o importe negativo causaba falsos positivos.

        # 9. Watermark y archivado
        from watermark.stamper import stamp_pdf
        from core.exceptions import AlreadyStampedError

        inv_date = fields.issue_date or datetime.now()

        from storage.filesystem import (
            build_invoice_filename, resolve_dest_path, avoid_collision, safe_name
        )
        
        # Obtener serie por defecto
        _serie = ""
        try:
            from database.manager import DatabaseManager as _DM
            _serie = _DM().get_config_ui("serie_default", "") or ""
        except Exception:
            pass

        # PRECEDENCIA DEL NÚMERO DE FACTURA
        num_manual = invoice.numero_factura_manual or ""
        num_regla  = getattr(result, "numero_factura_regla",  "") or ""
        if not num_regla and hasattr(result, "set_numero_factura"):
            num_regla = result.set_numero_factura or ""
        num_ia     = invoice.numero_factura_ia or ""
        num_ocr    = invoice.fields.invoice_number or ""
        
        log.info(f"VALORES - manual:'{num_manual}', regla:'{num_regla}', ia:'{num_ia}', ocr:'{num_ocr}'")
        
        inv_num_final = ""
        origen_num = "ninguno"
        
        if num_manual and num_manual.strip():
            inv_num_final = num_manual
            origen_num = "manual"
            log.info(f"Usando número MANUAL: '{inv_num_final}'")
        elif num_regla and num_regla.strip():
            inv_num_final = num_regla
            origen_num = "regla"
        elif num_ia and num_ia.strip():
            inv_num_final = num_ia
            origen_num = "ia"
        elif num_ocr and num_ocr.strip():
            inv_num_final = num_ocr
            origen_num = "ocr"
        else:
            inv_num_final = "S-N"
            origen_num = "default"

        log.info(f"NUM_FINAL_USADO={inv_num_final} | origen={origen_num}")

        # Construir nombre de archivo: nombre_proveedor + nro_factura
        _vendor_name_safe = safe_name(result.vendor.name or result.vendor_code or "PRV")
        filename = f"{_vendor_name_safe}_{safe_name(inv_num_final)}.pdf"

        # --- VALORES FINALES (prioridad: manual > regla > plantilla > ocr > default) ---
        # Categoría
        categoria_final = (invoice.categoria_manual or 
                          result.category or 
                          fields.categoria or 
                          "VARIOS")

        # Serie
        serie_final = (invoice.serie_manual or
                      getattr(result, "set_serie", "") or
                      getattr(result, "serie_regla", "") or
                      _serie or
                      "")

        # Tipo de factura
        tipo_final = (invoice.tipo_factura_manual or
                     getattr(result, "set_tipo_factura", "") or
                     ("RECT" if es_rect else "FACT"))

        # Cuenta de gasto
        cuenta_gasto_final = (invoice.cuenta_gasto_manual or
                             result.expense_account or
                             "")

        # Subcuenta de gasto
        subcuenta_gasto_final = (invoice.subcuenta_gasto_manual or
                                getattr(result, "set_subcuenta_gasto", "") or
                                "")

        # Cuenta proveedor
        cuenta_proveedor_final = (invoice.cuenta_proveedor_manual or
                                 getattr(result, "set_cuenta_prov", "") or
                                 "400000")

        # Subcuenta proveedor
        subcuenta_proveedor_final = (invoice.subcuenta_proveedor_manual or
                                    getattr(result, "set_subcuenta_prov", "") or
                                    "")

        log.info(f"VALORES FINALES: cat='{categoria_final}', serie='{serie_final}', "
                f"tipo='{tipo_final}', cta_gasto='{cuenta_gasto_final}', "
                f"sub_gasto='{subcuenta_gasto_final}', cta_prov='{cuenta_proveedor_final}', "
                f"sub_prov='{subcuenta_proveedor_final}'")
        # -------------------------------------------------------------------

        # Ruta de destino
        _storage_root = self.cfg.storage_root
        try:
            from database.manager import DatabaseManager
            _cfg_root = DatabaseManager().get_config_ui("carpeta_facturas", "")
            if _cfg_root and _cfg_root.strip():
                _storage_root = _cfg_root
        except Exception:
            pass

        dest_path = resolve_dest_path(
            base_dir=_storage_root,
            year=inv_date.year,
            month=inv_date.month,
            category=categoria_final,
            filename=filename,
            months=self.cfg.months,
        )
        dest_path = avoid_collision(dest_path)

        # Resolver tipo_iva aquí (antes del watermark y del registro en BD)
        # Prioridad: manual del visor > regla > OCR > default 21
        _tipo_iva_raw = (
            getattr(invoice, "_tipo_iva_manual", None)
            or getattr(result, "set_tipo_iva", None)
            or getattr(invoice.fields, "tipo_iva", None)
            or 21
        )
        try:
            _tipo_iva = int(_tipo_iva_raw)
        except (TypeError, ValueError):
            _tipo_iva = 21

        # Estampar watermark
        log.info("RUTA-ORIG: %s", invoice.file_path)
        log.info("RUTA-DEST: %s", dest_path)

        try:
            stamp_pdf(
                input_path=invoice.file_path,
                output_path=str(dest_path),
                vendor_code=result.vendor_code,
                expense_account=cuenta_gasto_final,
                cfg=self.cfg.watermark,
                overwrite=False,
                numero_proveedor=result.vendor_code,
                nombre_proveedor=result.vendor.name,
                categoria=categoria_final,
                serie=serie_final,
                cuenta_proveedor=cuenta_proveedor_final,
                subcuenta_proveedor=subcuenta_proveedor_final,
                subcuenta_gasto=subcuenta_gasto_final,
                cont_automatica=getattr(result, "cont_automatica", False),
                retencion_pct=getattr(invoice.fields, "retention_pct", None) or 0,
                retencion_importe=getattr(invoice.fields, "retention_amount", None) or 0,
                reparto_cuentas=getattr(invoice, "_reparto_cuentas", None) or [],
                tipo_iva=_tipo_iva,
                pos_datos=getattr(invoice, "_wm_pos_datos", None),
                pos_serie=getattr(invoice, "_wm_pos_serie", None),
            )
            invoice.is_stamped = True
            invoice.final_path = str(dest_path)
            log.info("RUTA-STAMP: %s", invoice.final_path)
        except AlreadyStampedError:
            import shutil
            shutil.copy2(invoice.file_path, str(dest_path))
            invoice.final_path = str(dest_path)
            log.info("RUTA-COPY: %s", invoice.final_path)

        if not Path(invoice.final_path).exists():
            raise StorageError(f"Archivo destino no existe: {invoice.final_path}")

        log.info(f"ARCHIVO | num_archivo={inv_num_final} | cat=\"{categoria_final}\" | "
                f"serie=\"{serie_final}\" | tipo=\"{tipo_final}\" | es_rect={es_rect} | "
                f"destino={dest_path}")

        # Registrar en BD (historial)
        inv_date_str = inv_date.strftime("%Y-%m-%d") if inv_date else datetime.now().strftime("%Y-%m-%d")
        ruta_final_abs = str(Path(invoice.final_path).resolve())
        nombre_final = Path(ruta_final_abs).name

        self.db.registrar_procesado(
            hash_pdf=invoice.file_hash,
            nombre_archivo=nombre_final,
            datos={
                "nombre_proveedor":      result.vendor.name,
                "numero_proveedor":      result.vendor_code,
                "cuenta_gasto":          cuenta_gasto_final,
                "tipo_factura":          tipo_final,
                "numero_factura":        inv_num_final,
                "proveedor_id":          result.vendor.id,
                "ruta_archivo_final":    ruta_final_abs,
                "id_regla_aplicada":     getattr(result, "regla_id", None),
                "es_rectificativa":      1 if es_rect else 0,
                "numero_factura_manual": num_manual,
                "serie_factura":         serie_final,
            }
        )

        # Registrar en facturas_v10
        try:
            _sign = -1 if es_rect else 1
            _base = (invoice.fields.base_amount  or 0) * _sign
            _iva  = (invoice.fields.vat_amount   or 0) * _sign
            _tot  = (invoice.fields.total_amount or 0) * _sign
            _ret_pct = getattr(invoice.fields, "retention_pct",    None) or 0
            _ret_imp = (getattr(invoice.fields, "retention_amount", None) or 0) * _sign

            # _tipo_iva ya calculado antes del stamp_pdf (ver arriba)
            if _tipo_iva == 0:
                _iva = 0.0  # exenta

            # Reparto de cuentas: desde invoice (manual/visor) o desde la regla
            import json as _json
            _reparto = getattr(invoice, "_reparto_cuentas", None)
            if not _reparto:
                _reparto_raw = getattr(result, "reparto_cuentas_json", "") or ""
                _reparto = _json.loads(_reparto_raw) if _reparto_raw else []
            _reparto_json = _json.dumps(_reparto, ensure_ascii=False) if _reparto else ""

            self.db.registrar_factura_v10({
                "id_proveedor":           result.vendor.id,
                "fecha":                  inv_date_str,
                "ruta_pdf":               ruta_final_abs,
                "ruta_archivo_final":     ruta_final_abs,
                "base_imponible":         _base,
                "iva":                    _iva,
                "total":                  _tot,
                "tipo_iva":               _tipo_iva,
                "retencion_pct":          _ret_pct,
                "retencion_importe":      _ret_imp,
                "reparto_cuentas_json":   _reparto_json,
                "tipo_factura":           tipo_final,
                "cuenta_gasto":           cuenta_gasto_final,
                "subcuenta_gasto":        subcuenta_gasto_final,
                "categoria":              categoria_final,
                "numero_factura":         inv_num_final,
                "procesada_desde_correo": 1 if invoice.source != "manual" else 0,
                "numero_proveedor":       result.vendor_code,
                "origen_correo":          invoice.email_sender,
                "id_mensaje_unico":       getattr(invoice, "message_id", None),
                "hash_pdf":               invoice.file_hash,
                "nombre_proveedor":       result.vendor.name,
                "cif_proveedor":          getattr(result.vendor, "cif_nif", None),
                "id_regla_aplicada":      getattr(result, "regla_id", None),
                "es_rectificativa":       1 if es_rect else 0,
                "numero_factura_manual":  num_manual,
                "serie_factura":          serie_final,
                "cuenta_proveedor":       cuenta_proveedor_final,
                "subcuenta_proveedor":    subcuenta_proveedor_final,
                "nombre_regla":           getattr(result, "nombre_regla", ""),
                "razon_social_prov":      result.vendor.name,
                "cont_automatica":        1 if getattr(result, "cont_automatica", False) else 0,
                "fecha_factura":          inv_date.strftime("%Y-%m-%d") if inv_date else "",
                "fecha_contabilizacion":  getattr(invoice, "_fecha_contabilizacion",
                                                  inv_date.strftime("%Y-%m-%d") if inv_date else ""),
            })
            log.info("Factura V10 registrada: base=%s iva=%s total=%s tipo_iva=%s ret=%s%%",
                     _base, _iva, _tot, _tipo_iva, _ret_pct)
        except Exception as e:
            log.warning("Error en facturas_v10: %s", e)

        # ── Disparar alertas ─────────────────────────────────────────────────
        try:
            from alertas.motor import comprobar_y_disparar
            factura_dict = {
                "nombre_proveedor": result.vendor.name if result.vendor else "",
                "categoria":        categoria_final,
                "base_imponible":   abs(invoice.fields.base_amount or 0),
                "numero_factura":   inv_num_final,
            }
            disparadas = comprobar_y_disparar(factura_dict, self.db)
            if disparadas:
                log.info("Alertas disparadas: %d", len(disparadas))
            else:
                log.debug("Alertas: ninguna aplicable para esta factura")
        except Exception as e:
            log.warning("Error en sistema de alertas: %s", e)

        # Borrar temporal
        temp_dir = str(self.cfg.temp_dir)
        src_path = invoice.file_path
        if (temp_dir and temp_dir in src_path and
                str(Path(src_path).resolve()) != str(Path(ruta_final_abs).resolve())):
            try:
                Path(src_path).unlink(missing_ok=True)
            except Exception:
                pass

        invoice.final_path = ruta_final_abs
        invoice.status = InvoiceStatus.PROCESSED
        invoice.processed_at = datetime.now()
        log.info("✅ PROCESADA: %s → %s", invoice.file_name, nombre_final)
        return invoice

    def process_batch(self, invoices: list) -> Tuple[int, int, int]:
        processed = duplicated = errors = 0
        for inv in invoices:
            self.process(inv)
            if inv.status == InvoiceStatus.PROCESSED:
                processed += 1
            elif inv.status == InvoiceStatus.DUPLICATE:
                duplicated += 1
            elif inv.status == InvoiceStatus.ERROR:
                errors += 1
        log.info("Lote: %d procesadas, %d duplicadas, %d errores",
                 processed, duplicated, errors)
        return processed, duplicated, errors


# ── Validación multipágina ─────────────────────────────────────────────────

def _sanity_check(fields) -> list[str]:
    issues = []
    base  = fields.base_amount  or 0.0
    iva   = fields.vat_amount   or 0.0
    total = fields.total_amount or 0.0

    if base <= 0:
        issues.append(f"base={base} no positiva")
    if iva < 0:
        issues.append(f"iva={iva} negativo")
    if total < base:
        issues.append(f"total={total} < base={base}")
    if base < 0 or total < 0:
        issues.append("ABONO/NEGATIVO")

    # SEAT/multi-page fix: if total == base and iva == 0, the "total" found is
    # likely a sub-total (Total Neto) not the final total including VAT.
    # Flag this so validate_and_enrich_fields reads all pages.
    # Exception: exenta invoices (tipo_iva == 0) legitimately have total == base.
    # 0 is a valid value for tipo_iva (exenta) — cannot use "or 21"
    _tipo_iva_sanity = getattr(fields, "tipo_iva", None)
    if _tipo_iva_sanity is None: _tipo_iva_sanity = 21
    if base > 0 and iva == 0.0 and abs(total - base) < 0.02 and _tipo_iva_sanity != 0:
        issues.append(f"total={total} parece ser Total Neto (igual a base, sin IVA)")

    return issues


def validate_and_enrich_fields(pdf_path: str, fields, tesseract_path=None,
                               languages=None, ocr_enabled=True) -> tuple:
    from ocr.field_extractor import extract_fields
    issues = _sanity_check(fields)

    if not issues:
        return fields, [], False

    log.info("Validación falló, fallback OCR completo")

    try:
        import fitz
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        doc.close()
    except Exception:
        num_pages = 1

    if num_pages > 1:
        from ocr.pipeline import extract_text
        full_text_parts = []
        for page_idx in range(num_pages):
            try:
                page_text, _ = extract_text(
                    pdf_path,
                    tesseract_path=tesseract_path,
                    languages=languages or ["spa", "eng"],
                    ocr_threshold=0.1,
                    ocr_enabled=ocr_enabled,
                    page_index=page_idx,
                )
                full_text_parts.append(page_text)
            except Exception as exc:
                log.debug("Pág %d error: %s", page_idx, exc)

        full_text = "\n".join(full_text_parts)
        if full_text.strip():
            fields3 = extract_fields(full_text)
            issues3 = _sanity_check(fields3)
            if not issues3:
                fields3.extraction_method = "ocr-multipage-fallback"
                return fields3, [], False
            return fields3, issues3, True

    return fields, issues, True