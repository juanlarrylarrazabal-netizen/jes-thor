# -*- coding: utf-8 -*-
"""
Mixin de menú contextual para QTableWidget.
Uso: añadir a cualquier tabla con tabla.setContextMenuPolicy(Qt.CustomContextMenu)
y conectar a la función add_context_menu(tabla, acciones).

Cada acción es: (texto, callback, condicion_opcional)
"""
from PyQt5.QtWidgets import QMenu, QAction
from PyQt5.QtCore import Qt


def add_context_menu(tabla, acciones):
    """
    Añade menú contextual (botón derecho) a una QTableWidget.
    acciones: lista de (texto, callback) o (texto, callback, enabled_fn)
              o None para separador.
    """
    tabla.setContextMenuPolicy(Qt.CustomContextMenu)

    def _show_menu(pos):
        if tabla.rowCount() == 0:
            return
        menu = QMenu(tabla)
        menu.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #CBD5E0;border-radius:6px;padding:4px;}"
            "QMenu::item{padding:6px 20px;border-radius:4px;color:#2D3748;}"
            "QMenu::item:selected{background:#EBF8FF;color:#1F4E79;}"
            "QMenu::separator{height:1px;background:#E2E8F0;margin:4px 8px;}"
        )
        row = tabla.rowAt(pos.y())
        for item in acciones:
            if item is None:
                menu.addSeparator()
                continue
            texto, cb = item[0], item[1]
            enabled_fn = item[2] if len(item) > 2 else None
            act = QAction(texto, menu)
            if enabled_fn is not None:
                act.setEnabled(enabled_fn(row))
            act.triggered.connect(lambda checked=False, r=row, c=cb: c(r))
            menu.addAction(act)
        menu.exec_(tabla.viewport().mapToGlobal(pos))

    tabla.customContextMenuRequested.connect(_show_menu)
