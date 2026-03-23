# CHECKLIST V1 — 2026-03-12

## H1 — Horizontal se ve igual que Acrobat
- [x] Sin auto-detección de orientación en _abrir_pdf
- [x] _render_page usa solo page.rotation + _user_rot
- [ ] Test funcional (requiere PyQt5)

## H2 — Girar manual + coords alineadas + regla persiste
- [x] _rotate_view modifica _user_rot (no reseteado en _render_page)
- [x] Coords guardadas en espacio visual; OCR en espacio PDF (rot_inv)
- [x] rot_entrenamiento guardado en campos_regla_v13
- [x] Al abrir con proveedor_id: _user_rot[0] restaurado
- [ ] Test funcional

## H3 — Proveedor nuevo escribible
- [x] inp_prov_nombre QLineEdit libre
- [x] _guardar() crea nuevo proveedor si nombre ≠ combo
- [ ] Test funcional

## H4 — Trigger en Campo Activo
- [x] Radio-botón "🎯 TRIGGER" en grupo Campo Activo
- [x] _on_trigger_rb activa _trigger_capture_mode
- [x] Botón "Probar trigger" + highlight canvas
- [ ] Test funcional

## H5 — Abrir en visor Historial/Descargas
- [x] _abrir_visor retry con ruta reparada
- [x] _buscar_archivo_manualmente en visor (segundo nivel)
- [ ] Test funcional

## H6 — Gemini 2.5-flash
- [x] ia/cliente.py default = gemini-2.5-flash
- [x] tab_ia.py: 2.5-flash primero + botón probar conexión
- [x] Botón "🤖 Ayuda IA" en panel reglas
- [ ] Test funcional (requiere API key)

## Sin regresiones
- [x] tab_informes, rules/engine, watermark/stamper: sin cambios
- [x] Todos los archivos modificados: SYNTAX OK
