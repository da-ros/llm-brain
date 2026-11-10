FROM python:3.13-slim

WORKDIR /app

# ffmpeg decodes a few frames. The embedding model only encodes images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-embedding.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-embedding.txt

# HEIC photos. Separate from the torch install so that layer stays cached.
RUN pip install --no-cache-dir pi_heif==1.1.1

COPY . .

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
