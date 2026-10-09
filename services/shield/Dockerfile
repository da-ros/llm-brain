FROM python:3.13-slim

WORKDIR /app

# tesseract reads the text on a screenshot. eng+spa matches the OCR call.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8009

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8009"]
