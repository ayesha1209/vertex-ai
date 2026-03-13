# Backend Dockerfile for Render (and local parity).
# Installs WeasyPrint system deps so PDF layout matches local (same engine as your dev machine).
FROM python:3.12-slim-bookworm

WORKDIR /app

# WeasyPrint system dependencies (cairo, pango, gdk-pixbuf, etc.)
# Without these, pip install weasyprint fails and production falls back to xhtml2pdf (different layout).
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets PORT; default for local Docker
ENV PORT=8000
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
