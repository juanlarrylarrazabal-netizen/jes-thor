# -*- coding: utf-8 -*-
"""Utilidades compartidas — parse_es_float centralizado."""
from __future__ import annotations
from typing import Optional


def parse_es_float(raw: str) -> float:
    """
    Convierte número español/internacional a float.
    Soporta: '1.234,56' '1,234.56' '1234,56' '-102,00' '-3.976,00'
    Lanza ValueError si no puede convertir.
    """
    if not raw:
        raise ValueError("cadena vacía")
    s = raw.strip()
    negativo = s.startswith('-')
    s = s.lstrip('-').replace('€', '').replace(' ', '').strip()
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')   # español: 1.234,56
        else:
            s = s.replace(',', '')                      # anglosajón: 1,234.56
    elif ',' in s:
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(',', '.')                     # decimal: 102,00
        else:
            s = s.replace(',', '')                      # millar: 1,234
    result = float(s)
    return -result if negativo else result


def parse_es_float_safe(raw: str, default: float = 0.0) -> float:
    """Como parse_es_float pero devuelve default en lugar de excepción."""
    try:
        return parse_es_float(raw)
    except (ValueError, TypeError, AttributeError):
        return default
