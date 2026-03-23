# -*- coding: utf-8 -*-

# === CONFIGURACIÓN DE RUTAS ===
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ===============================

"""
EXTRACTORES AVANZADOS
Extrae datos fiscales y bancarios de facturas usando expresiones regulares
"""

import re
from pypdf import PdfReader

class ExtractorDatosFiscales:
    """
    Extrae información fiscal y bancaria de texto de facturas
    """
    
    def __init__(self, texto):
        self.texto = texto.upper()
        self.texto_original = texto
    
    def extraer_cif_nif(self):
        """
        Extrae CIF/NIF español
        Formatos: A12345678, B12345678, 12345678A, etc.
        """
        # Patrón CIF: Letra + 8 dígitos
        patron_cif = r'\b([A-HJ-NP-SUVW]\d{7}[0-9A-J])\b'
        # Patrón NIF: 8 dígitos + Letra
        patron_nif = r'\b(\d{8}[A-Z])\b'
        # Patrón NIE: X/Y/Z + 7 dígitos + Letra
        patron_nie = r'\b([XYZ]\d{7}[A-Z])\b'
        
        # Buscar en el texto
        match_cif = re.search(patron_cif, self.texto)
        match_nif = re.search(patron_nif, self.texto)
        match_nie = re.search(patron_nie, self.texto)
        
        if match_cif:
            return match_cif.group(1)
        elif match_nif:
            return match_nif.group(1)
        elif match_nie:
            return match_nie.group(1)
        
        return ""
    
    def extraer_iban(self):
        """
        Extrae IBAN español
        Formato: ES91 2100 0418 4502 0005 1332
        """
        # Patrón IBAN: ES + 2 dígitos + 20 dígitos (con o sin espacios)
        patron = r'\b(ES\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4})\b'
        
        match = re.search(patron, self.texto)
        if match:
            # Eliminar espacios para normalizar
            iban = match.group(1).replace(' ', '')
            return iban
        
        return ""
    
    def extraer_telefono(self):
        """
        Extrae teléfono español
        Formatos: 912345678, 91 234 56 78, +34 912 345 678, etc.
        """
        # Limpiar el texto de palabras comunes antes de buscar
        texto_limpio = self.texto_original
        
        # Patrón 1: +34 912 345 678
        patron1 = r'\+34[\s]?[6-9]\d{2}[\s]?\d{3}[\s]?\d{3}'
        # Patrón 2: 912 345 678 o 912345678
        patron2 = r'\b[6-9]\d{2}[\s]?\d{3}[\s]?\d{3}\b'
        # Patrón 3: 91 234 56 78
        patron3 = r'\b[89]\d[\s]?\d{3}[\s]?\d{2}[\s]?\d{2}\b'
        
        for patron in [patron1, patron2, patron3]:
            match = re.search(patron, texto_limpio)
            if match:
                # Eliminar espacios
                telefono = match.group(0).replace(' ', '')
                # Si empieza con +34, quitarlo
                if telefono.startswith('+34'):
                    telefono = telefono[3:]
                return telefono
        
        return ""
    
    def extraer_email(self):
        """
        Extrae email
        Formato: contacto@empresa.com
        """
        patron = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        match = re.search(patron, self.texto_original)
        if match:
            return match.group(0).lower()
        
        return ""
    
    def extraer_codigo_postal(self):
        """
        Extrae código postal español (5 dígitos)
        """
        # Buscar patrón: 5 dígitos precedidos por ciudad o seguidos por provincia
        # Patrón simple: 28xxx, 08xxx, etc.
        patron = r'\b([0-5]\d{4})\b'
        
        matches = re.findall(patron, self.texto)
        
        # Filtrar para que sea un CP válido (entre 01000 y 52999)
        for cp in matches:
            if 1000 <= int(cp) <= 52999:
                return cp
        
        return ""
    
    def extraer_direccion(self):
        """
        Intenta extraer la dirección completa
        Busca líneas que contengan C/, Calle, Avenida, etc.
        """
        lineas = self.texto_original.split('\n')
        
        palabras_direccion = ['c/', 'calle', 'avenida', 'avda', 'plaza', 'pza', 
                             'paseo', 'ronda', 'camino', 'travesía']
        
        for linea in lineas:
            linea_lower = linea.lower()
            if any(palabra in linea_lower for palabra in palabras_direccion):
                # Limpiar la línea
                direccion = linea.strip()
                if 10 < len(direccion) < 100:
                    return direccion
        
        return ""
    
    def extraer_razon_social(self):
        """
        Intenta extraer la razón social completa
        Busca líneas con S.A., S.L., etc. y sus alrededores
        """
        lineas = self.texto_original.split('\n')
        
        palabras_empresa = ['s.a.', 's.l.', 's.l.u.', 's.a.u.', 's.coop',
                           'sociedad limitada', 'sociedad anónima', 
                           'sociedad', 'limitada', 'anónima']
        
        candidatos = []
        
        for i, linea in enumerate(lineas):
            linea_lower = linea.lower()
            
            # Si la línea tiene palabras de empresa
            if any(palabra in linea_lower for palabra in palabras_empresa):
                # Intentar concatenar con la línea anterior si es corta
                if i > 0 and len(lineas[i-1].strip()) < 40:
                    razon = lineas[i-1].strip() + ' ' + linea.strip()
                    candidatos.append(razon)
                else:
                    candidatos.append(linea.strip())
        
        # Devolver el primer candidato razonable
        for candidato in candidatos:
            if 10 < len(candidato) < 100:
                return candidato
        
        return ""
    
    def extraer_base_imponible(self):
        """
        Extrae la base imponible de la factura
        Busca patrones como "Base Imponible: 100,00"
        """
        palabras_clave = ['base imponible', 'base imp', 'base', 'subtotal']
        
        lineas = self.texto_original.split('\n')
        
        for linea in lineas:
            linea_upper = linea.upper()
            
            # Buscar si contiene alguna palabra clave
            if any(palabra.upper() in linea_upper for palabra in palabras_clave):
                # Buscar importe en formato español: 1.234,56
                patron = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
                match = re.search(patron, linea)
                
                if match:
                    try:
                        from core.utils import parse_es_float
                        return parse_es_float(match.group(1))
                    except (ValueError, ImportError):
                        pass
        
        return 0.0
    
    def extraer_iva(self):
        """
        Extrae el IVA de la factura
        Busca patrones como "IVA 21%: 21,00" o "IVA: 21,00"
        """
        lineas = self.texto_original.split('\n')
        
        # Intentar encontrar líneas que mencionen IVA
        for linea in lineas:
            linea_upper = linea.upper()
            
            if 'IVA' in linea_upper and 'TOTAL' not in linea_upper:
                # Buscar importe
                patron = r'(\d{1,3}(?:\.\d{3})*,\d{2})'
                matches = re.findall(patron, linea)
                
                # El IVA suele ser el último número en la línea
                if matches:
                    try:
                        from core.utils import parse_es_float
                        return parse_es_float(matches[-1])
                    except (ValueError, ImportError):
                        pass
        
        return 0.0
    
    def extraer_todo(self):
        """
        Extrae todos los datos fiscales de una vez
        
        Returns:
            dict con todos los campos extraídos
        """
        return {
            'cif_nif': self.extraer_cif_nif(),
            'iban': self.extraer_iban(),
            'telefono': self.extraer_telefono(),
            'email': self.extraer_email(),
            'codigo_postal': self.extraer_codigo_postal(),
            'direccion': self.extraer_direccion(),
            'razon_social': self.extraer_razon_social(),
            'base_imponible': self.extraer_base_imponible(),
            'iva': self.extraer_iva()
        }


# ==================== FUNCIONES DE UTILIDAD ====================
def extraer_texto_pdf(ruta_pdf):
    """
    Extrae el texto completo de un archivo PDF
    
    Args:
        ruta_pdf: str - Ruta al archivo PDF
    
    Returns:
        str - Texto extraído del PDF
    """
    try:
        reader = PdfReader(ruta_pdf)
        texto = ""
        
        for page in reader.pages:
            texto += page.extract_text()
        
        return texto
    
    except Exception as e:
        print(f"❌ Error leyendo PDF {ruta_pdf}: {e}")
        return ""


def extraer_datos_completos_pdf(texto_pdf):
    """
    Función auxiliar para extraer todos los datos fiscales de un texto de PDF
    
    Args:
        texto_pdf: str - Texto extraído del PDF
    
    Returns:
        dict con todos los campos fiscales y bancarios
    """
    extractor = ExtractorDatosFiscales(texto_pdf)
    return extractor.extraer_todo()
