# ═══════════════════════════════════════════════════════════
# 🐳 NAGU ULTRA DOWNLOADER - DOCKER IMAGE
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY bot.py .
COPY audiohandler.py .
COPY cookies_*.txt ./

# Copy application modules
COPY core/ ./core/
COPY downloaders/ ./downloaders/
COPY ui/ ./ui/
COPY utils/ ./utils/
COPY workers/ ./workers/

# Create temp directory
RUN mkdir -p /tmp/downloads

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["python", "-u", "bot.py"]
