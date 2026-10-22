"""Kafka producer / consumer for async file processing.

Producer: POST /api/upload → topic file.uploaded
Consumer: topic task.response → update MongoDB task_status
DLQ: permanent failures (dlq-max) are published to topic task.dlq

Retry policy (design):
  5xx and retries < max_retries → re-publish to file.uploaded
  3xx/4xx → status error, no retry
  5xx and retries >= max_retries → status dlq-max
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Literal

import db
import httpx
from config import get_settings
from logging_setup import log_with_correlation, logger

ResponseAction = Literal["success", "retry", "error", "dlq-max"]

_stop = threading.Event()
_consumer_thread: threading.Thread | None = None
# Motor is bound to the uvicorn loop. The consumer thread must schedule
# handlers there; a private loop raises "attached to a different loop".
_loop: asyncio.AbstractEventLoop | None = None


def classify_response(
    response_status: str,
    http_code: int | None,
    retries: int,
    max_retries: int,
) -> ResponseAction:
    """Decide how to handle a task.response payload."""
    if response_status == "success":
        return "success"
    if http_code is not None and http_code >= 500:
        if retries < max_retries:
            return "retry"
        return "dlq-max"
    return "error"


def _producer():
    from kafka import KafkaProducer

    settings = get_settings()
    return KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )


def publish_session_turn_completed(message: dict[str, Any]) -> None:
    """Publish a completed premium chat turn for learn_graph (after HTTP 200)."""
    settings = get_settings()
    correlation_id = message.get("correlation_id", "no-id")
    log_with_correlation(
        correlation_id,
        "info",
        f"Publishing to Kafka: {settings.KAFKA_TOPIC_SESSION_TURN}",
    )
    producer = _producer()
    try:
        producer.send(settings.KAFKA_TOPIC_SESSION_TURN, value=message)
        producer.flush()
    finally:
        producer.close()
    log_with_correlation(
        correlation_id,
        "info",
        f"Published to Kafka: {settings.KAFKA_TOPIC_SESSION_TURN}",
    )


def publish_file_uploaded(message: dict[str, Any]) -> None:
    """Publish a file-upload job to Kafka."""
    settings = get_settings()
    correlation_id = message.get("correlation_id", "no-id")
    log_with_correlation(
        correlation_id,
        "info",
        f"Publishing to Kafka: {settings.KAFKA_TOPIC_FILE_UPLOADED}",
    )
    producer = _producer()
    try:
        producer.send(settings.KAFKA_TOPIC_FILE_UPLOADED, value=message)
        producer.flush()
    finally:
        producer.close()
    log_with_correlation(
        correlation_id,
        "info",
        f"Published to Kafka: {settings.KAFKA_TOPIC_FILE_UPLOADED}",
    )


def publish_dlq(message: dict[str, Any]) -> None:
    """Publish a permanently failed task to the dead-letter topic."""
    settings = get_settings()
    correlation_id = message.get("correlation_id", "no-id")
    producer = _producer()
    try:
        producer.send(settings.KAFKA_TOPIC_DLQ, value=message)
        producer.flush()
    finally:
        producer.close()
    log_with_correlation(
        correlation_id,
        "error",
        f"Max retries reached — moved to DLQ ({settings.KAFKA_TOPIC_DLQ})",
    )


def file_uploaded_message(task: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the file.uploaded payload from a task_status document."""
    settings = get_settings()
    return {
        "correlation_id": task["_id"],
        "user_id": task.get("user_id"),
        "file_id": str(task.get("file_id")),
        "filename": task.get("filename"),
        "content_type": task.get("content_type"),
        "service": task.get("service", "etl-service"),
        "endpoint": task.get("endpoint", f"{settings.ETL_SERVICE_URL}/process"),
    }


async def trigger_rag_ingest(
    task: dict[str, Any],
    result: dict[str, Any] | None,
    correlation_id: str,
) -> None:
    """After ETL success, POST JSONL triples into the RAG vector store."""
    settings = get_settings()
    user_id = task.get("user_id")
    if not user_id:
        return
    output_path = (result or {}).get("output_path")
    if not output_path:
        output_path = f"/app/data/triples/{user_id}/{correlation_id}.jsonl"
    payload = {
        "user_id": user_id,
        "doc_id": correlation_id,
        "triples_path": output_path,
        "gridfs_id": str(task.get("file_id") or ""),
        "doc_type": task.get("content_type") or "text",
        "filename": task.get("filename") or "",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.RAG_SERVICE_URL}/ingest",
                json=payload,
                headers={"X-Request-ID": correlation_id},
            )
        if response.status_code >= 400:
            log_with_correlation(
                correlation_id,
                "warning",
                f"RAG ingest failed: HTTP {response.status_code}",
            )
            return
        count = (response.json() or {}).get("triples_count", 0)
        log_with_correlation(correlation_id, "info", f"RAG ingested {count} triples")
    except Exception as exc:
        log_with_correlation(correlation_id, "warning", f"RAG ingest skipped: {exc}")


async def apply_task_response(data: dict[str, Any]) -> None:
    """Update task_status from a Kafka task.response message."""
    correlation_id = data.get("correlation_id")
    if not correlation_id:
        logger.warning("task.response missing correlation_id")
        return

    log_with_correlation(correlation_id, "info", "Consumed from Kafka: task.response")

    task = await db.find_task(correlation_id)
    if not task:
        log_with_correlation(correlation_id, "warning", "Task not found in MongoDB")
        return

    response_status = data.get("status", "error")
    http_code = data.get("http_code")
    error_message = data.get("error_message")
    result = data.get("result")
    current_retries = int(task.get("retries", 0))
    max_retries = int(task.get("max_retries", get_settings().MAX_RETRIES))
    action = classify_response(response_status, http_code, current_retries, max_retries)

    log_with_correlation(
        correlation_id,
        "info" if action == "success" else "warning",
        f"Task response: {response_status} (http_code={http_code})",
    )

    if action == "success":
        await db.update_task(
            correlation_id,
            {
                "status": "success",
                "result": result,
                "http_code": http_code,
                "error_message": None,
            },
        )
        log_with_correlation(correlation_id, "info", "Task completed successfully")
        await trigger_rag_ingest(task, result, correlation_id)
        return

    if action == "retry":
        next_retries = current_retries + 1
        await db.update_task(
            correlation_id,
            {
                "status": "in_progress",
                "retries": next_retries,
                "http_code": http_code,
                "error_message": error_message,
            },
        )
        log_with_correlation(
            correlation_id,
            "warning",
            f"Retrying ({next_retries}/{max_retries}) — re-publishing to Kafka",
        )
        publish_file_uploaded(file_uploaded_message(task))
        return

    if action == "dlq-max":
        await db.update_task(
            correlation_id,
            {
                "status": "dlq-max",
                "http_code": http_code,
                "error_message": error_message,
            },
        )
        publish_dlq(
            {
                **file_uploaded_message(task),
                "status": "dlq-max",
                "http_code": http_code,
                "error_message": error_message,
                "retries": current_retries,
            }
        )
        return

    await db.update_task(
        correlation_id,
        {
            "status": "error",
            "http_code": http_code,
            "error_message": error_message,
        },
    )
    log_with_correlation(
        correlation_id,
        "error",
        f"Task failed (no retry): {error_message}",
    )


def _submit_task_response(payload: dict[str, Any]) -> None:
    """Run the handler on the application loop, where Motor was created."""
    if _loop is None or _loop.is_closed():
        logger.error("task.response dropped: application event loop is not running")
        return
    future = asyncio.run_coroutine_threadsafe(apply_task_response(payload), _loop)
    try:
        future.result()
    except Exception:
        logger.exception("task.response handler failed")


def _consume() -> None:
    from kafka import KafkaConsumer

    settings = get_settings()
    try:
        consumer = KafkaConsumer(
            settings.KAFKA_TOPIC_TASK_RESPONSE,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            auto_offset_reset="latest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            consumer_timeout_ms=1000,
        )
    except Exception:
        logger.exception("Kafka consumer failed to start")
        return

    logger.info("Consuming from topic %s", settings.KAFKA_TOPIC_TASK_RESPONSE)
    try:
        while not _stop.is_set():
            records = consumer.poll(timeout_ms=1000)
            for _tp, messages in records.items():
                for message in messages:
                    _submit_task_response(message.value)
    except Exception:
        logger.exception("Kafka consumer error")
    finally:
        consumer.close()


def start_consumer_thread() -> None:
    """Start the task.response consumer in a daemon thread."""
    global _consumer_thread, _loop
    _stop.clear()
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = None
        logger.error("Kafka consumer started without a running event loop")
    _consumer_thread = threading.Thread(
        target=_consume,
        name="api-router-kafka-consumer",
        daemon=True,
    )
    _consumer_thread.start()
    logger.info("Kafka consumer started")


def stop_consumer_thread() -> None:
    """Signal the consumer loop to exit."""
    _stop.set()
