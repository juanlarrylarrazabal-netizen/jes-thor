-- ============================================================
-- MIGRACIÓN V10 — Gestor Facturas Pro
-- Ejecutar SOLO si se actualiza desde una V9 existente.
-- La aplicación realiza estas migraciones automáticamente
-- en el arranque, pero este script permite ejecutarlas
-- manualmente si es necesario.
-- ============================================================

-- 1. Tabla de facturas procesadas con datos financieros
CREATE TABLE IF NOT EXISTS facturas_procesadas_v10 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_proveedor            INTEGER,
    fecha                   TEXT,
    ruta_pdf                TEXT,
    base_imponible          REAL DEFAULT 0,
    iva                     REAL DEFAULT 0,
    total                   REAL DEFAULT 0,
    tipo_factura            TEXT,
    cuenta_gasto            TEXT,
    categoria               TEXT,
    numero_factura          TEXT,
    procesada_desde_correo  INTEGER DEFAULT 0,
    numero_proveedor        TEXT,
    origen_correo           TEXT,
    id_mensaje_unico        TEXT,
    hash_pdf                TEXT UNIQUE,
    fecha_procesado         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nombre_proveedor        TEXT,
    cif_proveedor           TEXT,
    FOREIGN KEY (id_proveedor) REFERENCES proveedores(id)
);

-- 2. Tabla de mensajes de correo descargados
CREATE TABLE IF NOT EXISTS email_mensajes_v10 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      TEXT UNIQUE NOT NULL,
    cuenta_email    TEXT,
    asunto          TEXT,
    remitente       TEXT,
    fecha_correo    TEXT,
    fecha_descarga  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    num_adjuntos    INTEGER DEFAULT 0,
    procesado       INTEGER DEFAULT 0
);

-- 3. Añadir columnas financieras al historial (si no existen)
ALTER TABLE historial_procesado ADD COLUMN base_imponible REAL DEFAULT 0;
ALTER TABLE historial_procesado ADD COLUMN iva REAL DEFAULT 0;
ALTER TABLE historial_procesado ADD COLUMN total REAL DEFAULT 0;
ALTER TABLE historial_procesado ADD COLUMN cif_proveedor TEXT;
ALTER TABLE historial_procesado ADD COLUMN categoria TEXT;
ALTER TABLE historial_procesado ADD COLUMN ruta_pdf TEXT;
ALTER TABLE historial_procesado ADD COLUMN id_mensaje_unico TEXT;
ALTER TABLE historial_procesado ADD COLUMN origen_correo TEXT;

-- 4. Añadir columnas SMTP a cuentas_gmail
ALTER TABLE cuentas_gmail ADD COLUMN fecha_ultimo_escaneo TEXT;
ALTER TABLE cuentas_gmail ADD COLUMN smtp_host TEXT DEFAULT '';
ALTER TABLE cuentas_gmail ADD COLUMN smtp_port INTEGER DEFAULT 587;

-- ============================================================
-- NOTA: Los ALTER TABLE pueden fallar con "duplicate column name"
-- si la columna ya existe. Esto es normal y se puede ignorar.
-- ============================================================
