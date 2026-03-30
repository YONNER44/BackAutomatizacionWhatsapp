FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY app/ ./app/
COPY run.py .

# Crear carpeta de salida Excel
RUN mkdir -p output

EXPOSE 8000

CMD ["python", "run.py"]
