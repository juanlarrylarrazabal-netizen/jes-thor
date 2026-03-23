# -*- coding: utf-8 -*-
"""
modulos/escaner.py
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Callable

from PyQt5.QtCore import QThread, pyqtSignal

from core.logging_config import get_logger
log = get_logger("escaner")

# Número máximo de páginas por trabajo (evita bucle infinito si el escáner no lanza excepción)
MAX_ADF_PAGES = 200


def detect_backend() -> str:
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            import pythoncom        # noqa: F401
            return "wia"
        except ImportError:
            log.warning("pywin32 no instalado. Ejecuta: pip install pywin32")
    elif sys.platform.startswith("linux"):
        try:
            import sane             # noqa: F401
            return "sane"
        except ImportError:
            pass
    elif sys.platform == "darwin":
        return "ica"
    return "hotfolder"


def list_scanners() -> List[str]:
    backend = detect_backend()
    try:
        if backend == "wia":
            return _list_wia()
        elif backend == "sane":
            return _list_sane()
        elif backend == "ica":
            return ["ICA/ImageCapture (macOS)"]
    except Exception as exc:
        log.debug("list_scanners error: %s", exc)
    return ["(Hot-Folder — sin escáner detectado)"]


def _list_wia() -> List[str]:
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    try:
        wm = win32com.client.Dispatch("WIA.DeviceManager")
        scanners = []
        for i in range(wm.DeviceInfos.Count):
            di = wm.DeviceInfos.Item(i + 1)
            scanners.append(di.Properties("Name").Value)
        return scanners
    finally:
        pythoncom.CoUninitialize()


def _list_sane() -> List[str]:
    import sane
    sane.init()
    devices = sane.get_devices()
    return [f"{d[2]} ({d[0]})" for d in devices] if devices else []


def is_blank_page(image_path: str, threshold: float = 0.98) -> bool:
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(image_path).convert("L")
        img_array = np.array(img)
        white_ratio = (img_array > 240).sum() / img_array.size
        log.debug(f"Página {image_path}: ratio blanco = {white_ratio:.3f}")
        return white_ratio >= threshold
    except Exception as e:
        log.error(f"Error detectando página en blanco: {e}")
        return False


class _AdfEmptyError(Exception):
    """Señal interna: el ADF no tiene más papel. No es un error, es fin normal."""


class ScanJob:

    # WIA CONSTANTES
    WIA_DPS_DOCUMENT_HANDLING_SELECT = 3088
    FEEDER  = 1
    FLATBED = 2
    DUPLEX  = 4

    ADF_PROPERTY_NAMES = [
        "Document Handling Select", "Feeder", "ADF", "Source"
    ]

    XRES_NAMES = ["Horizontal Resolution", "X-Resolution", "X Resolution"]
    YRES_NAMES = ["Vertical Resolution", "Y-Resolution", "Y Resolution"]

    def __init__(self, db=None, output_dir: str = None,
                 dpi: int = 300, color: str = "color",
                 paper_size: str = "A4",
                 source: str = "flatbed",
                 duplex: bool = False,
                 combine_pages: bool = True,
                 detect_blank_pages: bool = True,
                 blank_threshold: float = 0.98,
                 timeout_seconds: int = 30,
                 on_progress: Optional[Callable] = None):

        self.db = db
        self.dpi = dpi
        self.color = color
        self.paper_size = paper_size
        self.source = source
        self.duplex = duplex
        self.combine_pages = combine_pages
        self.detect_blank_pages = detect_blank_pages
        self.blank_threshold = blank_threshold
        self.timeout_seconds = timeout_seconds
        self.on_progress = on_progress or (lambda msg: None)
        self._cancelled = False
        self._temp_files: List[str] = []

        if output_dir is None:
            try:
                from database.manager import DatabaseManager
                _db = db or DatabaseManager()
                output_dir = _db.get_config_ui(
                    "carpeta_escaner",
                    str(Path.home() / "Facturas_Escaneadas")
                )
            except Exception:
                output_dir = str(Path.home() / "Facturas_Escaneadas")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Directorio de salida: {self.output_dir}")

    def cancel(self):
        self._cancelled = True
        self.on_progress("⛔ Cancelando escaneo...")

    # ------------------------------------------------------------------
    # WIA helpers  (todos asumen que CoInitialize ya fue llamado)
    # ------------------------------------------------------------------

    def _connect_wia(self, scanner_name: str):
        """Conecta con el escáner WIA indicado. Lanza RuntimeError si no se encuentra."""
        import win32com.client
        wm = win32com.client.Dispatch("WIA.DeviceManager")
        for i in range(wm.DeviceInfos.Count):
            di = wm.DeviceInfos.Item(i + 1)
            if di.Properties("Name").Value == scanner_name:
                log.info(f"Escáner encontrado: {scanner_name}")
                return di.Connect()
        raise RuntimeError(f"Escáner no encontrado: {scanner_name}")

    def _get_scan_item(self, device):
        """
        Devuelve el primer item de escaneo del dispositivo.
        WIA Items es una colección COM indexada desde 1.
        """
        # Intentamos acceso por índice COM (1-based) primero; si falla, probamos 0-based.
        try:
            item = device.Items.Item(1)
            log.debug("Item obtenido vía Items.Item(1)")
            return item
        except Exception:
            pass
        try:
            item = device.Items[0]
            log.debug("Item obtenido vía Items[0]")
            return item
        except Exception:
            pass
        # Último recurso: Items sin índice (algunos drivers lo soportan)
        try:
            item = device.Items(1)
            log.debug("Item obtenido vía Items(1)")
            return item
        except Exception as e:
            raise RuntimeError(f"No se pudo obtener el item de escaneo: {e}") from e

    def _set_wia_adf(self, device, item) -> bool:
        """Activa el ADF en el dispositivo WIA."""
        value = self.FEEDER | (self.DUPLEX if self.duplex else 0)

        # 1️⃣ Por PropertyID en el item
        try:
            for prop in item.Properties:
                if prop.PropertyID == self.WIA_DPS_DOCUMENT_HANDLING_SELECT:
                    prop.Value = value
                    log.info(f"ADF activado (item, PropertyID={prop.PropertyID})")
                    return True
        except Exception as e:
            log.debug(f"ADF item por ID falló: {e}")

        # 2️⃣ Por PropertyID en el device
        try:
            for prop in device.Properties:
                if prop.PropertyID == self.WIA_DPS_DOCUMENT_HANDLING_SELECT:
                    prop.Value = value
                    log.info(f"ADF activado (device, PropertyID={prop.PropertyID})")
                    return True
        except Exception as e:
            log.debug(f"ADF device por ID falló: {e}")

        # 3️⃣ Fallback por nombre de propiedad
        try:
            for prop in item.Properties:
                if any(n.lower() in prop.Name.lower() for n in self.ADF_PROPERTY_NAMES):
                    prop.Value = value
                    log.info(f"ADF activado por nombre: {prop.Name}")
                    return True
        except Exception as e:
            log.debug(f"ADF fallback por nombre falló: {e}")

        log.warning("No se pudo activar el ADF en este dispositivo")
        return False

    # Códigos HRESULT de WIA que indican ADF vacío (fin normal, no error).
    _WIA_END_OF_PAPER_CODES = {
        -2147023436,   # 0x80070714  timeout sin papel (Brother)
        -2147216352,   # 0x80210020  WIA_ERROR_PAPER_EMPTY
        -2147216351,   # 0x80210021  WIA_ERROR_PAPER_JAM
        -2147216353,   # 0x8021001F  WIA_ERROR_PAPER_PROBLEM
        -2147352567,   # 0x80020009  DISP_E_EXCEPTION genérico (Brother ADF vacío)
    }

    def _scan_wia_page(self, item, page_num: int) -> Optional[str]:
        """
        Transfiere una página desde WIA y la guarda como JPEG.
        - Devuelve la ruta si la página se obtuvo correctamente.
        - Lanza _AdfEmptyError si WIA indica que el ADF está vacío (salida limpia del bucle).
        - Devuelve None ante cualquier otro error real.
        """
        try:
            img = item.Transfer("{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}")
            temp_file = self.output_dir / f"temp_{int(time.time() * 1000)}_{page_num}.jpg"
            img.SaveFile(str(temp_file))
            log.debug(f"Página {page_num} guardada: {temp_file}")
            # Notificar con la ruta del JPG para que la UI pueda generar miniatura
            self.on_progress(str(temp_file))
            return str(temp_file)
        except Exception as e:
            hresult = None
            if e.args:
                try:
                    hresult = int(e.args[0])
                except (TypeError, ValueError):
                    pass
            if hresult in self._WIA_END_OF_PAPER_CODES:
                log.info(f"ADF vacío en página {page_num} (HRESULT={hresult:#010x}) — fin normal")
                raise _AdfEmptyError()
            log.error(f"Error escaneando página {page_num}: {e}")
            return None

    # ------------------------------------------------------------------
    # Modos de escaneo WIA (cada uno gestiona su propio ciclo COM)
    # ------------------------------------------------------------------

    def _scan_wia_adf(self, scanner_name: str) -> List[str]:
        """Escanea todas las páginas del ADF. Gestiona COM en este hilo."""
        import pythoncom
        pythoncom.CoInitialize()
        device = None
        temp_files: List[str] = []

        try:
            device = self._connect_wia(scanner_name)
            item = self._get_scan_item(device)

            if not self._set_wia_adf(device, item):
                self.on_progress("⚠️ ADF no soportado → usando cristal")
                log.warning("ADF no disponible, cambiando a flatbed")
                # CORRECCIÓN: cerramos COM antes de llamar a flatbed
                #             para evitar doble CoInitialize en el mismo hilo
                device.Close()
                device = None
                pythoncom.CoUninitialize()
                return self._scan_wia_flatbed(scanner_name)

            self.on_progress("📠 ADF activo, escaneando...")
            page = 0

            while not self._cancelled and page < MAX_ADF_PAGES:
                self.on_progress(f"📄 Escaneando página {page + 1}...")
                try:
                    img = self._scan_wia_page(item, page)
                except _AdfEmptyError:
                    # Fin normal del ADF: no hay más papel
                    log.info(f"ADF vacío tras {page} página(s) — salida inmediata")
                    break

                if not img:
                    # Error real de escaneo — salir también para no bloquear
                    log.warning(f"Página {page} no obtenida (error real), terminando bucle")
                    break

                if self.detect_blank_pages and is_blank_page(img, self.blank_threshold):
                    log.info(f"Página {page} en blanco, descartada")
                    try:
                        os.remove(img)
                    except OSError:
                        pass
                else:
                    temp_files.append(img)
                    self._temp_files.append(img)

                page += 1
                # Pausa mínima entre páginas — el ADF no necesita más
                time.sleep(0.2)

            if page >= MAX_ADF_PAGES:
                log.warning(f"Se alcanzó el límite de {MAX_ADF_PAGES} páginas por trabajo")

            log.info(f"ADF: {page} páginas procesadas, {len(temp_files)} válidas")
            return temp_files

        except Exception as e:
            log.exception(f"Error en _scan_wia_adf: {e}")
            self.on_progress(f"❌ Error ADF: {e}")
            return []
        finally:
            if device is not None:
                try:
                    device.Close()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _scan_wia_flatbed(self, scanner_name: str) -> List[str]:
        """Escanea una sola página desde el cristal."""
        import pythoncom
        pythoncom.CoInitialize()
        device = None

        try:
            device = self._connect_wia(scanner_name)
            item = self._get_scan_item(device)
            self.on_progress("🖼️ Escaneando desde cristal...")
            img = self._scan_wia_page(item, 0)
            if img:
                self._temp_files.append(img)
                return [img]
            return []
        except Exception as e:
            log.exception(f"Error en _scan_wia_flatbed: {e}")
            self.on_progress(f"❌ Error flatbed: {e}")
            return []
        finally:
            if device is not None:
                try:
                    device.Close()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def scan(self, scanner_name: str) -> List[str]:
        backend = detect_backend()
        log.info(f"scan(): backend={backend}, source={self.source}, scanner={scanner_name}")

        try:
            if backend == "wia":
                if self.source == "adf":
                    return self._scan_wia_adf(scanner_name)
                return self._scan_wia_flatbed(scanner_name)

            self.on_progress("❌ Backend de escaneo no disponible en esta plataforma")
            log.error(f"Backend '{backend}' no implementado")
            return []

        except Exception as exc:
            log.exception(f"scan() error inesperado: {exc}")
            self.on_progress(f"❌ Error inesperado: {exc}")
            return []

    def convert_to_pdf(self, image_paths: List[str]) -> List[str]:
        """
        Convierte una lista de imágenes JPEG/PNG a un único PDF usando Pillow.
        Pillow es más robusto que img2pdf con los JPEGs que genera el driver WIA,
        que a menudo tienen metadatos EXIF o DPI incorrectos que img2pdf rechaza.
        """
        if not image_paths:
            log.warning("convert_to_pdf: lista de imágenes vacía")
            return []

        # Filtrar sólo los archivos que realmente existen
        existing = [p for p in image_paths if os.path.exists(p)]
        missing  = [p for p in image_paths if p not in existing]
        if missing:
            log.warning(f"Imágenes no encontradas (se ignoran): {missing}")
        if not existing:
            log.error("Ninguna imagen existe en disco")
            self.on_progress("❌ No se encontraron las imágenes escaneadas")
            return []

        try:
            from PIL import Image as PilImage
        except ImportError:
            log.error("Pillow no instalado. Ejecuta: pip install Pillow")
            self.on_progress("⚠️ Pillow no instalado. Ejecuta: pip install Pillow")
            return []

        out = self.output_dir / f"scan_{int(time.time())}.pdf"
        pdf_created = False
        try:
            self.on_progress(f"📎 Generando PDF ({len(existing)} página(s))...")

            paginas = []
            primera = None

            for ruta in existing:
                try:
                    img = PilImage.open(ruta)
                    # Convertir a RGB para garantizar compatibilidad PDF
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    elif img.mode == "L":
                        pass  # escala de grises es válida en PDF
                    else:
                        img = img.convert("RGB")

                    # Forzar DPI a 300 si no hay info o está mal
                    dpi = img.info.get("dpi", (300, 300))
                    if not dpi or dpi[0] < 10:
                        dpi = (300, 300)

                    if primera is None:
                        primera = (img, dpi)
                    else:
                        paginas.append((img, dpi))
                except Exception as e:
                    log.error(f"Error abriendo imagen {ruta}: {e}")
                    self.on_progress(f"⚠️ No se pudo leer {Path(ruta).name}: {e}")

            if primera is None:
                log.error("Ninguna imagen se pudo leer")
                self.on_progress("❌ No se pudieron leer las imágenes escaneadas")
                return []

            img_primera, dpi_primera = primera
            extra = [img for img, _ in paginas]

            save_kwargs = {
                "format":       "PDF",
                "resolution":   dpi_primera[0],
                "save_all":     True,
            }
            if extra:
                save_kwargs["append_images"] = extra

            img_primera.save(str(out), **save_kwargs)
            pdf_created = True

            # Cerrar imágenes Pillow
            img_primera.close()
            for img, _ in paginas:
                try:
                    img.close()
                except Exception:
                    pass

            size_kb = os.path.getsize(out) // 1024
            log.info(f"PDF creado: {out} ({size_kb} KB, {len(existing)} página(s))")
            self.on_progress(f"✅ PDF generado: {Path(out).name} ({size_kb} KB)")
            return [str(out)]

        except Exception as e:
            log.exception(f"Error al crear el PDF: {e}")
            self.on_progress(f"❌ Error al crear PDF: {e}")
            # Si el PDF quedó a medias, borrarlo
            if out.exists() and not pdf_created:
                try:
                    out.unlink()
                except OSError:
                    pass
            return []

        finally:
            # Limpiar JPEGs temporales sólo si el PDF se creó correctamente
            if pdf_created:
                for img_path in existing:
                    try:
                        os.remove(img_path)
                        log.debug(f"Temporal eliminado: {img_path}")
                    except OSError as e:
                        log.warning(f"No se pudo eliminar temporal {img_path}: {e}")
                self._temp_files = [f for f in self._temp_files if f not in existing]
            else:
                log.warning("PDF no creado — se conservan los JPEGs temporales en: "
                            + str(self.output_dir))

    def scan_page(self, scanner_name: str) -> str:
        """Escanea una sola página y devuelve la ruta al PDF resultante (o None)."""
        old_source = self.source
        self.source = "flatbed"
        try:
            pdfs = self.scan_to_pdf(scanner_name)
            return pdfs[0] if pdfs else None
        finally:
            self.source = old_source

    def scan_batch_adf(self, scanner_name: str) -> List[str]:
        """Escanea un lote desde el ADF y devuelve lista de PDFs."""
        old_source = self.source
        self.source = "adf"
        try:
            return self.scan_to_pdf(scanner_name)
        finally:
            self.source = old_source

    def scan_to_pdf(self, scanner_name: str) -> List[str]:
        images = self.scan(scanner_name)
        if not images:
            log.warning("scan_to_pdf: no se obtuvieron imágenes")
            self.on_progress("⚠️ No se obtuvo ninguna imagen del escáner")
            return []
        return self.convert_to_pdf(images)


class ScanWorker(QThread):
    progress = pyqtSignal(str)
    # 'object' evita que PyQt5 intente serializar la lista entre hilos,
    # lo que en algunos entornos provoca que la señal se descarte silenciosamente.
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, scanner_name: str, scan_job: ScanJob):
        super().__init__()
        self.scanner_name = scanner_name
        self.scan_job = scan_job
        # Conectar on_progress al hilo de UI a través de la señal
        self.scan_job.on_progress = self._emit_progress

    def _emit_progress(self, msg: str) -> None:
        """Wrapper thread-safe para emitir progreso."""
        try:
            self.progress.emit(str(msg))
        except Exception:
            pass

    def run(self):
        # COM debe inicializarse en cada hilo que lo use (Windows)
        _com_initialized = False
        pdfs = []
        try:
            if sys.platform == "win32":
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                    _com_initialized = True
                    log.debug("COM inicializado en ScanWorker")
                except Exception as e:
                    log.warning(f"CoInitialize en QThread falló: {e}")

            pdfs = self.scan_job.scan_to_pdf(self.scanner_name)
            log.info(f"ScanWorker: scan_to_pdf devolvió {len(pdfs)} PDF(s)")

        except Exception as e:
            log.exception(f"Excepción no controlada en ScanWorker: {e}")
            self.error.emit(str(e))
            return

        finally:
            if _com_initialized:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        # Emitir fuera del finally para garantizar que COM ya está liberado
        if pdfs:
            self.finished.emit(pdfs)
        else:
            self.error.emit("No se obtuvo ningún PDF. Comprueba que el escáner está encendido y tiene papel.")

    def cancel(self):
        self.scan_job.cancel()
