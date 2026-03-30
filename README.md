# BackAutomatizacionWhatsapp

Backend del sistema de automatización de recolección de precios de medicamentos vía WhatsApp Web.

## Tecnologías

- **Python 3.11+** + **FastAPI**
- **WhatsApp**: whatsapp-web.js (servicio Node.js en `WhatsAppService/`)
- **OCR + IA**: OpenAI GPT-4o-mini (Vision para imágenes, chat para extracción de precios)
- **Base de datos**: SQLite (dev) / PostgreSQL (prod)
- **Excel**: openpyxl
- **Google Sheets**: gspread (fuente principal de almacenamiento)

## Estructura del proyecto

```
app/
├── config.py              # Configuración y variables de entorno
├── main.py                # Aplicación FastAPI principal + watchdog mensual
├── database/
│   └── db.py              # Configuración SQLAlchemy async
├── models/
│   ├── provider.py        # Modelo proveedor
│   ├── message.py         # Modelo mensaje WhatsApp
│   └── price.py           # Modelo precio/medicamento
├── routers/
│   ├── webhook.py         # Endpoint para recibir mensajes de whatsapp-web.js
│   ├── providers.py       # CRUD proveedores
│   ├── prices.py          # Consulta precios, exportar Excel, inicializar mes/día
│   └── config.py          # Configuración dinámica de Google Sheets (credenciales, sheet ID)
└── services/
    ├── ocr.py             # OCR con OpenAI Vision
    ├── ai_parser.py       # OpenAI para extraer medicamentos/precios
    ├── excel.py           # Generación/actualización Excel local
    ├── sheets.py          # Sincronización Google Sheets (fuente principal)
    └── config_store.py    # Almacén de configuración en JSON (credenciales en tiempo de ejecución)
WhatsAppService/           # Servicio Node.js que captura mensajes de WhatsApp Web
data/
└── app_config.json        # Configuración dinámica guardada por el cliente (creado en runtime)
```

## Instalación (desarrollo local)

```bash
# 1. Crear entorno virtual
python -m venv venv
.\venv\Scripts\activate     # Windows CMD/PowerShell
source venv/bin/activate    # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales
```

## Correr el servidor (desarrollo local)

```bash
# En Windows, si venv está activo:
python run.py

# En Windows, sin activar venv:
.\venv\Scripts\python.exe run.py
```

El servidor queda en: http://localhost:8000
Documentación API (Swagger): http://localhost:8000/docs

## Despliegue con Docker

```bash
# Desde la raíz del proyecto (donde está docker-compose.yml)
docker compose up --build -d
```

Levanta automáticamente: base de datos PostgreSQL, backend Python, servicio WhatsApp Node.js y frontend React.

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `APP_NAME` | Nombre de la aplicación | `AutomatizacionWhatsapp` |
| `DEBUG` | Modo debug | `True` |
| `OPENAI_API_KEY` | Clave API de OpenAI | `sk-...` |
| `OPENAI_MODEL` | Modelo de OpenAI | `gpt-4o-mini` |
| `DATABASE_URL` | URL de la base de datos | `sqlite+aiosqlite:///./automatizacion.db` |
| `EXCEL_OUTPUT_PATH` | Ruta del archivo Excel generado | `./output/precios.xlsx` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al archivo JSON de credenciales Google (opcional si se configura desde la UI) | `./google_credentials.json` |
| `GOOGLE_SHEET_ID` | ID del Google Spreadsheet (opcional si se configura desde la UI) | `1ABC...xyz` |

> Las credenciales de Google también pueden configurarse desde la página **Configuración** del panel web, sin necesidad de editar archivos del servidor.

## Configuración dinámica de Google Sheets

El sistema permite al cliente configurar sus propias credenciales de Google sin tocar archivos del servidor:

1. El cliente abre la página **Configuración** (`/settings`) en el panel web.
2. Ingresa el **ID de su Google Sheet** y sube el archivo **JSON de cuenta de servicio**.
3. El backend valida las credenciales, prueba la conexión y guarda la configuración en `data/app_config.json`.
4. A partir de ese momento, el sistema usa esas credenciales para leer y escribir en la hoja del cliente.

La configuración dinámica (`config_store.py`) tiene prioridad sobre las variables de entorno del `.env`.

## Flujo diario de operación

1. **El administrador hace clic en "Inicializar día"** → el backend inserta un bloque de encabezado visual (nombres de proveedores + columnas Fecha/Medicamento/Precio/Cantidad) debajo de los datos del día anterior en Google Sheets y en el Excel local.
2. **El administrador agrega manualmente los medicamentos del día** con su fecha directamente en las filas vacías de la hoja de Google Sheets.
3. **El administrador envía la lista de medicamentos** a los proveedores por el grupo de WhatsApp.
4. **Cada proveedor responde en privado** con sus precios (texto o imagen).
5. **El sistema recibe el mensaje**, la IA extrae los precios y actualiza únicamente las filas del día actual.
6. **Los datos de días anteriores nunca se modifican** — cada día es un grupo de filas independiente.

## Estructura de la hoja de Google Sheets / Excel

Cada hoja tiene el nombre del mes en formato `YYYY-MM`. La hoja tiene una estructura por bloques de días:

**Encabezados fijos (filas 1–2)**:

| (fila 1) | Proveedor A | | Proveedor B | |
|----------|-------------|--|-------------|--|
| Fecha | Medicamento | Precio | Cantidad | Precio | Cantidad |

- **Fila 1**: nombre del proveedor combinado sobre sus 2 columnas (Precio + Cantidad)
- **Fila 2**: sub-encabezados fijos (Fecha, Medicamento, luego Precio/Cantidad por proveedor)
- **Columna A**: Fecha (compartida por todos los proveedores)
- **Columna B**: Medicamento (compartida)
- **Columnas C en adelante**: 2 columnas por proveedor (Precio + Cantidad)

**Bloques de días (fila 3 en adelante)**:

Cada día tiene su propio bloque precedido por un encabezado visual idéntico a las filas 1–2 (en azul). El administrador agrega las filas de medicamentos debajo de ese encabezado. Ejemplo:

```
[fila separadora vacía]
[fila encabezado proveedor azul]      ← insertada por "Inicializar día"
[fila Fecha | Medicamento | ... azul] ← insertada por "Inicializar día"
[24/03/2026] [Aspirina 500mg] [7800] [caja] [7500] [caja]   ← agrega el admin
[24/03/2026] [Dipirona 1g]    [NO]  [NO]   [4200] [caja]   ← agrega el admin
[fila separadora vacía]
[fila encabezado proveedor azul]      ← día siguiente
...
```

- El precio más bajo de cada medicamento se resalta en verde automáticamente.
- Las celdas sin precio llevan el valor `NO`.

## Lógica de actualización por día

Cuando un proveedor responde:

- El sistema obtiene **solo las filas que tienen la fecha de hoy** en la columna A.
- Busca cada medicamento del mensaje en esas filas (con coincidencia exacta, por palabras o fuzzy ≥ 80%).
- Si el medicamento existe en las filas de hoy → actualiza Precio y Cantidad.
- Si el medicamento **no** está en las filas de hoy → se **ignora** completamente.
- Si un proveedor responde tarde (al día siguiente), el sistema busca el medicamento solo en las filas de hoy. Si no existe, lo ignora; si existe, lo actualiza.
- Los días anteriores **nunca se tocan**.

## Inicialización mensual

Al inicio de cada mes se crea la hoja vacía con los proveedores activos (sin medicamentos). Esto ocurre:

- **Automáticamente**: un watchdog en background revisa cada hora si existe la hoja del mes y la crea si falta.
- **Manualmente**: botón "Inicializar [mes]" en el Dashboard del frontend.

Si la hoja ya existe y no se pasa `force=True`, no se modifica ni se borran datos.

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/webhook/whatsapp-web` | Recibir mensajes desde whatsapp-web.js |
| GET | `/providers` | Listar proveedores |
| POST | `/providers` | Crear proveedor |
| PUT | `/providers/{id}` | Actualizar proveedor |
| DELETE | `/providers/{id}` | Eliminar proveedor |
| GET | `/prices` | Consultar precios (filtros: medication, provider_id, date_from, date_to, limit) |
| GET | `/prices/summary` | Resumen estadístico |
| POST | `/prices/init-month` | Crear hoja del mes actual en Google Sheets y Excel (sin medicamentos) |
| POST | `/prices/init-day` | Insertar bloque de encabezado del día actual debajo de los datos existentes |
| GET | `/prices/export/excel` | Generar y descargar Excel desde la base de datos |
| DELETE | `/prices/{id}` | Eliminar registro de precio por ID |
| GET | `/config/status` | Estado de conexión con Google Sheets (credenciales, sheet ID, conectado) |
| POST | `/config/google` | Guardar ID de hoja y/o archivo JSON de credenciales de Google |

### Detalle de endpoints clave

**`POST /prices/init-month?force=false`**
Crea la hoja mensual en Google Sheets y en el Excel local con el formato de proveedores (filas 1–2) pero sin medicamentos. Si la hoja ya existe y `force=false`, retorna advertencia sin modificar nada. Con `force=true` elimina y recrea la hoja.

**`POST /prices/init-day`**
Inserta debajo del último dato existente: una fila vacía de separación, una fila con los nombres de los proveedores (estilo azul), y una fila con los sub-encabezados Fecha/Medicamento/Precio/Cantidad (estilo azul). El administrador agrega las filas de medicamentos manualmente. Si el encabezado del día ya existe, no se duplica.

**`POST /api/webhook/whatsapp-web`**
Recibe el payload JSON de whatsapp-web.js, identifica al proveedor por número telefónico, extrae precios con IA (y OCR si es imagen), filtra solo los medicamentos presentes en las filas de hoy, y actualiza Google Sheets + Excel + base de datos. Ignora mensajes duplicados.

**`GET /prices/export/excel`**
Genera en memoria un archivo `.xlsx` con todos los precios de la base de datos, una hoja por mes, en el mismo formato de columnas que Google Sheets. Devuelve el archivo como descarga directa.

**`GET /config/status`**
Retorna el estado actual de la integración con Google Sheets: si hay credenciales guardadas, el email de la cuenta de servicio, el sheet ID configurado y si la conexión está activa.

**`POST /config/google`**
Recibe `sheet_id` (Form) y opcionalmente `credentials` (archivo JSON multipart). Valida que el JSON sea una cuenta de servicio de Google (`type: service_account`), guarda la configuración en `data/app_config.json` e invalida el caché del servicio. Retorna si la conexión fue exitosa.
