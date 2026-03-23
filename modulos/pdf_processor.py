# -*- coding: utf-8 -*-
import re, os
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import red
from io import BytesIO
from database import DatabaseManager

def extraer_texto_pdf(ruta_pdf):
    """Extrae texto asegurando el cierre del archivo para evitar bloqueos WinError 32."""
    try:
        with open(ruta_pdf, "rb") as f:
            reader = PdfReader(f)
            texto = ""
            for page in reader.pages:
                texto += page.extract_text() or ""
            return texto
    except Exception as e:
        print(f"❌ Error leyendo PDF {ruta_pdf}: {e}")
        return ""

class PDFProcessor:
    def __init__(self, ruta_pdf):
        self.ruta_pdf = ruta_pdf
        self.texto = ""
        self.db = DatabaseManager()
        self._leer()

    def _leer(self):
        self.texto = extraer_texto_pdf(self.ruta_pdf)

    def grabar_y_distribuir(self, ruta_final, num_prov, cuenta):
        """
        Genera el PDF final con la marca de agua.
        """
        print(f"\n🔴 PDFProcessor.grabar_y_distribuir()")
        print(f"   Ruta: {ruta_final}")
        print(f"   num_prov recibido: '{num_prov}' (tipo: {type(num_prov)})")
        print(f"   cuenta recibida: '{cuenta}'")
        
        try:
            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=A4)
            can.setFont("Helvetica-Bold", 10)
            can.setFillColor(red)
            
            # Verificar que num_prov no esté vacío
            if not num_prov or str(num_prov).strip() == "":
                num_prov = "S/C"
                print(f"   ⚠️ num_prov vacío, usando 'S/C'")
            
            print(f"   ✅ Escribiendo en PDF: Prv: {num_prov} | Cta: {cuenta}")
            
            can.drawString(50, 50, f"Prv: {num_prov}")
            can.drawString(50, 35, f"Cta: {cuenta}")
            can.save()
            packet.seek(0)
            
            with open(self.ruta_pdf, "rb") as f_in:
                r = PdfReader(f_in)
                w = PdfWriter()
                marca = PdfReader(packet).pages[0]
                
                pag0 = r.pages[0]
                pag0.merge_page(marca)
                w.add_page(pag0)
                
                for p in r.pages[1:]:
                    w.add_page(p)
                
                with open(ruta_final, "wb") as f_out:
                    w.write(f_out)
            print(f"   ✅ PDF guardado en: {ruta_final}")
            return True
        except Exception as e:
            print(f"❌ Error al grabar PDF final: {e}")
            return False

def procesar_factura_completa(ruta_pdf):
    """
    Procesa una factura y devuelve TODOS los datos del proveedor.
    CON DEBUG EXTREMO.
    """
    print(f"\n🔵 procesar_factura_completa()")
    print(f"   Ruta PDF: {ruta_pdf}")
    
    proc = PDFProcessor(ruta_pdf)
    db = DatabaseManager()
    
    # Buscar proveedor en el texto
    print(f"   Buscando proveedor en el texto...")
    prov_db = db.buscar_proveedor_en_texto(proc.texto)
    
    if prov_db:
        print(f"   ✅ Proveedor encontrado en BD:")
        print(f"      ID: {prov_db[0]}")
        print(f"      Nombre: {prov_db[1]}")
        print(f"      Nº Proveedor: '{prov_db[2]}'")
        print(f"      Cuenta: {prov_db[3]}")
        print(f"      Categoría: {prov_db[4]}")
    else:
        print(f"   ⚠️ Proveedor NO encontrado en BD")
    
    if prov_db and len(prov_db) >= 5:
        id_db_proveedor = prov_db[0]   # ID interno
        nombre_db = prov_db[1]          # Nombre comercial
        numero_proveedor = prov_db[2]   # ¡NÚMERO DE PROVEEDOR!
        cuenta_gasto = prov_db[3]       # Cuenta contable
        categoria = prov_db[4]          # Categoría
    else:
        id_db_proveedor = None
        nombre_db = None
        numero_proveedor = ""
        cuenta_gasto = ""
        categoria = "VARIOS"
    
    # Extraer número de factura del PDF
    numero_factura = ""
    lineas = proc.texto.split('\n')
    for linea in lineas:
        if "FACTURA" in linea.upper() or "Nº" in linea.upper() or "NUMERO" in linea.upper():
            match = re.search(r'[A-Z0-9][-/\w]{5,}', linea)
            if match:
                numero_factura = match.group()
                break
    
    # ========== DEVOLVER CON NOMBRES CONSISTENTES ==========
    res = {
        "texto": proc.texto,
        "processor_obj": proc,
        "id_db_proveedor": id_db_proveedor,
        "nombre_db": nombre_db,
        "numero_proveedor": numero_proveedor,
        "id_proveedor": numero_proveedor,
        "cuenta_gasto": cuenta_gasto,
        "categoria": categoria,
        "numero_factura": numero_factura
    }
    
    print(f"\n   📦 Datos devueltos por procesar_factura_completa:")
    print(f"      id_db_proveedor: {res['id_db_proveedor']}")
    print(f"      nombre_db: {res['nombre_db']}")
    print(f"      numero_proveedor: '{res['numero_proveedor']}'")
    print(f"      id_proveedor: '{res['id_proveedor']}'")
    print(f"      cuenta_gasto: '{res['cuenta_gasto']}'")
    print(f"      categoria: '{res['categoria']}'")
    print(f"      numero_factura: '{res['numero_factura']}'")
    
    return res