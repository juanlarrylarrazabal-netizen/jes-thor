# CHANGELOG — GESTOR FACTURAS PRO

## v1.0-REPARADO — 2026-03-13

### B) Motor de reglas variable — ranking real (CRÍTICO)
- **CAUSA**: `Rule` dataclass no tenía campo `serie`, por lo que `_match_variable_providers`
  lanzaba `AttributeError: 'Rule' object has no attribute 'serie'` en cada factura de
  proveedor variable → NINGUNA factura variable se clasificaba.
- **CAUSA SECUNDARIA**: La guarda regex usaba `rule.rule_type == RuleType.REGEX if hasattr(...) else False`
  que siempre evaluaba `False` → las reglas regex de variables nunca se aplicaban.
- **FIX**: `core/models.py` — añadido `serie: str = ""` y `subcuenta_gasto: str = ""` a `Rule`.
- **FIX**: `rules/engine.py` — `RuleEngine.__init__` carga `serie` y `subcuenta_gasto` desde BD.
- **FIX**: `_match_variable_providers` reescrito limpio: guarda regex correcta
  (`is_regex = rule.rule_type == RuleType.REGEX`), sin dependencia de `rule.serie` separado del trigger.
- **COMPORTAMIENTO**: Ranking por score (exacto +100, parcial +60, tipo +20, prioridad +N).
  Empate → `needs_manual=True`. Sin match → fallback → visor automático.

### C) Informes — flujo procesado → BD → informes (CRÍTICO)
- **CAUSA**: `historial_procesado` se creaba sin `ruta_archivo_final`, `impresa`,
  `id_regla_aplicada`, `es_rectificativa`, `numero_factura_manual` → la migración los añadía
  pero si la BD existía de una sesión anterior sin migración las inserciones fallaban silenciosamente.
- **FIX**: `database/manager.py` — `CREATE TABLE historial_procesado` incluye todas las columnas
  desde el inicio (idempotente con `IF NOT EXISTS`).
- Las queries de informes (gastos=6xx, compras=3/4xx, base_imponible) estaban correctas
  en la BD y en `tab_informes.py` — el flujo completo funciona una vez resuelta la BD.

### D) Variable no inicializada `_serie` (CRÍTICO)
- **CAUSA REAL**: Antes del fix-B, el crash en `_match_variable_providers` interrumpía el
  pipeline antes de inicializar `_serie`, dejando el clasificador en estado indefinido.
- **FIX**: Con el fix-B resuelto, el pipeline llega siempre a la inicialización `_serie = ""`.
  No era una variable no inicializada per se: era un crash previo que simulaba el síntoma.

### E) inp_trigger — ya era QLineEdit (sin cambio necesario)
- Confirmado: `inp_trigger = QLineEdit()` desde la versión entregada. No había regresión.

### F) Campos contables cuenta_proveedor / subcuenta (sin cambio)
- `ventana_proveedor.py`: campos `e_cuenta_prv` y `e_subcuenta_prv` presentes.
- `classifier.py`: lee y graba `cuenta_proveedor`, `subcuenta_proveedor`, `subcuenta_gasto`.
- `watermark/stamper.py`: líneas L1/L2 con cuenta_proveedor/subcuenta_gasto.

### G) Marca de agua — roja, sin recuadro, con giro (sin cambio)
- Color `(1.0, 0.0, 0.0)` confirmado. `user_rot` propagado a cada bloque. Sin fondo.

### H) Historial — un solo botón imprimir (sin cambio)
- Un único `QPushButton("🖨️ Imprimir seleccionadas…")`. `QtPrintSupport` importado correctamente.

### I) Renombrado — precedencia Manual > Regla > IA > OCR (sin cambio)
- `resolve_invoice_number` en `storage/filesystem.py` verifica precedencia correcta.

### J) Rutas — "Abrir en visor" con reparación (sin cambio)
- `_resolve_ruta()` en `tab_historial.py` ofrece buscar si el archivo no existe y actualiza BD.

### K) Exportar/Importar y Escáner (sin cambio)
- Módulos intactos y no interfieren con BD ni rutas.
