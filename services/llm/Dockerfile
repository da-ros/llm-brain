# Linux GPU image. On this Mac the same app runs on the host so it can use Metal.
FROM python:3.13-slim

WORKDIR /app

# ffmpeg lets the processor read a short clip. The vision encoder ships
# inside the Qwen3.5-4B weights, which load when QWEN_MOCK=false.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-gpu.txt .
RUN pip install --no-cache-dir -r requirements-gpu.txt

COPY . .

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
