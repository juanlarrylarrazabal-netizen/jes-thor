# 🧾 Gestor Facturas Pro — v8.0

Sistema profesional de gestión documental para facturas de proveedores.
Refactorización completa desde V6 (monolito Tkinter) a arquitectura modular con PyQt5.

---

## 🚀 Inicio rápido

```bat
# Primera instalación
INSTALAR.bat

# Arrancar
INICIAR.bat
```

**Credenciales por defecto:** `JESUS` / `admin1977`

---

## 🏗️ Arquitectura

```
gestor_v8/
├── core/              # Modelos, excepciones, logging, config
├── database/          # DatabaseManager SQLite (singleton)
├── ingest/            # IMAP universal (Gmail, Outlook, Yahoo...)
├── ocr/               # Pipeline PDF-first + Tesseract fallback
├── rules/             # Motor de reglas con prioridades y auditoría
├── classify/          # Pipeline completo de clasificación
├── watermark/         # Sello PDF idempotente con metadata
├── storage/           # Archivado en carpetas + backup
├── ui/                # PyQt5: splash, login, ventana principal, tabs
├── cli/               # Diagnóstico y comandos de línea
├── tests/             # Tests unitarios e integración
└── docs/              # Documentación
```

---

## ✨ Características principales

### Pipeline PDF-first
1. **Texto nativo**: PyMuPDF o pypdf extraen texto embebido → rápido, exacto
2. **OCR fallback**: Solo si el texto es insuficiente (`< 50 chars` por defecto)
3. **Extracción de campos**: NIF/CIF, nº factura, fecha, base, IVA, total, matrícula, bastidor

### Motor de reglas (prioridades)
| Prioridad | Método | Descripción |
|-----------|--------|-------------|
| 1ª | Nombre exacto | Nombre del proveedor encontrado en el texto |
| 2ª | CIF/NIF | CIF extraído coincide con proveedor en BD |
| 3ª/4ª | Keyword / Regex | Trigger configurado en tabla de reglas |
| Fallback | Manual | Sin coincidencia → diálogo de clasificación manual |

### IMAP universal
Funciona con cualquier servidor IMAP: Gmail, Outlook, Hotmail, Yahoo, etc.
Auto-detecta host y puerto por el dominio del email.
Reintentos con backoff exponencial. Deduplicación por SHA-256.

### Watermark idempotente
- Texto configurable: `Prv: {vendor_code} | Cta: {expense_account}`
- Detecta si ya está estampado (metadata `/GestProStamped`) → no duplica
- Posición, opacidad, color y páginas configurables en `config.yaml`

---

## ⚙️ Configuración

Toda la configuración está en `config.yaml`. Los secrets (contraseñas) van en `.env`.

```yaml
# Ejemplo .env
# Las cuentas de correo se gestionan desde la UI (Ajustes → Correo)
# No pongas contraseñas en config.yaml
```

**Variables de entorno:** `GESTOR__SECTION__KEY=valor`  
Ejemplo: `GESTOR__OCR__ENABLED=false`

---

## 🔌 CLI

```bash
# Diagnóstico del sistema
python -m cli.commands diagnostics

# Clasificar una factura
python -m cli.commands classify ruta/factura.pdf

# Estampar manualmente
python -m cli.commands stamp ruta/factura.pdf PRV-001 628000
```

---

## 🧪 Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## 📋 Cambios respecto a V6

| Aspecto | V6 (original) | V8 (refactorizado) |
|---------|--------------|-------------------|
| UI | Tkinter monolito | PyQt5 modular |
| Config | Hardcoded en config.py | config.yaml + .env |
| Correo | Solo Gmail, sin config host | IMAP universal, cualquier servidor |
| Watermark | En 3 sitios distintos | Un solo stamper.py idempotente |
| Reglas | Solo en BD | Motor de reglas con prioridades |
| Logging | print() | Logging estructurado con contexto por factura |
| Tests | Ninguno | Tests unitarios (extractor, reglas, watermark) |
| Duplicados | 5 archivos de licencias, 3 de impresión | 1 de cada |
| OCR | OCR siempre | PDF-first, OCR solo si necesario |

---

## 📄 ADRs (Architectural Decision Records)

### ADR-001: SQLite en lugar de PostgreSQL
**Decisión:** Mantener SQLite.  
**Motivo:** Un solo usuario en Windows. Sin acceso concurrente real. WAL mode cubre la robustez necesaria.  
**Trade-off:** No escala a multi-usuario. Si se necesita, migrar con `ATTACH` o `sqldump`.

### ADR-002: PDF-first con OCR fallback
**Decisión:** Extracción de texto nativo primero, OCR solo si `len(texto) < threshold`.  
**Motivo:** El 80% de las facturas son PDFs nativos. OCR añade 2-5s por página.  
**Trade-off:** Threshold configurable (default 50 chars). Si un PDF nativo da poco texto (headers), reducir el threshold.

### ADR-003: Motor de reglas determinista
**Decisión:** Reglas con prioridades explícitas, sin ML.  
**Motivo:** Auditabilidad total. El usuario debe saber por qué una factura se asignó a un proveedor.  
**Trade-off:** Requiere entrenar reglas manualmente para nuevos proveedores.

### ADR-004: Watermark idempotente con metadata PDF
**Decisión:** Añadir clave `/GestProStamped` en metadata del PDF.  
**Motivo:** Evitar doble estampado en reprocesos o reinicios.  
**Trade-off:** Si el PDF se edita externamente y se borra la metadata, se podría re-estampar.

### ADR-005: IMAP universal (no OAuth2)
**Decisión:** IMAP con contraseña de aplicación. OAuth2 como mejora futura.  
**Motivo:** Evitar dependencia de registros OAuth en Google/Microsoft. La contraseña de aplicación funciona sin configuración adicional.  
**Trade-off:** Contraseñas almacenadas en BD (sin cifrado a nivel de app). Mitigación: usar contraseñas de aplicación (no la contraseña principal de la cuenta).

---

## 🔐 Seguridad y GDPR

- Las contraseñas de usuarios se almacenan como SHA-256 (no reversible).
- Las contraseñas de cuentas de correo se almacenan en SQLite. Recomendación: cifrar el archivo de BD con SQLCipher en despliegues producción.
- Los logs no incluyen datos de facturas (solo nombres de archivo y hashes).
- El directorio de facturas temporales se limpia automáticamente (archivos >24h).

---

## 🗺️ Roadmap

- [ ] OAuth2 para Gmail/Outlook
- [ ] Visor PDF manual migrado a PyQt5 (actualmente usa Tkinter)
- [ ] Exportación a Excel del historial
- [ ] API REST opcional para integración con ERP
- [ ] Cifrado de BD con SQLCipher
