# CHANGELOG — GESTOR FACTURAS PRO v1 — 2026-03-13 (iteración 6)

## A — Proveedor variable: selección de regla con ranking formal (rules/engine.py)
- `_match_variable_providers` reescrito por completo.
- Scoring formal: trigger exacto boundary +100, parcial +60, serie en OCR +30,
  tipo factura (RECT/proforma/pedido) +20, prioridad de regla +priority.
- Logs completos: `VAR-RANK regla=N vendor=X trigger=Y score=Z`.
- Reglas sin trigger/serie/tipo solo se usan como fallback de último recurso (score=1).
- Empate → `needs_manual=True` para diálogo de desambiguación en visor.
- `result.candidates` lleva `(score, rule, vendor)` para el diálogo.

## B — Informes rotos: flujo BD→Excel reparado
- `database/manager.py`:
  - Nuevas columnas en migración `facturas_procesadas_v10`:
    `serie_factura`, `cuenta_proveedor`, `subcuenta_proveedor`, `subcuenta_gasto`,
    `impresa`, `impresa_en`.
  - `registrar_factura_v10` acepta todos los nuevos campos en su lista `cols`.
  - Nuevo método `reconstruir_informes_backfill()`: rellena campos faltantes
    cruzando `historial_procesado` + `proveedores` para facturas antiguas.
- `classify/classifier.py`: pasa `serie_factura`, `cuenta_proveedor`,
  `subcuenta_proveedor`, `subcuenta_gasto` al llamar a `registrar_factura_v10`.
- `excel/excel_resumen.py`: rediseño a 18 columnas:
  Fecha | Proveedor | Nº Prov. | CIF | Cta.Prov. | Subcta.Prov. |
  Base | IVA | Total | Tipo Coste | Cta.Gasto | Subcta.Gasto |
  Nº Factura | Serie | Rect. | Impresa | Tipo | Ruta PDF.
  Eliminadas las columnas duplicadas (bug: cols 8-11 escritas dos veces).
- `ui/tabs/tab_ajustes.py`: pestaña "🔧 Reconstruir" con botón backfill.

## C — UnboundLocalError _serie (ya corregido iter.5, confirmado)
- `_serie` inicializado en líneas 178-182, antes de `resolve_invoice_number`.

## D — QTextEdit→QLineEdit inp_trigger (ya corregido iter.5, confirmado)
- `inp_trigger = QLineEdit()`, sin `toPlainText`/`setPlainText`.

## E/F — Cuenta/subcuenta + Watermark (ya aplicado iter.5, confirmado)
- Cols en `proveedores` y `reglas_proveedor` y `facturas_procesadas_v10`.
- `stamp_pdf` recibe `cuenta_proveedor`, `subcuenta_proveedor`, `subcuenta_gasto`.
- Líneas 1+2 de la marca de agua muestran cuentas contables en rojo.

## G/H — Historial: botón único de impresión (ya aplicado iter.5, confirmado)
- Un solo botón "🖨️ Imprimir seleccionadas…".
- Imports desde `PyQt5.QtPrintSupport`.

## Archivos modificados (iter.6)
- `rules/engine.py`
- `database/manager.py`
- `classify/classifier.py`
- `excel/excel_resumen.py`
- `ui/tabs/tab_ajustes.py`
