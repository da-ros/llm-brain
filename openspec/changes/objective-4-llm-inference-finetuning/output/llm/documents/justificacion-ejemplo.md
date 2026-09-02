# Justificación Técnica — LLM Service

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

### 1.2 Servicio separado de Fine-Tuning

**Decisión**: Inferencia y fine-tuning en microservicios separados.

**Justificación**:
- **Inferencia** (port 8003): Requests síncronos, timeout 30s, alta disponibilidad
- **Fine-Tuning** (port 8004): Jobs asíncronos, pueden durar horas, baja frecuencia
- Escalado independiente: inference necesita más instances que training
- Fault isolation: un error de training no afecta inference

### 1.3 AWS Bedrock (no OpenAI, no self-hosted)

**Decisión**: AWS Bedrock para inference.

**Justificación**:
- Managed service — sin infraestructura que mantener
- Free tier 750h/mes para Llama 3 8B
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

### 3.1 POST /generate (éxito)

```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars, user_id: user1
2026-08-31T10:00:01 [abc-123] INFO llm-service: Response: 200 OK — tokens_used: 0
```

### 3.2 POST /generate (tier inválido)

```
2026-08-31T10:00:00 [def-456] INFO llm-service: POST /generate — prompt length: 30 chars, user_id: user2
2026-08-31T10:00:00 [def-456] WARNING llm-service: Invalid tier: free
```

### 3.3 POST /generate (error Bedrock)

```
2026-08-31T10:00:00 [ghi-789] INFO llm-service: POST /generate — prompt length: 20 chars, user_id: user3
2026-08-31T10:00:01 [ghi-789] ERROR llm-service: LLM error: ThrottlingException
```

### 3.4 POST /chat (éxito)

```
2026-08-31T10:00:00 [jkl-012] INFO llm-service: POST /chat — messages: 1, user_id: user1
2026-08-31T10:00:01 [jkl-012] INFO llm-service: Response: 200 OK — tokens_used: 0
```

### 3.5 POST /chat (tier inválido)

```
2026-08-31T10:00:00 [mno-345] INFO llm-service: POST /chat — messages: 2, user_id: user4
2026-08-31T10:00:00 [mno-345] WARNING llm-service: Invalid tier: free
```

### 3.6 GET /health

```
2026-08-31T10:00:00 [pqr-678] INFO llm-service: GET /health
```

## 4. Principios SOLID Aplicados

| Principio | Aplicación |
|-----------|-----------|
| **S** (Single Responsibility) | Cada provider hace una cosa: BedrockProvider solo habla con Bedrock |
| **O** (Open/Closed) | Nuevo provider (ej: OpenAI) se agrega sin modificar el resolver |
| **L** (Liskov Substitution) | Cualquier implementación de LLMProvider puede sustituir a otra |
| **I** (Interface Segregation) | Protocol solo expone `chat()` y `complete()` — no métodos innecesarios |
| **D** (Dependency Inversion) | El servicio depende del Protocol (abstracción), no de Bedrock (concreción) |
