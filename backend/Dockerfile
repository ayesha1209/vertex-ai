# Backend Dockerfile for Render (and local parity).
# Installs WeasyPrint system deps so PDF layout matches local (same engine as your dev machine).
FROM python:3.12-slim-bookworm

WORKDIR /app

# WeasyPrint system dependencies (cairo, pango, gdk-pixbuf, etc.)
# pkg-config + *-dev headers needed so pycairo can build against cairo/pango.
# Fonts: match print_css.py (DejaVu Sans, Liberation Sans) so PDF layout matches local.
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libgdk-pixbuf2.0-dev \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets PORT; default for local Docker
ENV PORT=8000
EXPOSE ${PORT}

# glibc's malloc keeps freed arenas around per-thread instead of returning them
# to the OS; with pandas/cairo/pango doing lots of large, short-lived native
# allocations, that fragmentation ratchets process RSS up until the instance's
# memory limit kills it. Capping arenas keeps that bounded. (app code also
# calls malloc_trim after each heavy request — see app/utils/memory.py.)
ENV MALLOC_ARENA_MAX=2

# Safety net: recycle the process well before it could approach the memory
# ceiling, as a graceful restart instead of an OOM SIGKILL mid-request.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*" --limit-max-requests 500
