# BackAutomatizacionWhatsapp

Backend del sistema de automatización de recolección de precios de medicamentos vía WhatsApp Web.

## Tecnologías

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Framework web | FastAPI | 0.115.6 |
| Servidor ASGI | Uvicorn | 0.34.0 |
| Lenguaje | Python | 3.11 |
| ORM / BD async | SQLAlchemy + asyncpg | 2.0.36 / 0.31.0 |
| IA / OCR | OpenAI GPT-4o-mini | 1.66.3 |
| Google Sheets | gspread | 6.1.4 |
| Excel local | openpyxl | 3.1.5 |
| Servicio WhatsApp | whatsapp-web.js (Node.js) | 1.23.0 |
| Base de datos prod | PostgreSQL | 16 |
| Base de datos dev | SQLite | — |
| Contenedores | Docker + Docker Compose | — |

## Estructura del proyecto

```
BackAutomatizacionWhatsapp/
├── app/
│   ├── config.py              # Configuración y variables de entorno
│   ├── main.py                # App FastAPI + watchdog mensual (corre cada hora)
│   ├── database/
│   │   └── db.py              # SQLAlchemy async, migraciones
│   ├── models/
│   │   ├── provider.py        # Modelo proveedor (distribuidora)
│   │   ├── message.py         # Modelo mensaje WhatsApp (estados: received/processing/processed/failed)
│   │   └── price.py           # Modelo precio/medicamento
│   ├── routers/
│   │   ├── webhook.py         # Recibe mensajes de whatsapp-web.js y dispara procesamiento
│   │   ├── providers.py       # CRUD proveedores
│   │   ├── prices.py          # Consulta precios, inicializar mes/día, exportar Excel
│   │   └── config.py          # Configuración dinámica de Google Sheets
│   └── services/
│       ├── ocr.py             # OCR con OpenAI Vision (imágenes → texto)
│       ├── ai_parser.py       # Extracción de medicamentos/precios con OpenAI + parser regex
│       ├── excel.py           # Gestión del archivo Excel local
│       ├── sheets.py          # Sincronización Google Sheets (fuente principal)
│       └── config_store.py    # Configuración dinámica en JSON (credenciales en runtime)
├── WhatsAppService/           # Servicio Node.js (whatsapp-web.js)
│   ├── index.js               # Escucha mensajes, envía QR, reenvía al backend
│   ├── Dockerfile
│   └── package.json
├── data/
│   └── app_config.json        # Config dinámica (creado en runtime, persistido en volumen Docker)
├── .env                       # Variables de entorno (NO subir a Git)
├── .env.example               # Plantilla de variables
├── Dockerfile                 # Imagen Docker del backend Python
├── requirements.txt           # Dependencias Python
└── run.py                     # Punto de entrada: uvicorn en 0.0.0.0:8000
```

## Instalación (desarrollo local)

```bash
# 1. Crear entorno virtual
python -m venv venv
.\venv\Scripts\activate     # Windows
source venv/bin/activate    # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 4. Levantar el servidor
python run.py
```

Servidor disponible en: `http://localhost:8000`
Documentación Swagger: `http://localhost:8000/docs`

## Despliegue con Docker (producción)

```bash
# Desde la raíz del proyecto (donde está docker-compose.yml)
docker compose up --build -d

# Solo reconstruir el backend:
docker compose up --build -d backend
```

Levanta automáticamente: PostgreSQL 16, backend Python, servicio WhatsApp Node.js y frontend React (nginx).

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `APP_NAME` | Nombre de la aplicación | `AutomatizacionWhatsapp` |
| `DEBUG` | Modo debug | `True` |
| `OPENAI_API_KEY` | Clave API de OpenAI | `sk-...` |
| `OPENAI_MODEL` | Modelo de OpenAI a usar | `gpt-4o-mini` |
| `DATABASE_URL` | URL de conexión a la BD | `sqlite+aiosqlite:///./automatizacion.db` |
| `EXCEL_OUTPUT_PATH` | Ruta del Excel local generado | `./output/precios.xlsx` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al JSON de cuenta de servicio Google | `./google_credentials.json` |
| `GOOGLE_SHEET_ID` | ID del Google Spreadsheet | `1ABC...xyz` |

> **Nota**: las credenciales de Google también pueden configurarse desde la página **Configuración** del panel web sin tocar archivos del servidor. La configuración dinámica tiene prioridad sobre el `.env`.

## Configuración dinámica de Google Sheets

1. Abrir la página **Configuración** (`/settings`) en el panel web.
2. Ingresar el **ID de la Google Sheet** y subir el **JSON de cuenta de servicio**.
3. El backend valida las credenciales y guarda la configuración en `data/app_config.json`.
4. A partir de ese momento, el sistema usa esas credenciales para leer y escribir en la hoja.

El archivo `data/app_config.json` se persiste en un volumen Docker bind-mounted (`./data:/app/data`), por lo que sobrevive a reinicios y rebuilds del contenedor.

## Flujo diario de operación

```
1. Admin hace clic en "Inicializar día"
   └─ Si es el primer día del mes en la hoja: crea la estructura completa
      (fila 1 proveedores + fila 2 Fecha/Medicamento/Precio/Cantidad)
   └─ Si ya hay días previos: inserta bloque de encabezado debajo de los datos existentes

2. Admin agrega los medicamentos del día directamente en Google Sheets
   └─ Escribe nombre del medicamento y fecha en las filas debajo del encabezado

3. Admin envía la lista de medicamentos a los proveedores por WhatsApp

4. Cada proveedor responde con sus precios (texto o imagen)

5. Sistema recibe el mensaje → IA extrae precios → actualiza filas del día actual
   └─ Solo se actualizan medicamentos que ya existen en las filas de hoy
   └─ Medicamentos no reconocidos son ignorados

6. Precio más bajo por medicamento se resalta en verde automáticamente
```

## Estructura de Google Sheets / Excel

Cada hoja tiene el nombre del mes en formato `YYYY-MM`. Estructura por bloques:

**Encabezados fijos (filas 1–2) — creados al "Inicializar día" por primera vez:**

| Fila 1 | Arca software ←──────→ | Brayan farmacia ←──→ | ... |
|--------|------------------------|----------------------|-----|
| Fila 2 | Fecha | Medicamento | Precio | Cantidad | Precio | Cantidad | ... |

- **Columna A**: Fecha (compartida)
- **Columna B**: Medicamento (compartida)
- **Columnas C en adelante**: 2 columnas por proveedor (Precio + Cantidad)
- **Columna Z**: Marcador invisible de fecha (para detectar duplicados de inicialización)

**Bloques de días posteriores (desde fila 3):**

```
[fila vacía de separación]
[fila azul: nombres de proveedores]      ← insertada por "Inicializar día"
[fila azul: Fecha | Medicamento | ...]   ← insertada por "Inicializar día"
[31/03/2026] [Aspirina 500mg]  [7,800] [caja]  [12,800] [caja]
[31/03/2026] [Dipirona 500mg]  [5,700] [unidad] [3,700] [unidad]
[31/03/2026] [Tinox rg 2.5mg]  [32,830][caja]  [NO]     [NO]
```

- El precio más bajo por medicamento se resalta en **verde** (solo si no todos son iguales).
- Las celdas sin precio llevan el valor `NO`.
- Los días anteriores **nunca se modifican**.

## Lógica de coincidencia de medicamentos

Cuando un proveedor responde, el sistema identifica los medicamentos del mensaje usando 4 niveles:

1. **Exacto** (case-insensitive): `"aspirina 500mg"` == `"Aspirina 500mg"`
2. **Subconjunto de palabras**: `"aspirina"` encontrado en `"Aspirina 500mg tabletas"`
3. **Nombres normalizados**: quita paréntesis y sufijos de empaque antes de comparar  
   `"Tinox (RG)"` → `"tinox rg"`, `"Caja X 30 UNDS"` → ignorado
4. **Fuzzy ≥ 80%**: tolera typos, abreviaciones de OCR  
   `"asprina 500"` → `"Aspirina 500mg"` (87% similitud)

Además, antes de parsear el mensaje la IA recibe la lista de medicamentos conocidos del día para hacer matching canónico directo (evita duplicados por nombres distintos del mismo medicamento).

## Inicialización mensual automática

Al inicio de cada mes, el watchdog en background crea automáticamente la pestaña vacía (`YYYY-MM`) en Google Sheets y en el Excel local. La creación automática **solo crea la pestaña vacía** — sin formato ni encabezados. El formato completo (proveedores + columnas) se crea cuando el administrador hace clic en **"Inicializar día"** por primera vez.

Comportamiento:
- **Automático**: watchdog revisa cada hora, crea la pestaña si no existe.
- **Manual**: botón "Inicializar [mes]" en el Dashboard (también crea solo la pestaña vacía).
- Si la hoja ya existe y no se pasa `force=True`, no se toca.
- Con `force=True` (botón con confirmación): elimina y recrea la pestaña vacía.

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Estado del servidor |
| `POST` | `/api/webhook/whatsapp-web` | Recibir mensajes de whatsapp-web.js |
| `GET` | `/providers` | Listar proveedores activos e inactivos |
| `POST` | `/providers` | Crear proveedor (phone_number, name) |
| `PUT` | `/providers/{id}` | Actualizar proveedor |
| `DELETE` | `/providers/{id}` | Eliminar proveedor |
| `GET` | `/prices` | Consultar precios (filtros: medication, provider_id, date_from, date_to, limit) |
| `GET` | `/prices/summary` | Resumen estadístico (total precios, medicamentos, Excel) |
| `DELETE` | `/prices/{id}` | Eliminar registro de precio |
| `GET` | `/prices/export/excel` | Descargar Excel generado desde la BD |
| `POST` | `/prices/init-month` | Crear pestaña vacía del mes en Sheets/Excel |
| `POST` | `/prices/init-day` | Inicializar estructura del día (primer día) o nuevo bloque (días posteriores) |
| `GET` | `/config/status` | Estado de conexión con Google Sheets |
| `POST` | `/config/google` | Guardar sheet ID y/o credenciales JSON |

### Detalle de endpoints clave

**`POST /prices/init-month?force=false`**  
Crea la pestaña `YYYY-MM` vacía (sin formato ni proveedores) en Google Sheets y en el Excel local. Si la pestaña ya existe y `force=false`, retorna advertencia sin modificar. Con `force=true` elimina y recrea.

**`POST /prices/init-day`**  
- **Primera vez en el mes** (hoja vacía): crea la estructura completa — fila 1 con nombres de proveedores activos (celda azul, celdas combinadas), fila 2 con Fecha/Medicamento/Precio/Cantidad (azul).  
- **Días posteriores**: inserta fila vacía de separación + fila azul de proveedores + fila azul de sub-encabezados debajo del último dato.  
- Si el día ya fue inicializado (marcador en col Z), retorna `"created": false` sin duplicar.

**`POST /api/webhook/whatsapp-web`**  
Recibe el payload JSON de whatsapp-web.js, identifica al proveedor por número telefónico (normalización E.164 y 10 dígitos), extrae precios con IA (y OCR si es imagen), filtra solo los medicamentos en las filas de hoy, y actualiza Google Sheets + Excel + base de datos. Ignora mensajes duplicados por `messageId`.

**`GET /prices/export/excel`**  
Genera en memoria un `.xlsx` con todos los precios de la BD (una hoja por mes, mismo formato que Google Sheets). Devuelve como descarga directa.

## Servicio WhatsApp (Node.js)

Ubicado en `WhatsAppService/`. Usa `whatsapp-web.js` con Puppeteer/Chromium headless.

**Variable de entorno requerida:**
```
BACKEND_URL=http://backend:8000   # En Docker (nombre de servicio)
BACKEND_URL=http://localhost:8000  # En desarrollo local
```

**Endpoints expuestos (puerto 3000):**
- `GET /qr` → retorna el QR actual como JSON `{ qr: "..." }` o estado de la sesión
- `GET /status` → estado de la sesión WhatsApp
- `POST /send` → enviar mensaje (uso interno)

**Sesión persistente:** Los datos de Chrome se guardan en `session-data/` (volumen Docker `whatsapp_session`). Una vez escaneado el QR, la sesión persiste entre reinicios.
