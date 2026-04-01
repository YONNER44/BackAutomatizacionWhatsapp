#!/bin/sh
echo "🧹 Limpiando locks y cache de Chromium..."

# Eliminar locks de Chromium en toda la carpeta de sesión
find /app/session-data -name "SingletonLock" -delete 2>/dev/null
find /app/session-data -name "SingletonSocket" -delete 2>/dev/null
find /app/session-data -name ".org.chromium.Chromium" -delete 2>/dev/null
find /app/session-data -name "lockfile" -delete 2>/dev/null

echo "✅ Limpieza completa. Iniciando servicio WhatsApp..."
exec node index.js
