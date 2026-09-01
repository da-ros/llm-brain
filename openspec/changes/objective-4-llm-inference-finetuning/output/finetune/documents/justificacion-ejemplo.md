# Justificación Técnica — Fine-Tune Service

## 1. Decisiones de Diseño

### 1.1 Servicio separado de Inference

**Decisión**: Fine-tuning en microservicio independiente del LLM Service.

**Justificación**:
- **Inferencia** (port 8003): Requests síncronos, timeout 30s, alta disponibilidad
- **Fine-Tuning** (port 8004): Jobs asíncronos, pueden durar horas, baja frecuencia
- Escalado independiente: inference necesita más instances que training
- Fault isolation: un error de training no afecta inference
- Training jobs son pesados — no deben bloquear el event loop del inference service

### 1.2 LoRA (Low-Rank Adaptation)

**Decisión**: LoRA para fine-tuning de Llama 3 8B.

**Justificación**:
- Parameter-efficient (<1% of weights trained)
- Lower compute cost que full fine-tuning
- Preserva capacidades del modelo base
- AWS Bedrock soporta LoRA nativamente

### 1.3 In-Memory Job Store (stubbed)

**Decisión**: Almacenar jobs en un dict en memoria, no en MongoDB.

**Justificación**:
- Bedrock está stubbed — no hay jobs reales ejecutándose
- Cada instancia del servicio tiene su propio estado
- Cuando la integración con Bedrock sea real, se reemplaza por MongoDB (matching api-router pattern)
- Aceptable para MVP y demos

### 1.4 POST /train returns 202 Accepted

**Decisión**: Retornar 202 en lugar de 200 para el endpoint de training.

**Justificación**:
- Pattern consistente con el upload del api-router (que también retorna 202)
- El training es asíncrono — puede durar horas
- El cliente debe hacer polling via GET /status/:job_id
- HTTP 202 indica "aceptado pero no completado"

## 2. Patrones de Diseño Aplicados

### Command Pattern (Training Job)

```python
# Cada job encapsula una operación de training
@dataclass
class TrainingJob:
    job_id: str
    status: str  # submitted, in_progress, completed, failed, cancelled
    user_id: str
    triples_count: int
    config: dict
```

### Repository Pattern (Job Store)

```python
# El pipeline actúa como repositorio para jobs
def submit_training_job(user_id, triples_path, config) -> str:
    # Crea job y almacena
def get_job_status(job_id) -> TrainingJob | None:
    # Consulta job
def cancel_job(job_id) -> TrainingJob | None:
    # Cancela job
```

### Pipeline Pattern (ETL → Training)

```python
# Flujo secuencial: Triples → Conversión → Submit → Status
convert_triples_to_training_format(triples_path)  # Paso 1
submit_training_job(user_id, triples_path, config)  # Paso 2
get_job_status(job_id)  # Paso 3 (polling)
```

## 3. Ejemplos de Logs

### 3.1 POST /train (éxito)

```
2026-08-31T10:00:00 [abc-123] INFO finetune-service: POST /train — dataset: data/triples/user-123/receta.jsonl, user_id: user-123
2026-08-31T10:00:01 [abc-123] INFO finetune-service: Job submitted: ft-job-a1b2c3d4
```

### 3.2 POST /train (dataset no encontrado)

```
2026-08-31T10:00:00 [def-456] INFO finetune-service: POST /train — dataset: /fake/path.jsonl, user_id: user-456
2026-08-31T10:00:00 [def-456] ERROR finetune-service: Dataset not found: /fake/path.jsonl
```

### 3.3 POST /train (dataset inválido)

```
2026-08-31T10:00:00 [ghi-789] INFO finetune-service: POST /train — dataset: empty.jsonl, user_id: user-789
2026-08-31T10:00:00 [ghi-789] ERROR finetune-service: Invalid dataset: No valid triples found
```

### 3.4 GET /status (éxito)

```
2026-08-31T10:00:00 [jkl-012] INFO finetune-service: GET /status/ft-job-a1b2c3d4
2026-08-31T10:00:00 [jkl-012] INFO finetune-service: Job status: submitted
```

### 3.5 GET /status (job no encontrado)

```
2026-08-31T10:00:00 [mno-345] INFO finetune-service: GET /status/nonexistent
2026-08-31T10:00:00 [mno-345] WARNING finetune-service: Job not found: nonexistent
```

### 3.6 GET /health

```
2026-08-31T10:00:00 [pqr-678] INFO finetune-service: GET /health
```

## 4. Principios SOLID Aplicados

| Principio | Aplicación |
|-----------|-----------|
| **S** (Single Responsibility) | El servicio solo hace una cosa: manejar jobs de fine-tuning |
| **O** (Open/Closed) | Nuevo tipo de training (ej: full fine-tuning) se agrega sin modificar endpoints |
| **L** (Liskov Substitution) | El pipeline puede cambiar de implementación (Bedrock → otro provider) sin cambiar la interfaz |
| **I** (Interface Segregation) | Endpoints expuestos: solo /train, /status, /health — no hay métodos innecesarios |
| **D** (Dependency Inversion) | El servicio depende de abstractions (pipeline functions), no de implementaciones concretas |
