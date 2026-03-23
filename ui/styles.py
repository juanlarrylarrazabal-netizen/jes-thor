# -*- coding: utf-8 -*-
"""Estilos QSS centralizados para toda la aplicación."""

PALETTE_PRIMARY   = "#1F4E79"
PALETTE_ACCENT    = "#2563A8"
PALETTE_LIGHT     = "#EDF2F7"
PALETTE_BORDER    = "#CBD5E0"
PALETTE_TEXT      = "#2D3748"
PALETTE_TEXT_MUTED= "#718096"
PALETTE_SUCCESS   = "#276749"
PALETTE_SUCCESS_BG= "#C6F6D5"
PALETTE_DANGER    = "#C53030"
PALETTE_WARNING   = "#C05621"

BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {PALETTE_PRIMARY}; color: white;
        border: none; border-radius: 5px;
        padding: 7px 16px; font-weight: bold; font-size: 11px;
    }}
    QPushButton:hover {{ background-color: {PALETTE_ACCENT}; }}
    QPushButton:pressed {{ background-color: #1a3f63; }}
    QPushButton:disabled {{ background-color: #A0AEC0; color: #E2E8F0; }}
"""

BTN_SECONDARY = f"""
    QPushButton {{
        background-color: {PALETTE_LIGHT}; color: {PALETTE_TEXT};
        border: 1px solid {PALETTE_BORDER}; border-radius: 5px;
        padding: 7px 16px; font-size: 11px;
    }}
    QPushButton:hover {{ background-color: #E2E8F0; }}
    QPushButton:pressed {{ background-color: {PALETTE_BORDER}; }}
"""

BTN_DANGER = f"""
    QPushButton {{
        background-color: {PALETTE_DANGER}; color: white;
        border: none; border-radius: 5px; padding: 7px 16px; font-size: 11px;
    }}
    QPushButton:hover {{ background-color: #9B2C2C; }}
    QPushButton:pressed {{ background-color: #742A2A; }}
"""

TABLE = f"""
    QTableWidget {{
        border: 1px solid {PALETTE_BORDER};
        gridline-color: {PALETTE_LIGHT};
        background: white;
        alternate-background-color: #F7FAFC;
        selection-background-color: #BEE3F8;
        selection-color: #1A202C;
        font-size: 11px;
    }}
    QHeaderView::section {{
        background-color: {PALETTE_PRIMARY}; color: white;
        padding: 8px 6px; border: none;
        font-weight: bold; font-size: 10px;
        border-right: 1px solid {PALETTE_ACCENT};
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QTableWidget::item:selected {{ background: #BEE3F8; color: #1A202C; }}
"""

TABS = f"""
    QTabWidget::pane {{
        border: none; background: #F5F7FA;
    }}
    QTabBar::tab {{
        padding: 10px 20px; background: #E2E8F0; color: {PALETTE_TEXT_MUTED};
        border: none; font-size: 11px; font-weight: 500;
        border-right: 1px solid {PALETTE_BORDER};
        min-width: 120px;
    }}
    QTabBar::tab:selected {{
        background: {PALETTE_PRIMARY}; color: white; font-weight: bold;
    }}
    QTabBar::tab:hover:!selected {{ background: #BEE3F8; color: {PALETTE_TEXT}; }}
"""

GROUPBOX = f"""
    QGroupBox {{
        font-weight: bold; font-size: 11px; color: {PALETTE_TEXT};
        border: 1px solid {PALETTE_BORDER};
        border-radius: 6px; margin-top: 8px; padding-top: 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px; padding: 0 4px;
    }}
"""

INPUT = f"""
    QLineEdit {{
        border: 1px solid {PALETTE_BORDER}; border-radius: 5px;
        padding: 5px 10px; background: white; color: {PALETTE_TEXT};
        font-size: 11px;
    }}
    QLineEdit:focus {{ border: 2px solid {PALETTE_ACCENT}; }}
    QLineEdit:disabled {{ background: {PALETTE_LIGHT}; color: {PALETTE_TEXT_MUTED}; }}
"""

COMBOBOX = f"""
    QComboBox {{
        border: 1px solid {PALETTE_BORDER}; border-radius: 5px;
        padding: 5px 10px; background: white; font-size: 11px;
    }}
    QComboBox:focus {{ border: 2px solid {PALETTE_ACCENT}; }}
"""

LOG_CONSOLE = """
    QTextEdit {
        background: #1A202C; color: #68D391;
        border: none; font-family: 'Consolas', 'Courier New', monospace;
        font-size: 9px;
    }
"""

MENUBAR = f"""
    QMenuBar {{ background: {PALETTE_PRIMARY}; color: white; font-size: 11px; }}
    QMenuBar::item:selected {{ background: {PALETTE_ACCENT}; }}
    QMenu {{ background: white; border: 1px solid {PALETTE_BORDER}; }}
    QMenu::item:selected {{ background: #BEE3F8; color: {PALETTE_TEXT}; }}
"""

STATUSBAR = f"""
    QStatusBar {{
        background: {PALETTE_PRIMARY}; color: white;
        font-size: 10px; padding: 3px 10px;
    }}
"""

SCROLLBAR = f"""
    QScrollBar:vertical {{
        border: none; background: {PALETTE_LIGHT}; width: 8px;
    }}
    QScrollBar::handle:vertical {{
        background: {PALETTE_BORDER}; border-radius: 4px; min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {PALETTE_ACCENT}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""
