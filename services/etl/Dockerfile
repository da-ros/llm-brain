FROM python:3.13-slim

WORKDIR /app

# libmagic = python-magic MIME detection.
# tesseract/poppler/ffmpeg = runtime for Unstructured* loaders (OCR/PDF/video),
# not a bespoke Tesseract pipeline in our code.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    poppler-utils \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data/triples

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
