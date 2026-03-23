-- Migración: añadir campo cont_automatica
-- Ejecutar UNA VEZ contra facturas.db si la app no lo hace automáticamente

ALTER TABLE reglas_proveedor        ADD COLUMN cont_automatica INTEGER DEFAULT 0;
ALTER TABLE facturas_procesadas_v10 ADD COLUMN cont_automatica INTEGER DEFAULT 0;
