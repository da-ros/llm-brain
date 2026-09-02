# Spec: LLM Service

## Overview

Microservicio de inferencia LLM que recibe requests del API Router y los procesa
usando AWS Bedrock (Llama 3 8B). Solo para usuarios premium.

## Port

8003

## Endpoints

### POST /generate

Realiza una completion de texto.

**Request**:
```json
{
  "prompt": "¿Cuándo debo tomar la medicina?",
  "user_id": "user-123"
}
```

**Response 200**:
```json
{
  "response": "Basado en tu receta médica...",
  "tokens_used": 150
}
```

**Errors**:
- 400: Invalid request (missing prompt)
- 401: Invalid/missing API key (internal)
- 500: Bedrock error (throttling, model not found)
- 504: Bedrock timeout

### POST /chat

Realiza un chat con contexto RAG opcional.

**Request**:
```json
{
  "messages": [
    {"role": "user", "content": "¿Qué debo comprar esta semana?"}
  ],
  "context": "Receta: Ibuprofeno 400mg, 3 veces al día",
  "user_id": "user-123"
}
```

**Response 200**:
```json
{
  "response": "Basado en tu receta, deberías comprar Ibuprofeno...",
  "tokens_used": 200
}
```

### GET /health

Health check público.

**Response 200**:
```json
{
  "status": "ok",
  "service": "llm-service",
  "provider": "bedrock",
  "model": "meta.llama3-8b-instruct-v1:0",
  "version": "0.1.0"
}
```

## Configuration

| Variable | Default | Descripción |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | — | AWS credential (required) |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credential (required) |
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | Bedrock model |
| `LLM_HOST` | `0.0.0.0` | Bind host |
| `LLM_PORT` | `8003` | Bind port |

## Dependencies

- AWS Bedrock (Llama 3 8B)
- boto3 (AWS SDK)

## Integration

- **Upstream**: API Router (`services/api-router/routers/chat.py`) llama a `http://llm-service:8003/generate`
- **Downstream**: AWS Bedrock API

## Correlation ID

El servicio propagа el header `X-Request-ID` en logs estructurados:
```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars
2026-08-31T10:00:01 [abc-123] INFO llm-service: Bedrock response: 150 tokens
```
