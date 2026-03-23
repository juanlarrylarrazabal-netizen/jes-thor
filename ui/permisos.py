# -*- coding: utf-8 -*-
"""
ui/permisos.py — Sistema de permisos por rol V15.
"""
from __future__ import annotations

# Jerarquía de roles (mayor = más privilegios)
ROL_NIVEL = {
    "super_admin":     100,
    "admin":            80,
    "usuario_avanzado": 50,
    "usuario_basico":   20,
}

# Permisos mínimos por módulo/acción
PERMISOS = {
    # Módulos (tab visibilidad)
    "tab_facturas":      "usuario_basico",
    "tab_historial":     "usuario_basico",
    "tab_proveedores":   "usuario_avanzado",
    "tab_informes":      "usuario_avanzado",
    "tab_ajustes":       "admin",

    # Acciones
    "cargar_pdf":        "usuario_basico",
    "descargar_correo":  "usuario_avanzado",
    "editar_proveedor":  "usuario_avanzado",
    "eliminar_proveedor":"admin",
    "exportar_excel":    "usuario_avanzado",
    "gestionar_usuarios":"admin",
    "cambiar_config":    "admin",
    "gestionar_licencia":"super_admin",
}


def tiene_permiso(rol: str, permiso: str) -> bool:
    """Devuelve True si el rol tiene nivel suficiente para el permiso."""
    nivel_usuario  = ROL_NIVEL.get(rol.lower(), 0)
    min_rol        = PERMISOS.get(permiso, "usuario_basico")
    nivel_requerido = ROL_NIVEL.get(min_rol, 0)
    return nivel_usuario >= nivel_requerido


def bloquear_widget(widget, rol: str, permiso: str, tooltip: str = ""):
    """Deshabilita un widget si el rol no tiene el permiso."""
    ok = tiene_permiso(rol, permiso)
    widget.setEnabled(ok)
    if not ok:
        t = tooltip or f"No tiene permiso ({permiso} requiere {PERMISOS.get(permiso,'admin')})"
        widget.setToolTip(t)
    return ok
