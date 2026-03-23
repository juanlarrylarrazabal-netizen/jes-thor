# INFORME TÉCNICO V1 — FINAL — 2026-03-12

## 1. Orientación: eliminada al 100%
`_abrir_pdf()` = solo `_user_rot = {}`. Render = `page.rotation + user_rot`. Sin heurísticas.

## 2. Marca de agua: rotación manual + zona blanca girada
- `detect_rotation()` ahora es trivial: devuelve `user_rot` (0 si no se pasa).
- `find_white_zone_rotated(page, user_rot)`: renderiza con `total_rot = page.rotation + user_rot`, busca zona blanca en la imagen visual, convierte coords de vuelta al espacio PDF con la rotación inversa del user_rot.
- `stamp_pdf(user_rot_pages)`: usa `find_white_zone_rotated` por página.

## 3. Coordenadas OCR con rotación manual
`ocr_zona(user_rot)` = solo rotación manual. Inversa aplicada para get_text() (espacio post-page.rotation). Tesseract = `page.rotation + user_rot` para imagen idéntica a pantalla.

## 4. Consola IA (D)
Tab "🧠 IA" en panel derecho: selector Gemini/Ollama, cuadro libre, botón Ejecutar → JSON no destructivo → botones "Aplicar trigger/proveedor/campos". Solo pasa OCR+metadata, nunca el PDF.

## 5. Gemini 2.5-flash + Ollama (E)
`GeminiClient` default=`gemini-2.5-flash`. `OllamaClient` nuevo con REST a `http://localhost:11434`, configurable. Tab "🦙 Ollama Local" en Ajustes → IA.

## 6. Proveedor editable + Trigger en Campo Activo (C)
`inp_prov_nombre` libre. Radio "🎯 TRIGGER" en grupo Campo Activo activa captura.

## 7. Rutas (F)
Retry en `_abrir_visor()` tras `_reparar_ruta()`. Visor: `_buscar_archivo_manualmente()`.

## Archivos modificados
- `modulos/visor_pdf_manual.py` — A, C, D
- `watermark/stamper.py` — B
- `ia/cliente.py` — E (OllamaClient + ejecutar_instruccion)
- `ui/tabs/tab_ia.py` — E (pestaña Ollama)
- `ui/tabs/tab_historial.py` — F (ya aplicado)
