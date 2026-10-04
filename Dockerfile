# Imagen de la API y del worker de lectura (E08). Una sola imagen, dos comandos:
#   API:        uvicorn api.main:app ...   (comando por defecto)
#   worker:     python -m worker_lectura
#   migración:  alembic upgrade head       (paso aparte, una vez por despliegue)

FROM python:3.11-slim-bookworm AS dependencias
# Compilo en una etapa separada por si algún paquete no trae wheel; la imagen final no lleva compiladores.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir --prefix=/instalado -r requirements.txt -c constraints.txt

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=dependencias /instalado /usr/local
WORKDIR /app
COPY . .
# Sin root: el proceso no puede escribir fuera de su directorio de trabajo temporal.
RUN useradd --system --uid 10001 --home /app chainsignal && mkdir -p /tmp/chainsignal && chown chainsignal /tmp/chainsignal
USER chainsignal
WORKDIR /tmp/chainsignal
ENV PYTHONPATH=/app
EXPOSE 8001
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "20", "--no-server-header"]
