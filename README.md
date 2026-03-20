# BackAutomatizacionWhatsapp

Backend del sistema de automatización de recolección de precios de medicamentos vía WhatsApp Web.

## Tecnologías

- **Python 3.11+** + **FastAPI**
- **WhatsApp**: whatsapp-web.js (servicio Node.js en `WhatsAppService/`)
- **OCR + IA**: OpenAI GPT-4o-mini (Vision para imágenes, chat para extracción de precios)
- **Base de datos**: SQLite (dev) / PostgreSQL (prod)
- **Excel**: openpyxl
- **Google Sheets**: gspread (opcional)

## Estructura del proyecto

```
app/
├── config.py          # Configuración y variables de entorno
├── main.py            # Aplicación FastAPI principal
├── database/
│   └── db.py          # Configuración SQLAlchemy async
├── models/
│   ├── provider.py    # Modelo proveedor
│   ├── message.py     # Modelo mensaje WhatsApp
│   └── price.py       # Modelo precio/medicamento
├── routers/
│   ├── webhook.py     # Endpoint para recibir mensajes de whatsapp-web.js
│   ├── providers.py   # CRUD proveedores
│   └── prices.py      # Consulta precios + exportar Excel
└── services/
    ├── ocr.py         # OCR con OpenAI Vision
    ├── ai_parser.py   # OpenAI para extraer medicamentos/precios
    ├── excel.py       # Generación/actualización Excel
    └── sheets.py      # Sincronización Google Sheets (opcional)
WhatsAppService/       # Servicio Node.js que captura mensajes de WhatsApp Web
```

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales
```

## Correr el servidor

```bash
# Activar el entorno virtual (si no está activo)
venv\Scripts\activate     # Windows
source venv/bin/activate  # Linux/Mac

# Iniciar el servidor
python run.py
```

El servidor queda en: http://localhost:8000
Documentación API (Swagger): http://localhost:8000/docs

## Flujo de procesamiento

1. Proveedor envía mensaje (texto o imagen) por WhatsApp
2. El servicio `WhatsAppService/` captura el mensaje y lo envía al backend (`POST /api/webhook/whatsapp-web`)
3. Sistema identifica al proveedor por número telefónico
4. Si es imagen → OCR con OpenAI Vision extrae el texto
5. OpenAI GPT-4o-mini estructura medicamentos y precios
6. Se guarda en base de datos SQLite
7. Se actualiza el archivo Excel (medicamentos en filas, proveedores en columnas)
8. Si está configurado, se sincroniza con Google Sheets

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/webhook/whatsapp-web` | Recibir mensajes desde whatsapp-web.js |
| GET | `/providers` | Listar proveedores |
| POST | `/providers` | Crear proveedor |
| PUT | `/providers/{id}` | Actualizar proveedor |
| DELETE | `/providers/{id}` | Eliminar proveedor |
| GET | `/prices` | Consultar precios |
| DELETE | `/prices/{id}` | Eliminar precio |
| GET | `/prices/export/excel` | Descargar Excel |
| GET | `/prices/summary` | Resumen estadístico |
