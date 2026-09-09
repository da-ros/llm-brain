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
- **S** (Single Responsibility): Cada provider hace una cosa (inferencia Qwen3.5-4B en el contenedor local)
- **O** (Open/Closed): Nuevo provider se agrega sin modificar el resolver
- **D** (Dependency Inversion): El servicio depende del Protocol, no de la implementación

### 1.2 Servicio separado de Fine-Tuning

**Decisión**: Inferencia y fine-tuning en microservicios separados.

**Justificación**:
- **Inferencia** (port 8003): Requests síncronos, timeout 30s, alta disponibilidad
- **Fine-Tuning** (port 8004): Jobs asíncronos, pueden durar horas, baja frecuencia
- Escalado independiente: inference necesita más instances que training
- Fault isolation: un error de training no afecta inference

### 1.3 Qwen3.5-4B en contenedor local (no AWS Bedrock, no OpenAI)

**Decisión**: Qwen3.5-4B servido en un contenedor Docker local ("cloud" = contenedor local) para inference.

**Justificación**:
- Un único modelo para todo: Qwen3.5-4B (dense, nativo multimodal — texto, imagen, video; 262K ctx; Apache 2.0; ~8 GB BF16, ~2.5–3 GB Q4)
- $0 y totalmente local — MVP solo local; AWS Bedrock/ECS/API Gateway quedan como trabajo futuro
- Misma familia Qwen para on-device (Frame 10) y embeddings (Qwen3-VL-Embedding-2B)

## 2. Patrones de Diseño Aplicados

### Strategy Pattern (Provider Resolver)

```python
# El resolver selecciona la estrategia (provider) según el tier
def get_provider(tier: str) -> LLMProvider:
    if tier == "premium":
        return QwenLocalProvider(...)  # Estrategia premium (contenedor local + LoRA)
    else:
        raise ValueError("Free tier uses on-device base Qwen3.5-4B in the React Native app (Frame 10)")
```

### Adapter Pattern (QwenLocalProvider)

```python
# QwenLocalProvider adapta la API del contenedor local Qwen3.5-4B a nuestro protocol
class QwenLocalProvider:
    def chat(self, messages, context=None) -> str:
        # Adapta messages → formato del contenedor Qwen3.5-4B (multimodal: texto/imagen/video)
        # Adapta la respuesta de Qwen3.5-4B → str
```

### Dependency Inversion

```python
# El servicio depende del Protocol (abstracción), no de QwenLocalProvider (concreción)
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

### 3.3 POST /generate (error del contenedor local)

```
2026-08-31T10:00:00 [ghi-789] INFO llm-service: POST /generate — prompt length: 20 chars, user_id: user3
2026-08-31T10:00:01 [ghi-789] ERROR llm-service: LLM error: Qwen3.5-4B container unavailable
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
| **S** (Single Responsibility) | Cada provider hace una cosa: QwenLocalProvider solo habla con el contenedor local Qwen3.5-4B |
| **O** (Open/Closed) | Nuevo provider (ej: otro backend local) se agrega sin modificar el resolver |
| **L** (Liskov Substitution) | Cualquier implementación de LLMProvider puede sustituir a otra |
| **I** (Interface Segregation) | Protocol solo expone `chat()` y `complete()` — no métodos innecesarios |
| **D** (Dependency Inversion) | El servicio depende del Protocol (abstracción), no del contenedor Qwen3.5-4B (concreción) |
