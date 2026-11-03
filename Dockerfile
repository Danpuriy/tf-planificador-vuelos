# Imagen del servidor web del TF.
# Mantiene la estructura app/ + data/ para que cargador_datos encuentre los .dat.

FROM python:3.11-slim

# Evita archivos .pyc y fuerza logs sin buffer (útiles en la nube).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /proyecto

# 1) Dependencias primero (mejor caché de capas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código y datos, conservando la estructura relativa.
COPY app ./app
COPY data ./data

# 3) El servidor se ejecuta desde app/ para que los imports funcionen.
WORKDIR /proyecto/app

EXPOSE 8000

# Render inyecta PORT; en local usamos 8000 por defecto.
CMD uvicorn servidor:app --host 0.0.0.0 --port ${PORT:-8000}
