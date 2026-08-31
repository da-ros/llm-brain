"""API Gateway — FastAPI Application.

Main entry point for the microservices architecture.
Handles JWT validation, correlation ID, routing, task status polling,
and Kafka consumer for task responses.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# --- Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("api-gateway")


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
    title="llm-brain API Gateway",
    description="AI-Augmented Digital Brain — API Gateway with correlation ID",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()


# --- Correlation ID Middleware ---
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to every request.

    If X-Request-ID header is present, use it.
    Otherwise, generate a new UUID.
    """
    correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id

    # Log request with correlation_id
    log_with_correlation(correlation_id, "info", f"{request.method} {request.url.path}")

    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


# --- Auth dependency ---
def verify_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    """Verify JWT token and return user info."""
    from jose import jwt, JWTError

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )
        return {"user_id": user_id, "subscription_tier": payload.get("tier", "free")}
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


# --- Health endpoint ---
@app.get("/health")
async def health_check():
    """Public health check endpoint."""
    return {
        "status": "ok",
        "service": "api-gateway",
        "version": "0.1.0",
    }


# --- Task status endpoint ---
@app.get("/tasks/{correlation_id}")
async def get_task_status(
    correlation_id: str,
    user: Annotated[dict, Depends(verify_token)],
):
    """Get task status by correlation ID.

    Used for polling after async operations (file upload).
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    log_with_correlation(correlation_id, "info", "Polling task status")

    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]

    task = await db.task_status.find_one({"_id": correlation_id})
    client.close()

    if not task:
        log_with_correlation(correlation_id, "warning", "Task not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {correlation_id}",
        )

    # Verify user owns this task
    if task.get("user_id") != user["user_id"]:
        log_with_correlation(correlation_id, "warning", "Access denied — wrong user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this task",
        )

    log_with_correlation(correlation_id, "info", f"Task status: {task.get('status')}")

    return {
        "correlation_id": task["_id"],
        "status": task["status"],
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "retries": task.get("retries", 0),
        "http_code": task.get("http_code"),
        "error_message": task.get("error_message"),
        "result": task.get("result"),
    }


# --- Import routers ---
from routers import upload, chat

app.include_router(upload.router)
app.include_router(chat.router)


# --- Kafka Consumer for Task Responses ---
def start_kafka_consumer():
    """Start Kafka consumer in background thread to handle task responses."""
    from kafka import KafkaConsumer

    def process_response(message):
        """Process a task response from Kafka."""
        data = message.value
        correlation_id = data.get("correlation_id")
        response_status = data.get("status")
        http_code = data.get("http_code")
        error_message = data.get("error_message")
        result = data.get("result")

        log_with_correlation(correlation_id, "info", f"Received response: {response_status}")

        # Update MongoDB task_status
        from motor.motor_asyncio import AsyncIOMotorClient
        import asyncio

        async def update_task():
            client = AsyncIOMotorClient(settings.MONGODB_URI)
            db = client[settings.MONGODB_DB]

            # Get current task
            task = await db.task_status.find_one({"_id": correlation_id})
            if not task:
                log_with_correlation(correlation_id, "warning", "Task not found in MongoDB")
                client.close()
                return

            current_retries = task.get("retries", 0)
            max_retries = task.get("max_retries", settings.MAX_RETRIES)

            if response_status == "success":
                # Success — update status
                await db.task_status.update_one(
                    {"_id": correlation_id},
                    {
                        "$set": {
                            "status": "success",
                            "result": result,
                            "http_code": http_code,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                log_with_correlation(correlation_id, "info", "Task completed successfully")

            elif http_code and http_code >= 500:
                # Server error — retry if possible
                if current_retries < max_retries:
                    await db.task_status.update_one(
                        {"_id": correlation_id},
                        {
                            "$set": {
                                "retries": current_retries + 1,
                                "updated_at": datetime.now(timezone.utc),
                            },
                            "$unset": {"status": "in_progress"},
                        },
                    )
                    log_with_correlation(
                        correlation_id, "warning",
                        f"Retrying ({current_retries + 1}/{max_retries})"
                    )

                    # Re-publish to Kafka for retry
                    from kafka import KafkaProducer

                    producer = KafkaProducer(
                        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    )
                    retry_message = {
                        "correlation_id": correlation_id,
                        "user_id": task.get("user_id"),
                        "file_id": task.get("file_id"),
                        "filename": task.get("filename"),
                        "content_type": task.get("content_type"),
                        "service": task.get("service"),
                        "endpoint": task.get("endpoint"),
                    }
                    producer.send(settings.KAFKA_TOPIC_FILE_UPLOADED, value=retry_message)
                    producer.flush()
                    producer.close()
                else:
                    # Max retries reached — DLQ
                    await db.task_status.update_one(
                        {"_id": correlation_id},
                        {
                            "$set": {
                                "status": "dlq-max",
                                "http_code": http_code,
                                "error_message": error_message,
                                "updated_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    log_with_correlation(
                        correlation_id, "error",
                        f"Max retries reached — moved to DLQ: {error_message}"
                    )

            else:
                # Client error (3xx/4xx) — no retry
                await db.task_status.update_one(
                    {"_id": correlation_id},
                    {
                        "$set": {
                            "status": "error",
                            "http_code": http_code,
                            "error_message": error_message,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                log_with_correlation(
                    correlation_id, "error",
                    f"Task failed (no retry): {error_message}"
                )

            client.close()

        # Run async update
        asyncio.run(update_task())

    # Start consumer
    try:
        consumer = KafkaConsumer(
            settings.KAFKA_TOPIC_TASK_RESPONSE,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="api-gateway",
            auto_offset_reset="latest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        logger.info(f"Consuming from topic {settings.KAFKA_TOPIC_TASK_RESPONSE}")

        for message in consumer:
            process_response(message)
    except Exception as e:
        logger.error(f"Kafka consumer error: {str(e)}")


# Start Kafka consumer on startup
@app.on_event("startup")
async def startup_event():
    """Start Kafka consumer in background thread."""
    consumer_thread = threading.Thread(target=start_kafka_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Kafka consumer started")
