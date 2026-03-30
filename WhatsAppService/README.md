# Servicio WhatsApp Web

Este servicio captura mensajes de WhatsApp usando `whatsapp-web.js` y los envía al backend Python.

## Tecnologías

- **Node.js 20**
- **whatsapp-web.js** – automatización de WhatsApp Web
- **Puppeteer** – control de Chromium headless
- **Express** – servidor HTTP para endpoints de monitoreo y QR

## Instalación (desarrollo local)

```bash
npm install
```

## Configuración

1. Copia el archivo de ejemplo:
```bash
cp .env.example .env
```

2. Configura las variables (opcional, valores por defecto incluidos):
```env
PORT=3000
BACKEND_URL=http://localhost:8000
DEBUG=true
```

## Correr el servicio

```bash
# Producción
npm start

# Desarrollo (reinicia automáticamente al guardar cambios)
npm run dev
```

## Despliegue con Docker

El servicio corre dentro de un contenedor Docker usando Chromium del sistema (no descarga Chrome por separado):

```bash
# Desde la raíz del proyecto
docker compose up --build -d whatsapp
```

Variables de entorno relevantes en Docker:
- `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true` – no descarga Chrome, usa el del sistema
- `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium` – ruta de Chromium en la imagen

La sesión de WhatsApp se persiste en el volumen `whatsapp_session` para que no pida QR en cada reinicio.

## Vincular WhatsApp

1. Al iniciar el servicio, aparecerá un **código QR** en la terminal
2. Abre WhatsApp en tu celular
3. Ve a: **Configuración > Dispositivos vinculados > Vincular dispositivo**
4. Escanea el código QR
5. El QR también está disponible visualmente en: `http://localhost:3000/qr-viewer`

> La sesión se guarda en `./session-data`. No la borres o tendrás que escanear el QR nuevamente.

## Funcionamiento

Cuando llega un mensaje de WhatsApp:
1. El servicio lo captura automáticamente
2. Si tiene media (imagen), la descarga en base64
3. Resuelve números con formato `@lid` al número real (`@c.us`)
4. Envía todo al backend Python: `POST /api/webhook/whatsapp-web`
5. El backend extrae texto (OCR si es imagen), la IA parsea precios y actualiza Google Sheets/Excel

## Reinicio automático

El servicio se reinicia solo ante cualquier desconexión (`disconnected`, `auth_failure`, errores no capturados). No requiere intervención manual. Espera 5–8 segundos y reconecta.

## Endpoints de monitoreo

| Endpoint | Descripción |
|----------|-------------|
| `GET /status` | Estado de conexión (`connected`/`disconnected`), QR actual y timestamp |
| `GET /health` | Health check básico |
| `GET /qr` | Código QR en JSON (para integraciones) |
| `GET /qr-viewer` | Página HTML para escanear el QR visualmente |

## Detener el servicio

Presiona `Ctrl + C` — el servicio cierra la sesión de WhatsApp limpiamente antes de salir.

## Notas

- Soporta mensajes de texto e imágenes
- Variable `DEBUG=true` en `.env` muestra logs detallados de cada mensaje recibido
- El payload enviado al backend incluye: `from`, `timestamp`, `messageId`, `type`, `body`, `hasMedia`, y opcionalmente `media` (base64)
- En Docker, Chromium corre con `--no-sandbox` ya que está dentro de un contenedor sin privilegios de root
