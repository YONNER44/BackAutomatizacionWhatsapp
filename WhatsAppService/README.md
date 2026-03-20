# Servicio WhatsApp Web

Este servicio captura mensajes de WhatsApp usando `whatsapp-web.js` y los envía al backend Python.

## 🚀 Instalación

```bash
npm install
```

## ⚙️ Configuración

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

## ▶️ Correr el servicio

```bash
# Producción
npm start

# Desarrollo (reinicia automáticamente al guardar cambios)
npm run dev
```

## 📱 Vincular WhatsApp

1. Al iniciar el servicio, aparecerá un **código QR** en la terminal
2. Abre WhatsApp en tu celular
3. Ve a: **Configuración > Dispositivos vinculados > Vincular dispositivo**
4. Escanea el código QR
5. ¡Listo! El servicio está conectado

## 🔄 Funcionamiento

Cuando recibas mensajes de WhatsApp:
1. El servicio los captura automáticamente
2. Los envía al backend Python (`http://localhost:8000/api/webhook/whatsapp-web`)
3. El backend procesa OCR (si es imagen) + IA
4. Actualiza automáticamente Excel/Google Sheets

## 📊 Endpoints de monitoreo

- **Status**: `http://localhost:3000/status` - Estado de conexión (connected/disconnected) y timestamp
- **Health**: `http://localhost:3000/health` - Verificar si el servicio está corriendo
- **QR (JSON)**: `http://localhost:3000/qr` - Obtener el código QR en formato JSON
- **QR (visual)**: `http://localhost:3000/qr-viewer` - Ver el código QR en el navegador

## 🛑 Detener el servicio

Presiona `Ctrl + C` en la terminal

## 📝 Notas

- La sesión se guarda en `./session-data` - no la borres o tendrás que escanear el QR nuevamente
- Soporta mensajes de texto e imágenes
- Los mensajes se procesan en segundo plano
