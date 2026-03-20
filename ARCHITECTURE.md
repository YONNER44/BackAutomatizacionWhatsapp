# Arquitectura del Sistema

## Visión general

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Distribuidoras                                                 │
│   (WhatsApp)    ──► WhatsApp Web ──► Node.js ──► Backend        │
│                     (celular)        :3000        :8000          │
│                                                                  │
│              ┌────────────────────────────────────┐             │
│              │     Backend FastAPI (Python)        │             │
│              │         localhost:8000              │             │
│              └────────────────────────────────────┘             │
│                    │              │              │               │
│                    ▼              ▼              ▼               │
│              SQLite/PG      Excel local    Google Sheets         │
│                                                                  │
│   Panel React ──────────────► Backend                           │
│   localhost:5173               :8000                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo de procesamiento de mensajes

```
Distribuidora
    │
    │  Envía mensaje WhatsApp (texto o imagen)
    ▼
WhatsApp Web (celular vinculado)
    │
    │  whatsapp-web.js captura el mensaje
    ▼
Node.js Service (localhost:3000)
    │
    │  POST /api/webhook/whatsapp-web
    │  { from, type, body, hasMedia, media:{data,mimetype} }
    ▼
webhook.py :: receive_message_whatsapp_web()
    │
    ├─► Limpiar sufijos (@c.us, @lid, @s.whatsapp.net)
    ├─► Verificar duplicados por whatsapp_message_id
    ├─► Normalizar número (E.164 ↔ 10 dígitos locales)
    ├─► Buscar proveedor en BD → si no existe: ignorar
    ├─► Crear registro Message (status=RECEIVED)
    └─► Lanzar background task: process_message()

process_message() [background]
    │
    ├─ Si TEXT ──────────────────────────────────────────────────┐
    │                                                            │
    └─ Si IMAGE                                                  │
           │                                                     │
           └─► Decodificar base64 → bytes                       │
               OCRService.extract_text_from_bytes()  ───────────┘
               (OpenAI GPT-4o-mini Vision)
                                                    │
                                              text_to_parse
                                                    │
                                                    ▼
                                    AIParserService.parse_prices(text)
                                    (OpenAI GPT-4o-mini / fallback regex)
                                                    │
                                                    ▼
                                    Upsert Price[] en BD
                                    (actualiza si ya existe proveedor+medicamento)
                                                    │
                                     ┌──────────────┴──────────────┐
                                     ▼                             ▼
                              ExcelService                  SheetsService
                              update_prices()               update_prices()
                              (archivo local)          (Google Sheets, opcional)
                                                    │
                                                    ▼
                                      Message.status = PROCESSED
```

---

## Modelos de datos

```
providers
─────────────────────────────
id              INTEGER PK
phone_number    VARCHAR(20) UNIQUE
name            VARCHAR(100)
is_active       BOOLEAN  DEFAULT TRUE
created_at      DATETIME
updated_at      DATETIME

messages
─────────────────────────────
id                    INTEGER PK
whatsapp_message_id   VARCHAR(100) UNIQUE
provider_id           INTEGER FK → providers
phone_number          VARCHAR(20)
message_type          ENUM('text','image')
raw_text              TEXT
image_url             VARCHAR(500)
extracted_text        TEXT
status                ENUM('received','processing','processed','failed')
error_message         TEXT
received_at           DATETIME
processed_at          DATETIME

prices
─────────────────────────────
id               INTEGER PK
message_id       INTEGER FK → messages
provider_id      INTEGER FK → providers
medication_name  VARCHAR(200)
price            FLOAT
unit             VARCHAR(50)
date_reported    DATE
created_at       DATETIME
```

---

## Servicios internos

| Servicio | Archivo | Responsabilidad |
|---|---|---|
| `OCRService` | `services/ocr.py` | Extrae texto de imágenes usando OpenAI GPT-4o-mini Vision. |
| `AIParserService` | `services/ai_parser.py` | Estructura medicamentos y precios desde texto libre usando OpenAI GPT-4o-mini. Incluye parser regex como fallback. |
| `ExcelService` | `services/excel.py` | Mantiene un archivo `.xlsx` local con la matriz precios (filas=medicamentos, columnas=proveedores), organizado por hojas mensuales. Resalta en verde el menor precio. |
| `SheetsService` | `services/sheets.py` | Replica la misma matriz en Google Sheets. Usa fuzzy matching (80%) para medicamentos con nombre ligeramente distinto. |

---

## Endpoints de la API

### Health

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Estado de la aplicación |
| GET | `/health` | Health check básico |

### Webhook WhatsApp Web

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/webhook/whatsapp-web` | Recibir mensajes desde el servicio Node.js |

### Proveedores

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/providers` | Listar todos los proveedores |
| POST | `/providers` | Crear proveedor |
| GET | `/providers/{id}` | Obtener proveedor por ID |
| PUT | `/providers/{id}` | Actualizar proveedor |
| DELETE | `/providers/{id}` | Eliminar proveedor |

### Precios

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/prices` | Listar precios (filtros: provider_id, medication, date_from, date_to, limit) |
| GET | `/prices/summary` | Estadísticas: total precios, medicamentos, estado Excel |
| GET | `/prices/export/excel` | Descargar el Excel generado desde la BD |
| DELETE | `/prices/{id}` | Eliminar un registro de precio |

---

## Decisiones de diseño

### Procesamiento asíncrono en background
Los mensajes se reciben y registran en BD de forma inmediata, mientras el procesamiento pesado (OCR + IA + Excel) ocurre en segundo plano. Esto evita bloquear la respuesta HTTP al servicio Node.js.

### Normalización de número telefónico
Los proveedores pueden estar registrados con 10 dígitos locales o con prefijo internacional (E.164). El sistema busca ambos formatos en cada mensaje entrante.

### Upsert de precios
Cuando la misma distribuidora envía su lista actualizada, el sistema actualiza el precio existente del medicamento en lugar de acumular duplicados. Mantiene un único precio vigente por par `proveedor + medicamento`.

### Fallback del parser IA
Si OpenAI no está disponible, el sistema usa expresiones regulares para extraer precios en formatos colombianos comunes (`*36.450*`, `Aspirina 500mg: $8.500`).

### Excel mensual
El archivo Excel organiza los precios en hojas por mes (`YYYY-MM`). El precio más bajo de cada medicamento se resalta en verde para facilitar la comparación visual.
