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
│                                         (fuente principal)       │
│                                                                  │
│   Panel React ──────────────► Backend                           │
│   localhost:5173               :8000                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo de negocio diario

```
Cada mañana:
  Dueño agrega medicamentos del día en Google Sheets (hoja YYYY-MM)
      │
      ▼
  Dueño envía la lista a proveedores por WhatsApp
      │
      ▼
  Proveedores responden con precios por WhatsApp
      │
      ▼
  Sistema captura, filtra y registra SOLO los medicamentos
  que ya están en la hoja — los nuevos son ignorados
```

---

## Flujo de procesamiento de mensajes

```
Distribuidora
    │
    │  Envía mensaje WhatsApp (texto o imagen con lista de precios)
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
                                    ┌─ FILTRADO POR HOJA MENSUAL ──────────┐
                                    │  Lee medicamentos de Google Sheets   │
                                    │  Solo pasan los que ya están en la   │
                                    │  hoja del mes actual (fuzzy match)   │
                                    │  Los nuevos son ignorados y logueados│
                                    └──────────────────────────────────────┘
                                                    │
                                                    ▼
                                    Upsert Price[] en BD
                                    (actualiza si ya existe proveedor+medicamento)
                                                    │
                                     ┌──────────────┴──────────────┐
                                     ▼                             ▼
                              ExcelService                  SheetsService
                              update_prices()               update_prices()
                              (archivo local)          (Google Sheets, principal)
                                                    │
                                                    ▼
                                      Message.status = PROCESSED
```

---

## Inicialización mensual automática

Al arrancar y cada hora, un watchdog en background verifica si existe la hoja del mes actual:

```
main.py startup
    │
    └─► asyncio.create_task(_monthly_sheet_watchdog())
              │
              │  cada 3600 segundos
              ▼
         _try_init_monthly_sheet()
              │
              ├─► Si no existe hoja en Excel local → crear
              └─► Si no existe hoja en Google Sheets → crear
                  (con los proveedores activos, sin medicamentos)
```

La creación manual también está disponible vía `POST /prices/init-month` desde el Dashboard.

---

## Formato de la hoja mensual

```
Fila 1:  [Fecha+Med+P1+C1 fusionadas → Proveedor A] [P2+C2 → Proveedor B] ...
Fila 2:  Fecha | Medicamento | Precio | Cantidad | Precio | Cantidad | ...
Fila 3+: 24/03/2026 | Aspirina 500mg | 7800 | caja | 7500 | caja | ...
```

- Cada proveedor ocupa **2 columnas**: Precio + Cantidad
- La hoja se crea **vacía** (sin medicamentos); se llenan cuando los proveedores envían precios
- El precio más bajo por medicamento se resalta en **verde** automáticamente

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
| `AIParserService` | `services/ai_parser.py` | Estructura medicamentos y precios desde texto libre usando OpenAI GPT-4o-mini. Incluye parser regex como fallback para formatos colombianos. |
| `ExcelService` | `services/excel.py` | Mantiene un archivo `.xlsx` local con la matriz de precios organizada en hojas mensuales (2 columnas por proveedor: Precio + Cantidad). Resalta en verde el menor precio. |
| `SheetsService` | `services/sheets.py` | Replica la misma matriz en Google Sheets (fuente principal). Usa fuzzy matching de 3 niveles (exacto → palabras → similitud 80%) para medicamentos con nombre ligeramente distinto. Filtra medicamentos no listados. |

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
| GET | `/prices/summary` | Estadísticas: total precios, medicamentos, estado Sheets/Excel |
| POST | `/prices/init-month` | Crear hoja del mes actual en Google Sheets y Excel (param: `force`) |
| GET | `/prices/export/excel` | Descargar el Excel generado desde la BD |
| DELETE | `/prices/{id}` | Eliminar un registro de precio |

---

## Decisiones de diseño

### Solo se registran medicamentos de la lista del dueño
El sistema **no agrega medicamentos nuevos** que provengan de los proveedores. Cada mañana el dueño llena la hoja mensual con los medicamentos que necesita cotizar. Cuando los proveedores responden, solo se actualizan los precios de los medicamentos ya listados — cualquier medicamento extra enviado por el proveedor es ignorado silenciosamente.

### Procesamiento asíncrono en background
Los mensajes se reciben y registran en BD de forma inmediata, mientras el procesamiento pesado (OCR + IA + Excel + Sheets) ocurre en segundo plano. Esto evita bloquear la respuesta HTTP al servicio Node.js.

### Normalización de número telefónico
Los proveedores pueden estar registrados con 10 dígitos locales o con prefijo internacional (E.164). El sistema busca ambos formatos en cada mensaje entrante.

### Upsert de precios
Cuando la misma distribuidora envía su lista actualizada, el sistema actualiza el precio existente del medicamento en lugar de acumular duplicados. Mantiene un único precio vigente por par `proveedor + medicamento`.

### Fuzzy matching de medicamentos (3 niveles)
1. **Exacto** (case-insensitive): `"aspirina 500mg"` = `"Aspirina 500mg"`
2. **Subconjunto de palabras**: `"dipirona"` coincide con `"dipirona 500mg"`
3. **Similitud por caracteres** (umbral 80%): `"aspiria"` → `"aspirina"` (maneja typos)

### Fallback del parser IA
Si OpenAI no está disponible, el sistema usa expresiones regulares para extraer precios en formatos colombianos comunes (`*36.450*`, `Aspirina 500mg: $8.500`).

### Hoja mensual con watchdog
Al inicio del mes el sistema crea automáticamente la hoja con el formato y los proveedores activos (sin medicamentos). Un watchdog en background revisa cada hora si hay que crear la hoja, por si el servidor arranca a mitad de mes.

### Google Sheets como fuente principal
Cuando `GOOGLE_SHEET_ID` está configurado, Google Sheets es la fuente de verdad para verificar medicamentos y hojas existentes. El Excel local es una copia secundaria para descarga offline.
