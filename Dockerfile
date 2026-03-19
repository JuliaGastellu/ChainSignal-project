FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requerimientos e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear directorio de cache
RUN mkdir -p cache demo_data

# Exponer puertos (API y Web)
EXPOSE 8001
EXPOSE 8081

# Script de inicio por defecto para la API
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8001"]
