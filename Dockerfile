# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Optional: override apt/pip mirrors for restricted networks (e.g. Iran)
# Usage: docker build --build-arg APT_MIRROR=https://repo.abrha.net/debian \
#                     --build-arg PIP_MIRROR=https://package-mirror.liara.ir/repository/pypi/simple
ARG APT_MIRROR=""
ARG PIP_MIRROR="https://pypi.org/simple"

RUN if [ -n "$APT_MIRROR" ]; then \
      echo "deb ${APT_MIRROR} bookworm main contrib non-free" > /etc/apt/sources.list && \
      echo "deb ${APT_MIRROR} bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
      echo "deb ${APT_MIRROR} bookworm-backports main contrib non-free" >> /etc/apt/sources.list && \
      echo "deb ${APT_MIRROR}-security bookworm-security main contrib non-free" >> /etc/apt/sources.list && \
      rm -f /etc/apt/sources.list.d/debian.sources; \
    fi

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
ENV PIP_INDEX_URL=${PIP_MIRROR}
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files (Django)
RUN python manage.py collectstatic --noinput --settings=config.settings.production

# Non-root user for security
RUN adduser --disabled-password --gecos "" farmpulse
USER farmpulse

EXPOSE 8000

# Default: run Daphne ASGI server (overridden per-service in compose)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
