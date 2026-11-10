"""Kafka consumer/producer for the ETL Service.

Consume file.uploaded → distill → publish task.response.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from config import get_settings
from exceptions import (
    CorruptFileError,
    FileTooLargeError,
    LLMExtractionError,
    LoaderError,
    UnsupportedFileTypeError,
)
from gridfs_store import fetch_file
from logging_setup import log_with_correlation, logger
from pipeline import distill

_stop = threading.Event()
_consumer_thread: threading.Thread | None = None


def _producer():
    from kafka import KafkaProducer

    settings = get_settings()
    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )


def publish_task_response(payload: dict[str, Any]) -> None:
    """Publish success/error to Kafka topic task.response."""
    settings = get_settings()
    correlation_id = payload.get("correlation_id", "no-id")
    producer = _producer()
    try:
        producer.send(settings.KAFKA_TOPIC_TASK_RESPONSE, value=payload)
        producer.flush()
    finally:
        producer.close()
    log_with_correlation(
        correlation_id,
        "info" if payload.get("status") == "success" else "error",
        f"Published to Kafka: {settings.KAFKA_TOPIC_TASK_RESPONSE} ({payload.get('status')})",
    )


def _clip_summary(triples: list, limit: int = 250) -> str:
    parts = [
        " ".join(part for part in (item.subject, item.predicate, item.object) if part)
        for item in triples
    ]
    compact = "; ".join(" ".join(part.split()) for part in parts if part.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def process_file_message(
    message: dict[str, Any],
    *,
    llm_client=None,
    output_dir: str | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Run distillation for one Kafka file.uploaded payload."""
    correlation_id = message.get("correlation_id") or "no-id"
    user_id = message.get("user_id") or "unknown"
    file_id = message.get("file_id")
    filename = message.get("filename") or "upload.bin"
    content_type = message.get("content_type")

    log_with_correlation(
        correlation_id,
        "info",
        f"Consumed from Kafka: file.uploaded — Processing file: {filename} (user_id={user_id})",
    )

    if not file_id:
        response = _error_payload(correlation_id, 422, "Missing file_id in Kafka message")
        if publish:
            publish_task_response(response)
        return response

    try:
        payload, stored_name, stored_type = fetch_file(file_id, correlation_id=correlation_id)
        name = stored_name or filename
        mime = content_type or stored_type
        suffix = Path(name).suffix or ""
        tmp_path = _write_temp(payload, suffix)
        try:
            triples = distill(
                tmp_path,
                user_id=user_id,
                document_id=correlation_id,
                mime_type=mime,
                llm_client=llm_client,
                output_dir=output_dir,
                correlation_id=correlation_id,
                filename=name,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        settings = get_settings()
        triples_dir = output_dir or settings.TRIPLES_OUTPUT_DIR
        output_path = f"{triples_dir}/{user_id}/{correlation_id}.jsonl"
        response = {
            "correlation_id": correlation_id,
            "status": "success",
            "http_code": 200,
            "result": {
                "triples_count": len(triples),
                "output_path": output_path,
                "summary": _clip_summary(triples),
            },
        }
        if publish:
            publish_task_response(response)
        return response
    except (UnsupportedFileTypeError, CorruptFileError, LoaderError, FileTooLargeError) as exc:
        response = _error_payload(correlation_id, 422, str(exc))
        if publish:
            publish_task_response(response)
        return response
    except FileNotFoundError as exc:
        response = _error_payload(correlation_id, 422, str(exc))
        if publish:
            publish_task_response(response)
        return response
    except LLMExtractionError as exc:
        log_with_correlation(correlation_id, "error", f"Processing failed: {exc}")
        response = _error_payload(correlation_id, 500, str(exc))
        if publish:
            publish_task_response(response)
        return response
    except Exception as exc:
        log_with_correlation(correlation_id, "error", f"Processing failed: {exc}")
        response = _error_payload(correlation_id, 500, str(exc))
        if publish:
            publish_task_response(response)
        return response


def _error_payload(correlation_id: str, http_code: int, error_message: str) -> dict[str, Any]:
    log_with_correlation(correlation_id, "error", f"Processing failed: {error_message}")
    return {
        "correlation_id": correlation_id,
        "status": "error",
        "http_code": http_code,
        "error_message": error_message,
    }


def _write_temp(payload: bytes, suffix: str) -> str:
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        handle.flush()
        return handle.name


def _consume() -> None:
    from kafka import KafkaConsumer

    settings = get_settings()
    try:
        consumer = KafkaConsumer(
            settings.KAFKA_TOPIC_FILE_UPLOADED,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            auto_offset_reset="earliest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            consumer_timeout_ms=1000,
        )
    except Exception:
        logger.exception("Kafka consumer failed to start")
        return

    logger.info("Consuming from topic %s", settings.KAFKA_TOPIC_FILE_UPLOADED)
    try:
        while not _stop.is_set():
            records = consumer.poll(timeout_ms=1000)
            for _tp, messages in records.items():
                for message in messages:
                    process_file_message(message.value)
    except Exception:
        logger.exception("Kafka consumer error")
    finally:
        consumer.close()


def start_consumer_thread() -> None:
    """Start the file.uploaded consumer in a daemon thread."""
    global _consumer_thread
    _stop.clear()
    _consumer_thread = threading.Thread(
        target=_consume,
        name="etl-kafka-consumer",
        daemon=True,
    )
    _consumer_thread.start()
    logger.info("Kafka consumer started in background")


def stop_consumer_thread() -> None:
    """Signal the consumer loop to exit."""
    _stop.set()
