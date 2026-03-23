-- MIGRACIÓN V1 — Gestor Facturas Pro
-- Ejecutar solo si actualizas desde una instalación anterior a V15.
-- Las migraciones se aplican automáticamente al arrancar la app.
-- Este script es solo para aplicación manual en caso de error.

-- Añadir ruta_archivo_final a historial si no existe
ALTER TABLE historial_procesado ADD COLUMN ruta_archivo_final TEXT;

-- Añadir ruta_archivo_final y base_imponible a facturas_procesadas si no existen
ALTER TABLE facturas_procesadas_v10 ADD COLUMN ruta_archivo_final TEXT;
ALTER TABLE facturas_procesadas_v10 ADD COLUMN base_imponible REAL;

-- Actualizar ruta_archivo_final desde ruta_pdf donde esté vacía
UPDATE historial_procesado
SET ruta_archivo_final = ruta_pdf
WHERE ruta_archivo_final IS NULL AND ruta_pdf IS NOT NULL;

UPDATE facturas_procesadas_v10
SET ruta_archivo_final = ruta_pdf
WHERE ruta_archivo_final IS NULL AND ruta_pdf IS NOT NULL;
