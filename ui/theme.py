# -*- coding: utf-8 -*-
"""
ui/theme.py — F-FIX: Gestión centralizada de temas (Claro / Oscuro / Auto).
Aplica QPalette global que cumple contraste WCAG AA.
"""
from __future__ import annotations
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt

PALETTE_CLARO = {
    "Window":          "#FFFFFF",
    "WindowText":      "#1A202C",
    "Base":            "#FFFFFF",
    "AlternateBase":   "#F7FAFC",
    "Text":            "#1A202C",
    "BrightText":      "#FFFFFF",
    "Button":          "#EDF2F7",
    "ButtonText":      "#1A202C",
    "Highlight":       "#1F4E79",
    "HighlightedText": "#FFFFFF",
    "ToolTipBase":     "#FFFBEB",
    "ToolTipText":     "#1A202C",
    "Link":            "#2B6CB0",
    "Disabled_Text":   "#A0AEC0",
    "Disabled_ButtonText": "#A0AEC0",
}

PALETTE_OSCURO = {
    "Window":          "#1A202C",
    "WindowText":      "#F7FAFC",
    "Base":            "#2D3748",
    "AlternateBase":   "#1A202C",
    "Text":            "#F7FAFC",
    "BrightText":      "#FFFFFF",
    "Button":          "#2D3748",
    "ButtonText":      "#F7FAFC",
    "Highlight":       "#3182CE",
    "HighlightedText": "#FFFFFF",
    "ToolTipBase":     "#2D3748",
    "ToolTipText":     "#F7FAFC",
    "Link":            "#63B3ED",
    "Disabled_Text":   "#718096",
    "Disabled_ButtonText": "#718096",
}

_ROLE_MAP = {
    "Window":          QPalette.Window,
    "WindowText":      QPalette.WindowText,
    "Base":            QPalette.Base,
    "AlternateBase":   QPalette.AlternateBase,
    "Text":            QPalette.Text,
    "BrightText":      QPalette.BrightText,
    "Button":          QPalette.Button,
    "ButtonText":      QPalette.ButtonText,
    "Highlight":       QPalette.Highlight,
    "HighlightedText": QPalette.HighlightedText,
    "ToolTipBase":     QPalette.ToolTipBase,
    "ToolTipText":     QPalette.ToolTipText,
    "Link":            QPalette.Link,
}


def _build_palette(colors: dict) -> QPalette:
    pal = QPalette()
    for name, hex_color in colors.items():
        if name.startswith("Disabled_"):
            role_name = name[len("Disabled_"):]
            role = _ROLE_MAP.get(role_name)
            if role is not None:
                pal.setColor(QPalette.Disabled, role, QColor(hex_color))
        else:
            role = _ROLE_MAP.get(name)
            if role is not None:
                col = QColor(hex_color)
                pal.setColor(QPalette.Active,   role, col)
                pal.setColor(QPalette.Inactive, role, col)
    return pal


def apply_theme(app: QApplication = None, tema: str = "claro") -> None:
    """
    Aplica el tema de color a la aplicación Qt completa.
    tema: 'claro' | 'oscuro' | 'auto'
    """
    if app is None:
        app = QApplication.instance()
    if app is None:
        return

    if tema == "auto":
        # Detectar por el fondo por defecto del sistema
        system_bg = app.style().standardPalette().color(QPalette.Window)
        luminance  = 0.299*system_bg.redF() + 0.587*system_bg.greenF() + 0.114*system_bg.blueF()
        tema = "oscuro" if luminance < 0.5 else "claro"

    colors = PALETTE_OSCURO if tema == "oscuro" else PALETTE_CLARO
    pal = _build_palette(colors)
    app.setPalette(pal)

    # Stylesheet global que fuerza contraste en ComboBox, QMenu, QLabel
    if tema == "oscuro":
        qss = """
            QComboBox, QComboBox QAbstractItemView { color: #F7FAFC; background: #2D3748; border: 1px solid #4A5568; }
            QMenu { color: #F7FAFC; background: #2D3748; }
            QMenu::item:selected { background: #3182CE; color: white; }
            QToolTip { color: #F7FAFC; background: #2D3748; border: 1px solid #4A5568; }
            QLabel { color: #F7FAFC; }
            QPushButton { color: #F7FAFC; background: #2D3748; border: 1px solid #4A5568; border-radius: 4px; padding: 5px; }
            QPushButton:hover { background: #3182CE; }
            QLineEdit, QTextEdit { color: #F7FAFC; background: #2D3748; border: 1px solid #4A5568; }
            QTabBar::tab { color: #F7FAFC; background: #2D3748; padding: 6px 12px; }
            QTabBar::tab:selected { background: #1F4E79; color: white; }
            QGroupBox { color: #F7FAFC; }
            QCheckBox { color: #F7FAFC; }
        """
    else:
        qss = """
            QComboBox, QComboBox QAbstractItemView { color: #1A202C; background: #FFFFFF; }
            QMenu { color: #1A202C; background: #FFFFFF; }
            QMenu::item:selected { background: #1F4E79; color: white; }
            QToolTip { color: #1A202C; background: #FFFBEB; }
            QLabel { color: #1A202C; }
        """
    app.setStyleSheet(qss)


def load_and_apply_theme(db=None, app: QApplication = None) -> None:
    """Carga el tema guardado en BD y lo aplica al arrancar la app."""
    tema = "claro"
    if db:
        try: tema = db.get_config_ui("ui_tema", "claro")
        except Exception: pass
    apply_theme(app, tema)
