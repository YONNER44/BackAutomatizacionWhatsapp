import pkg from 'whatsapp-web.js';
const { Client, LocalAuth } = pkg;
import qrcode from 'qrcode-terminal';
import axios from 'axios';
import express from 'express';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';

dotenv.config();

// Eliminar archivos de bloqueo de Chromium recursivamente en session-data
function cleanChromiumLocks(dir = './session-data') {
    const lockNames = ['SingletonLock', 'SingletonSocket', '.org.chromium.Chromium'];
    try {
        if (!fs.existsSync(dir)) return;
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                cleanChromiumLocks(fullPath);
            } else if (lockNames.includes(entry.name)) {
                try {
                    fs.unlinkSync(fullPath);
                    console.log(`🧹 Lock eliminado: ${fullPath}`);
                } catch (_) {}
            }
        }
    } catch (_) {}
}

cleanChromiumLocks();

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const DEBUG = process.env.DEBUG === 'true';

// Estado global (persiste entre reinicios del cliente)
let isReady = false;
let qrCodeData = null;
let client = null;
let restarting = false;

// ─── Creación del cliente ────────────────────────────────────────────────────

function createClient() {
    return new Client({
        authStrategy: new LocalAuth({ dataPath: './session-data' }),
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu'
            ]
        }
    });
}

function attachEvents(c) {
    c.on('qr', (qr) => {
        console.log('\n🔐 Escanea este código QR con WhatsApp:\n');
        qrcode.generate(qr, { small: true });
        qrCodeData = qr;
        console.log('\n📱 Abre WhatsApp > Dispositivos vinculados > Vincular dispositivo');
    });

    c.on('ready', () => {
        console.log('✅ WhatsApp conectado correctamente');
        isReady = true;
        qrCodeData = null;
        restarting = false;
    });

    c.on('authenticated', () => {
        console.log('🔓 Sesión autenticada');
    });

    c.on('auth_failure', (msg) => {
        console.error('❌ Fallo de autenticación:', msg);
        isReady = false;
        scheduleRestart(5000);
    });

    c.on('disconnected', (reason) => {
        console.log('⚠️  WhatsApp desconectado:', reason);
        isReady = false;
        scheduleRestart(5000);
    });

    c.on('message', handleMessage);
}

// ─── Reinicio del cliente ────────────────────────────────────────────────────

function scheduleRestart(delay = 8000) {
    if (restarting) return;
    restarting = true;
    isReady = false;
    qrCodeData = null;
    console.log(`🔄 Reiniciando cliente en ${delay / 1000}s...`);
    setTimeout(async () => {
        try {
            if (client) {
                await client.destroy().catch(() => {});
            }
        } catch (_) {}
        client = createClient();
        attachEvents(client);
        await client.initialize();
    }, delay);
}

// ─── Manejo de mensajes ──────────────────────────────────────────────────────

async function handleMessage(message) {
    try {
        let fromNumber = message.from;
        if (fromNumber.includes('@lid')) {
            try {
                const contact = await message.getContact();
                if (contact?.number) {
                    fromNumber = contact.number + '@c.us';
                    console.log(`📱 @lid resuelto: ${message.from} → ${fromNumber}`);
                }
            } catch (e) {
                console.error('⚠️  No se pudo resolver @lid:', e.message);
            }
        }

        if (DEBUG) {
            console.log('\n📨 Mensaje recibido:');
            console.log('  De:', fromNumber);
            console.log('  Tipo:', message.type);
            console.log('  Contenido:', message.body?.substring(0, 100));
        }

        const messageData = {
            from: fromNumber,
            timestamp: message.timestamp,
            messageId: message.id._serialized,
            type: message.type,
            body: message.body || '',
            hasMedia: message.hasMedia
        };

        if (message.hasMedia) {
            try {
                const media = await message.downloadMedia();
                if (media) {
                    messageData.media = {
                        mimetype: media.mimetype,
                        data: media.data,
                        filename: media.filename || 'image.jpg'
                    };
                    if (DEBUG) console.log('  📎 Media descargada:', media.mimetype);
                }
            } catch (error) {
                console.error('❌ Error descargando media:', error.message);
            }
        }

        try {
            const response = await axios.post(
                `${BACKEND_URL}/api/webhook/whatsapp-web`,
                messageData,
                { headers: { 'Content-Type': 'application/json' }, timeout: 30000 }
            );
            if (DEBUG) console.log('  ✅ Enviado al backend:', response.data);
        } catch (error) {
            console.error('❌ Error enviando al backend:', error.message);
        }

    } catch (error) {
        console.error('❌ Error procesando mensaje:', error);
    }
}

// ─── API REST ────────────────────────────────────────────────────────────────

app.use(express.json());

app.get('/status', (req, res) => {
    res.json({
        status: isReady ? 'connected' : 'disconnected',
        qrCode: qrCodeData,
        timestamp: new Date().toISOString()
    });
});

app.get('/health', (req, res) => {
    res.json({
        service: 'whatsapp-service',
        status: 'running',
        whatsapp: isReady ? 'connected' : 'disconnected'
    });
});

app.get('/qr', (req, res) => {
    if (qrCodeData) {
        res.json({ qr: qrCodeData, message: 'Escanea este QR con WhatsApp' });
    } else if (isReady) {
        res.json({ message: 'WhatsApp ya está conectado' });
    } else {
        res.json({ message: 'Esperando generación de QR...' });
    }
});

app.get('/qr-viewer', (req, res) => {
    res.sendFile(path.join(process.cwd(), 'qr-viewer.html'));
});

// ─── Arranque ────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
    console.log(`\n🚀 Servicio WhatsApp iniciado en puerto ${PORT}`);
    console.log(`📊 Monitoreo: http://localhost:${PORT}/status`);
    console.log(`🔍 Health check: http://localhost:${PORT}/health`);
});

console.log('\n⏳ Iniciando conexión con WhatsApp...');
client = createClient();
attachEvents(client);
client.initialize();

// ─── Captura de errores globales (evita que el proceso muera) ────────────────

process.on('uncaughtException', (err) => {
    console.error('⚠️  Error no capturado:', err.message);
    scheduleRestart(8000);
});

process.on('unhandledRejection', (reason) => {
    console.error('⚠️  Promesa rechazada:', reason?.message || reason);
    scheduleRestart(8000);
});

process.on('SIGINT', async () => {
    console.log('\n\n⏹️  Cerrando servicio...');
    if (client) await client.destroy().catch(() => {});
    process.exit(0);
});
