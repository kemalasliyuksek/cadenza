FROM python:3.12-slim

# Install system dependencies (ffmpeg for audio, nodejs for yt-dlp signature solving)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install yt-dlp with all extras (includes EJS challenge solver)
RUN pip install --no-cache-dir --upgrade "yt-dlp[default]"

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
    CADENZA_LOG_LEVEL=info

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
