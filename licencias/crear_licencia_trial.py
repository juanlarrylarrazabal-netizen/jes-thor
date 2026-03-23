# -*- coding: utf-8 -*-

# === CONFIGURACIÓN DE RUTAS ===
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ===============================

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CREADOR DE LICENCIA TRIAL
Crea una licencia de prueba de 30 días
"""

import sys
import os

# Agregar el directorio actual al path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gestor_licencias import crear_licencia_trial
    
    print("=" * 50)
    print("  CREANDO LICENCIA TRIAL DE 30 DÍAS")
    print("=" * 50)
    print()
    
    if crear_licencia_trial(dias=30):
        print("✅ Licencia trial creada correctamente")
        print("   Archivo: licencia.dat")
        print("   Validez: 30 días")
        print()
        print("   Esta licencia se incluirá en el instalador")
    else:
        print("❌ Error al crear la licencia trial")
        sys.exit(1)
    
    print("=" * 50)
    
except ImportError as e:
    print(f"❌ Error: No se pudo importar gestor_licencias")
    print(f"   Detalle: {e}")
    print()
    print("   Asegúrate de que gestor_licencias.py está en el mismo directorio")
    sys.exit(1)

except Exception as e:
    print(f"❌ Error inesperado: {e}")
    sys.exit(1)
