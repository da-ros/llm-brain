"""Kafka consumer for session.turn.completed → learn_graph."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from config import get_settings
from graphs import run_learn_graph
from logging_setup import correlation_id_var, log_with_correlation, logger

_stop = threading.Event()
_consumer_thread: threading.Thread | None = None


async def process_session_turn(message: dict[str, Any]) -> dict[str, Any]:
    """Invoke learn_graph for one Kafka payload. Idempotent ingest."""
    correlation_id = message.get("correlation_id") or "no-id"
    token = correlation_id_var.set(correlation_id)
    try:
        log_with_correlation(
            correlation_id,
            "info",
            "Consumed from Kafka: session.turn.completed",
        )
        user_id = message.get("user_id")
        if not user_id:
            log_with_correlation(
                correlation_id, "warning", "session.turn.completed missing user_id"
            )
            return {"error": "missing user_id"}
        state = {
            "user_id": user_id,
            "session_id": message.get("session_id") or "",
            "correlation_id": correlation_id,
            "query": message.get("query") or "",
            "response": message.get("response") or "",
            "assumptions": message.get("assumptions") or [],
            "sources": message.get("sources") or [],
        }
        return await run_learn_graph(state)
    finally:
        correlation_id_var.reset(token)


def _save_on_server_loop(loop: asyncio.AbstractEventLoop, message: dict[str, Any]) -> None:
    """Save one turn on the server loop. The database client is bound to that loop."""
    try:
        asyncio.run_coroutine_threadsafe(process_session_turn(message), loop).result()
    except Exception:
        logger.exception("session.turn.completed was not saved")


def _consume(loop: asyncio.AbstractEventLoop) -> None:
    from kafka import KafkaConsumer

    settings = get_settings()
    try:
        consumer = KafkaConsumer(
            settings.KAFKA_TOPIC_SESSION_TURN,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_CONSUMER_GROUP,
            auto_offset_reset="earliest",
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
            consumer_timeout_ms=1000,
        )
    except Exception:
        logger.exception("Kafka consumer failed to start")
        return

    logger.info("Consuming from topic %s", settings.KAFKA_TOPIC_SESSION_TURN)
    try:
        while not _stop.is_set():
            records = consumer.poll(timeout_ms=1000)
            for _tp, messages in records.items():
                for message in messages:
                    _save_on_server_loop(loop, message.value)
    except Exception:
        logger.exception("Kafka consumer error")
    finally:
        consumer.close()


def start_consumer_thread() -> None:
    """Start the session.turn.completed consumer in a daemon thread."""
    global _consumer_thread
    loop = asyncio.get_running_loop()
    _stop.clear()
    _consumer_thread = threading.Thread(
        target=_consume,
        args=(loop,),
        name="agents-kafka-consumer",
        daemon=True,
    )
    _consumer_thread.start()
    logger.info("Kafka consumer started")


def stop_consumer_thread() -> None:
    """Signal the consumer loop to exit."""
    _stop.set()
