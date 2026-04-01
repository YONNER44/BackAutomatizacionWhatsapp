FROM node:20-slim

# Dependencias de Chrome/Puppeteer (necesarias para whatsapp-web.js)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-freefont-ttf \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Decirle a Puppeteer que use el Chrome del sistema en vez de descargar uno
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY index.js .
COPY start.sh .
RUN chmod +x start.sh

# Sesión de WhatsApp persistente (montar como volumen)
RUN mkdir -p session-data

EXPOSE 3000

CMD ["sh", "start.sh"]
