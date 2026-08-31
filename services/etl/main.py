"""ETL Service — Standalone Microservice.

Consumes from Kafka, processes documents, publishes results.
Runs on Port 8001 as an independent FastAPI service.
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from config import settings

# --- Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("etl-service")


class CorrelationFilter(logging.Filter):
    """Add correlation_id to all log records."""

    def filter(self, record):
        record.correlation_id = getattr(record, "correlation_id", "no-id")
        return True


logger.addFilter(CorrelationFilter())


def log_with_correlation(correlation_id: str, level: str, message: str):
    """Log a message with correlation_id context."""
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)


app = FastAPI(
    title="ETL Service",
    description="Memory Distillation — Document processing and triple extraction",
    version="0.1.0",
)


# --- Health endpoint ---
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "etl-service",
        "version": "0.1.0",
    }


# --- Kafka Consumer ---
def start_kafka_consumer():
    """Start Kafka consumer in background thread."""
    from kafka import KafkaConsumer, KafkaProducer

    def process_message(message):
        """Process a file upload message from Kafka."""
        correlation_id = message.value.get("correlation_id")
        user_id = message.value.get("user_id")
        file_id = message.value.get("file_id")
        filename = message.value.get("filename")
        content_type = message.value.get("content_type")

        log_with_correlation(correlation_id, "info", f"Processing file: {filename}")

        try:
            # Fetch file from MongoDB GridFS
            from motor.motor_asyncio import AsyncIOMotorClient
            from gridfs import GridFS

            log_with_correlation(correlation_id, "info", "Fetching file from MongoDB GridFS")
            client = AsyncIOMotorClient(settings.MONGODB_URI)
            db = client[settings.MONGODB_DB]
            fs = GridFS(db)

            # Get file from GridFS
            from bson import ObjectId

            file_data = fs.get(ObjectId(file_id))
            log_with_correlation(correlation_id, "info", "File fetched successfully")

            # Save to temporary file for processing
            import tempfile

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{filename}"
            ) as tmp:
                tmp.write(file_data.read())
                tmp_path = tmp.name

            try:
                # Process file with ETL pipeline
                from services.etl.pipeline import distill, save_triples

                log_with_correlation(correlation_id, "info", "Starting ETL pipeline")
                triples = distill(tmp_path)
                log_with_correlation(correlation_id, "info", f"Extracted {len(triples)} triples")

                # Save triples to output directory
                output_dir = f"{settings.TRIPLES_OUTPUT_DIR}/{user_id}"
                output_path = f"{output_dir}/{correlation_id}.jsonl"
                triples_count = save_triples(triples, output_path)
                log_with_correlation(correlation_id, "info", f"Saved {triples_count} triples to {output_path}")

                # Publish success response
                producer = KafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )

                response = {
                    "correlation_id": correlation_id,
                    "status": "success",
                    "http_code": 200,
                    "triples_count": triples_count,
                    "output_path": output_path,
                }

                producer.send(settings.KAFKA_TOPIC_TASK_RESPONSE, value=response)
                producer.flush()
                producer.close()

                log_with_correlation(correlation_id, "info", f"Published success response: {triples_count} triples")

            finally:
                # Clean up temp file
                os.unlink(tmp_path)

        except Exception as e:
            # Publish error response
            log_with_correlation(correlation_id, "error", f"Processing failed: {str(e)}")

            producer = KafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )

            response = {
                "correlation_id": correlation_id,
                "status": "error",
                "http_code": 500,
                "error_message": str(e),
            }

            producer.send(settings.KAFKA_TOPIC_TASK_RESPONSE, value=response)
            producer.flush()
            producer.close()

            log_with_correlation(correlation_id, "error", "Published error response")

    # Start consumer
    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC_FILE_UPLOADED,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="etl-service",
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    logger.info(f"Consuming from topic {settings.KAFKA_TOPIC_FILE_UPLOADED}")

    for message in consumer:
        process_message(message)


# Start Kafka consumer in background thread
@app.on_event("startup")
async def startup_event():
    """Start Kafka consumer on service startup."""
    consumer_thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Kafka consumer started in background")
