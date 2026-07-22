# syntax=docker/dockerfile:1.7

# ============================================================================
# Imagen base: Python 3.12 slim para reducir superficie de ataque.
# ============================================================================
FROM python:3.12-slim AS base

# ----------------------------------------------------------------------------
# Issue #25 — Parchear paquetes del SO y limpiar la caché de apt.
# Se hace en una sola capa para no dejar listas de paquetes residuales.
# ----------------------------------------------------------------------------
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------
# Crear el usuario no-root antes de copiar el código (Issue #20).
# De esta forma el WORKDIR ya pertenece a appuser y evitamos un chown extra.
# ----------------------------------------------------------------------------
RUN useradd --create-home --shell /bin/bash appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

# ----------------------------------------------------------------------------
# Copiar SOLO los archivos de manifiesto de dependencias (Issue #26).
# Gracias al .dockerignore este COPY no arrastra .git, .venv, tests, etc.
# Esta capa se cachea mientras no cambien pyproject.toml / uv.lock.
# ----------------------------------------------------------------------------
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Instalar uv y sincronizar dependencias SIN el grupo dev (--no-dev).
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

# ----------------------------------------------------------------------------
# Copiar estrictamente el código de la aplicación.
# No copiamos tests/, docs/, main.py (CLI), src/ ni .env.
# ----------------------------------------------------------------------------
COPY --chown=appuser:appuser app/ ./app/

# ----------------------------------------------------------------------------
# Ejecutar como usuario no privilegiado (Issue #20).
# ----------------------------------------------------------------------------
USER appuser

EXPOSE 8000

# Healthcheck ligero: curl al endpoint /health (Issue #24).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://127.0.0.1:8000/health || exit 1

# ----------------------------------------------------------------------------
# Issue #21 — CMD apunta al módulo correcto: app.main:app
# ----------------------------------------------------------------------------
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
