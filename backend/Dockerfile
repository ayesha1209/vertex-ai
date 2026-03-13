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

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
