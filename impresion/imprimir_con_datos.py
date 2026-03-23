# -*- coding: utf-8 -*-
"""
Módulo para imprimir PDFs con datos de procesamiento
DISEÑO FINAL CORREGIDO:
- Marca de agua ROJA en zona central
- Esquina superior derecha: SERIE MÁS PEQUEÑA Y CENTRADA
- Espacio para escribir Nº de proveedor a mano (25000088)
"""
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import red, black
import os
import tempfile
import logging

_log = logging.getLogger("gestor.impresion")


def detectar_zona_blanca(ruta_pdf):
    """
    Detecta una zona con poco texto en el centro del PDF.
    Retorna coordenadas (x, y) óptimas para la marca de agua.
    """
    try:
        doc = fitz.open(ruta_pdf)
        pagina = doc[0]
        
        # Obtener tamaño de página
        rect = pagina.rect
        ancho = rect.width
        alto = rect.height
        
        # Extraer bloques de texto
        bloques = pagina.get_text("blocks")
        
        # Definir zonas candidatas (centro y centro-derecha)
        zonas_candidatas = [
            (ancho * 0.5, alto * 0.5),   # Centro
            (ancho * 0.6, alto * 0.4),   # Centro-derecha superior
            (ancho * 0.6, alto * 0.6),   # Centro-derecha inferior
            (ancho * 0.4, alto * 0.5),   # Centro-izquierda
        ]
        
        # Buscar zona con menos texto cerca
        mejor_zona = zonas_candidatas[0]
        min_bloques = float('inf')
        
        for x, y in zonas_candidatas:
            # Contar bloques en radio de 100 puntos
            bloques_cerca = sum(1 for b in bloques 
                              if abs(b[0] - x) < 100 and abs(b[1] - y) < 100)
            if bloques_cerca < min_bloques:
                min_bloques = bloques_cerca
                mejor_zona = (x, y)
        
        doc.close()
        return mejor_zona
        
    except Exception as e:
        _log.warning("detectar_zona_blanca: error al analizar PDF, usando centro A4: %s", e)
        # Fallback: centro de página A4
        return (A4[0] * 0.5, A4[1] * 0.5)


def crear_pdf_con_cabecera(ruta_pdf_original, datos_procesamiento, ruta_salida=None):
    """
    Crea un nuevo PDF con datos de procesamiento.
    
    DISEÑO CORREGIDO:
    - MARCA DE AGUA ROJA en zona central óptima
    - Esquina superior derecha: SERIE PEQUEÑA (14pt) y MÁS CENTRADA
    - Espacio a la derecha para escribir Nº proveedor a mano
    
    Args:
        ruta_pdf_original: Ruta del PDF original
        datos_procesamiento: Dict con {proveedor, cuenta_gasto, serie}
        ruta_salida: Ruta donde guardar el PDF (opcional)
    
    Returns:
        Ruta del PDF generado
    """
    if not ruta_salida:
        ruta_salida = tempfile.mktemp(suffix='.pdf')
    
    # Detectar mejor posición para marca de agua
    pos_x, pos_y = detectar_zona_blanca(ruta_pdf_original)
    
    # Abrir PDF original
    doc_original = fitz.open(ruta_pdf_original)
    
    # Crear PDF de overlay con reportlab
    overlay_temp = tempfile.mktemp(suffix='.pdf')
    
    c = canvas.Canvas(overlay_temp, pagesize=A4)
    ancho, alto = A4
    
    # Extraer datos
    proveedor = str(datos_procesamiento.get('proveedor', '') or '').upper()
    cuenta = str(datos_procesamiento.get('cuenta_gasto', '') or '')
    serie = str(datos_procesamiento.get('serie', '') or '').strip()
    
    # ============================================================
    # MARCA DE AGUA ROJA EN ZONA CENTRAL ÓPTIMA
    # ============================================================
    c.saveState()
    
    # Mover a posición detectada
    c.translate(pos_x, pos_y)
    
    # Configurar color ROJO con transparencia (más discreta)
    c.setFillColorRGB(1, 0, 0, alpha=0.08)  # Rojo 8% opacidad
    
    # Texto MÁS PEQUEÑO y en dos líneas
    c.setFont("Helvetica", 16)  # Reducido de 18 a 16
    texto_marca = f"Nº {proveedor}"
    c.drawCentredString(0, 10, texto_marca)
    
    c.setFont("Helvetica", 12)  # Reducido de 14 a 12
    c.drawCentredString(0, -8, cuenta)
    
    c.restoreState()
    
    # ============================================================
    # ESQUINA SUPERIOR DERECHA - SERIE MÁS PEQUEÑA Y CENTRADA
    # ============================================================
    c.setFillColor(black)
    
    # ========== CORRECCIÓN: Serie más pequeña y movida a la izquierda ==========
    c.setFont("Helvetica-Bold", 14)  # Reducido de 28 a 14
    
    # Mover más a la izquierda para dejar espacio para escribir a mano
    margen_derecha = ancho - 35*mm  # Antes era 18mm, ahora 35mm (más a la izquierda)
    margen_superior = alto - 10*mm   # Antes 12mm, ahora 10mm (un poco más arriba)
    
    # Solo la letra/número de serie, nada más
    c.drawRightString(margen_derecha, margen_superior, serie)
    # ===========================================================================
    
    # Guardar
    c.showPage()
    c.save()
    
    # Combinar PDFs
    doc_overlay = fitz.open(overlay_temp)
    doc_final = fitz.open()
    
    # Para cada página del documento original
    for i in range(len(doc_original)):
        # Obtener página original
        pagina_original = doc_original[i]
        
        # Crear nueva página en doc final
        pagina_final = doc_final.new_page(
            width=pagina_original.rect.width,
            height=pagina_original.rect.height
        )
        
        # Añadir contenido original
        pagina_final.show_pdf_page(pagina_final.rect, doc_original, i)
        
        # Superponer overlay solo en primera página
        if i == 0:
            pagina_overlay = doc_overlay[0]
            pagina_final.show_pdf_page(pagina_final.rect, doc_overlay, 0)
    
    # Guardar
    doc_final.save(ruta_salida)
    
    # Limpiar
    doc_original.close()
    doc_overlay.close()
    doc_final.close()
    
    try:
        os.remove(overlay_temp)
    except Exception as e:
        _log.debug("No se pudo eliminar archivo temporal %s: %s", overlay_temp, e)
    
    return ruta_salida


def imprimir_pdf_procesado(ruta_pdf, datos_procesamiento, nombre_impresora=None):
    """
    Imprime un PDF con datos de procesamiento.
    
    Args:
        ruta_pdf: Ruta del PDF a imprimir
        datos_procesamiento: Dict con datos de procesamiento
        nombre_impresora: Nombre de la impresora (opcional)
    """
    import win32print
    import win32api
    
    # Crear PDF temporal con overlay
    pdf_temp = crear_pdf_con_cabecera(ruta_pdf, datos_procesamiento)
    
    try:
        # Imprimir
        if nombre_impresora:
            win32print.SetDefaultPrinter(nombre_impresora)
        
        win32api.ShellExecute(0, "print", pdf_temp, None, ".", 0)
        
        # Esperar un poco antes de borrar el archivo temporal
        import time
        time.sleep(2)
        
    finally:
        # Limpiar archivo temporal
        try:
            os.remove(pdf_temp)
        except Exception as e:
            _log.debug("No se pudo eliminar PDF temporal %s: %s", pdf_temp, e)


if __name__ == "__main__":
    # Test
    datos_test = {
        'proveedor': '12345',
        'cuenta_gasto': '628.100',
        'serie': 'A'
    }
    
    print("=" * 60)
    print("PRUEBA DE IMPRESIÓN CON MARCA DE AGUA")
    print("=" * 60)
    print()
    print("Creando PDF de prueba...")
    
    pdf_salida = crear_pdf_con_cabecera(
        "factura_ejemplo.pdf",
        datos_test,
        "factura_con_marca_agua.pdf"
    )
    
    print(f"✓ PDF creado: {pdf_salida}")
    print()
    print("Características:")
    print(f"  • Marca de agua ROJA en zona central óptima")
    print(f"  • Texto: Nº {datos_test['proveedor']} / {datos_test['cuenta_gasto']}")
    print(f"  • Serie arriba derecha: {datos_test['serie']} (tamaño 14pt)")
    print(f"  • Posición: 35mm desde borde derecho (espacio para escribir)")
    print()
    print("✓ Listo para imprimir")