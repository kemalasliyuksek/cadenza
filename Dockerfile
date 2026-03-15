FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install yt-dlp (latest version, updated frequently)
RUN pip install --no-cache-dir --upgrade yt-dlp

# Copy application code
COPY cadenza/ cadenza/

# Create directories for data and music
RUN mkdir -p /app/data /music

# Volumes
VOLUME ["/app/data", "/music"]

# Port
EXPOSE 8811

# Environment defaults
ENV FLASK_APP=cadenza.app \
    CADENZA_DB_PATH=/app/data/cadenza.db \
    CADENZA_MUSIC_PATH=/music \
    CADENZA_LOG_LEVEL=info \
    CADENZA_SECRET_KEY=change-me

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8811/health')" || exit 1

# Run with gunicorn
CMD ["python", "-m", "gunicorn", \
     "--bind", "0.0.0.0:8811", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "cadenza.app:create_app()"]
