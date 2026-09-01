# Justificación Técnica — LLM Cloud (Bedrock) + Fine-Tuning Services

## 1. Decisiones de Diseño

### 1.1 Protocol-based Provider (no herencia)

**Decisión**: Usar Python Protocol (structural subtyping) en lugar de ABC (herencia).

**Justificación**:
- No requiere herencia — cualquier clase con `chat()` y `complete()` cumple el protocolo
- Fácil de mockear para testing
- Desacoplado: el servicio no conoce la implementación concreta

**Patrón de diseño**: Strategy Pattern — el provider selection es una estrategia que cambia según el tier.

**SOLID**:
- **S** (Single Responsibility): Cada provider hace una cosa (Bedrock inference)
- **O** (Open/Closed): Nuevo provider se agrega sin modificar el resolver
- **D** (Dependency Inversion): El servicio depende del Protocol, no de la implementación

### 1.2 Servicios separados (LLM vs Fine-Tune)

**Decisión**: Inferencia y fine-tuning en microservicios separados.

**Justificación**:
- **Inferencia** (port 8003): Requests síncronos, timeout 30s, alta disponibilidad
- **Fine-Tuning** (port 8004): Jobs asíncronos, pueden durar horas, baja frecuencia
- Escalado independiente: inference necesita más instances que training
- Fault isolation: un error de training no afecta inference

### 1.3 AWS Bedrock (no OpenAI, no self-hosted)

**Decisión**: AWS Bedrock para inference y fine-tuning.

**Justificación**:
- Managed service — sin infraestructura que mantener
- Free tier 750h/mes para Llama 3 8B
- Soporte nativo para LoRA fine-tuning
- Mismo provider para training e inference (consistencia)

## 2. Patrones de Diseño Aplicados

### Strategy Pattern (Provider Resolver)

```python
# El resolver selecciona la estrategia (provider) según el tier
def get_provider(tier: str) -> LLMProvider:
    if tier == "premium":
        return BedrockProvider(...)  # Estrategia premium
    else:
        raise ValueError("Free tier uses on-device LLM (Frame 10)")
```

### Adapter Pattern (BedrockProvider)

```python
# BedrockProvider adapta la API de boto3/Bedrock a nuestro protocol
class BedrockProvider:
    def chat(self, messages, context=None) -> str:
        # Adapta messages → Bedrock API format
        # Adapta Bedrock response → str
```

### Dependency Inversion

```python
# El servicio depende del Protocol (abstracción), no de BedrockProvider (concreción)
from services.llm.providers.base import LLMProvider  # Protocol

def generate(prompt: str, provider: LLMProvider) -> str:
    return provider.complete(prompt)  # No sabe qué provider es
```

## 3. Ejemplos de Logs

### 3.1 LLM Service — POST /generate

```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars
2026-08-31T10:00:00 [abc-123] INFO llm-service: Provider resolved: BedrockProvider
2026-08-31T10:00:00 [abc-123] INFO llm-service: Calling AWS Bedrock — model: meta.llama3-8b-instruct-v1:0
2026-08-31T10:00:01 [abc-123] INFO llm-service: Bedrock response: 150 tokens, 0.8s latency
2026-08-31T10:00:01 [abc-123] INFO llm-service: Response: 200 OK — tokens_used: 150
```

### 3.2 LLM Service — POST /chat

```
2026-08-31T10:00:00 [def-456] INFO llm-service: POST /chat — messages: 1, context: 200 chars
2026-08-31T10:00:00 [def-456] INFO llm-service: Provider resolved: BedrockProvider
2026-08-31T10:00:00 [def-456] INFO llm-service: Building prompt with RAG context
2026-08-31T10:00:00 [def-456] INFO llm-service: Calling AWS Bedrock — model: meta.llama3-8b-instruct-v1:0
2026-08-31T10:00:01 [def-456] INFO llm-service: Bedrock response: 200 tokens, 1.2s latency
2026-08-31T10:00:01 [def-456] INFO llm-service: Response: 200 OK — tokens_used: 200
```

### 3.3 LLM Service — Error (Bedrock throttling)

```
2026-08-31T10:00:00 [ghi-789] INFO llm-service: POST /generate — prompt length: 30 chars
2026-08-31T10:00:00 [ghi-789] INFO llm-service: Calling AWS Bedrock
2026-08-31T10:00:01 [ghi-789] ERROR llm-service: Bedrock error: ThrottlingException — Too many requests
2026-08-31T10:00:01 [ghi-789] ERROR llm-service: Response: 503 Service Unavailable
```

### 3.4 Fine-Tune Service — POST /train

```
2026-08-31T10:00:00 [jkl-012] INFO finetune-service: POST /train — dataset: data/triples/user-123/receta.jsonl
2026-08-31T10:00:00 [jkl-012] INFO finetune-service: Validating dataset — 50 triples found
2026-08-31T10:00:00 [jkl-012] INFO finetune-service: Converting triples → Bedrock training format
2026-08-31T10:00:01 [jkl-012] INFO finetune-service: Submitting LoRA job to Bedrock — epochs: 5, lr: 0.001
2026-08-31T10:00:02 [jkl-012] INFO finetune-service: Job submitted: ft-job-abc-123
2026-08-31T10:00:02 [jkl-012] INFO finetune-service: Response: 202 Accepted — job_id: ft-job-abc-123
```

### 3.5 Fine-Tune Service — GET /status

```
2026-08-31T12:00:00 [jkl-012] INFO finetune-service: GET /status/ft-job-abc-123
2026-08-31T12:00:00 [jkl-012] INFO finetune-service: Polling Bedrock training job status
2026-08-31T12:00:01 [jkl-012] INFO finetune-service: Job completed — loss: 0.15, time: 1.8h
2026-08-31T12:00:01 [jkl-012] INFO finetune-service: Saving LoRA adapter to s3://llm-brain/models/user-123/adapter/
2026-08-31T12:00:02 [jkl-012] INFO finetune-service: Response: 200 OK — status: completed
```

### 3.6 Fine-Tune Service — Training failed

```
2026-08-31T14:00:00 [mno-345] INFO finetune-service: GET /status/ft-job-xyz-789
2026-08-31T14:00:00 [mno-345] WARNING finetune-service: Job failed — Bedrock error: InvalidTrainingData
2026-08-31T14:00:00 [mno-345] ERROR finetune-service: Response: 200 OK — status: failed
```

## 4. Principios SOLID Aplicados

| Principio | Aplicación |
|-----------|-----------|
| **S** (Single Responsibility) | Cada provider hace una cosa: BedrockProvider solo habla con Bedrock |
| **O** (Open/Closed) | Nuevo provider (ej: OpenAI) se agrega sin modificar el resolver |
| **L** (Liskov Substitution) | Cualquier implementación de LLMProvider puede sustituir a otra |
| **I** (Interface Segregation) | Protocol solo expone `chat()` y `complete()` — no métodos innecesarios |
| **D** (Dependency Inversion) | El servicio depende del Protocol (abstracción), no de Bedrock (concreción) |
