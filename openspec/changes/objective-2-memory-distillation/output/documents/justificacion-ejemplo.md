# Justificación — Memory Distillation (Frame 2)

Explicación de los componentes clave del módulo ETL.

## El problema que resuelve

El usuario sube documentos (texto, PDFs de recetas médicas, facturas, fotos, videos) y el sistema debe **entender** qué hay ahí dentro para que el LLM pueda razonar sobre eso. No puedes pasar un binario entero a un vector store — primero **cargas** el contenido con un loader de LangChain y luego dejas que el **LLM razone** y lo convierta en datos estructurados (triples).

---

## 📋 base.py — Selección de loaders LangChain

```python
# Loaders out-of-the-box de langchain_community.document_loaders
LOADERS = {
    "application/pdf": PyPDFLoader,          # o PDFPlumberLoader
    "text/plain":      TextLoader,
    "text/html":       UnstructuredHTMLLoader,
    "message/rfc822":  UnstructuredEmailLoader,
    "image/*":         UnstructuredImageLoader,  # OCR out-of-the-box
    "video/*":         <video loader>,
}

def select(file_path: str): ...   # elige el loader por MIME type
def load(file_path: str): ...     # devuelve el contenido cargado
```

**Regla clave**: **todos los parsers usan loaders de LangChain out-of-the-box** (`langchain_community.document_loaders`). **No** se escriben parsers a mano salvo que ningún loader cubra el formato. El OCR lo hacen los loaders `Unstructured*`, **no** un pipeline propio de Tesseract.

**¿Por qué?** Porque así puedes agregar un tipo de archivo nuevo (ej: DOCX) registrando otro loader — sin tocar el resto del código. Es el **Open/Closed Principle** — abierto para extensión, cerrado para modificación.

---

## 🔄 pipeline.py — El orquestador (distill())

```
Usuario sube archivo
        │
        ▼
   distill(file_path)
        │
        ├─ MIME application/pdf   → PyPDFLoader.load()
        ├─ MIME text/plain        → TextLoader.load()
        ├─ MIME text/html         → UnstructuredHTMLLoader.load()
        ├─ MIME message/rfc822    → UnstructuredEmailLoader.load()
        ├─ MIME image/*           → UnstructuredImageLoader.load()  (OCR)
        └─ MIME video/*           → video loader .load()
        │
        ▼
   Contenido cargado (texto / multimodal)
        │
        ▼
   POST LLM Service (8003, Qwen3.5-4B base) → el modelo RAZONA → emite triples JSON
        │
        ▼
   Escribe archivo JSONL
```

El orquestador **no sabe** cómo cargar cada tipo — solo **selecciona** el loader de LangChain correcto y luego delega el razonamiento al **LLM Service**. Es un switch case inteligente sobre loaders + una llamada al LLM.

---

## 📊 triples.py — Los triples (sujeto-predicado-objeto)

Un **triple** es la unidad mínima de conocimiento:

```json
{"subject": "Paciente", "predicate": "tiene", "object": "diabetes", "metadata": {...}}
```

Es como una oración simplificada:
- **Sujeto**: ¿De quién hablamos? → "Paciente"
- **Predicado**: ¿Qué relación tiene? → "tiene"
- **Objeto**: ¿Qué cosa? → "diabetes"

**¿Quién los crea?** El **LLM (Qwen3.5-4B base)**: recibe el contenido cargado, **razona** sobre él y **recién entonces emite los triples en JSON** (proceso LLM-first, no reglas/regex). Si tienes 100 triples de un paciente, el LLM puede decir "Este paciente tiene diabetes, toma metformina, y su presión es alta".

> **Dependencia entre frames:** ETL (Frame 2) llama al **LLM Service (Frame 4)** con el modelo **base** Qwen3.5-4B (no requiere fine-tuning). El fine-tuning sí depende de los triples que ETL acumula, pero ETL solo necesita inferencia base.

---

## 📁 JSONL — ¿Qué es?

**JSON Lines** = un JSON por línea:

```
{"subject": "Paciente", "predicate": "tiene", "object": "diabetes", "metadata": {"source": "receta.pdf", "page": 1}}
{"subject": "Paciente", "predicate": "toma", "object": "metformina", "metadata": {"source": "receta.pdf", "page": 1}}
{"subject": "Paciente", "predicate": "tiene", "object": "presión alta", "metadata": {"source": "receta.pdf", "page": 2}}
```

**¿Por qué no un JSON normal?**
- **Append-only**: Puedes agregar triples sin reescribir el archivo
- **Streaming**: Se puede leer línea por línea (no carga todo en memoria)
- **Debugging**: Cada línea es un triple — fácil de leer
- **Frame 3**: Chroma puede ingerir línea por línea para crear embeddings

**¿Por qué un archivo por usuario?**
- Aislamiento: `data/triples/{user_id}/{doc_id}.jsonl`
- Un usuario nunca ve los triples de otro
- Cumple con el requisito de multi-tenancy del Frame 1

---

## 📡 upload.py — El router FastAPI (API Router, puerto 8000)

El upload **no** vive en el ETL Service (el diseño lo prohíbe: ETL no expone HTTP de
carga). El API Router es la fachada:

```python
@router.post("/api/upload")  # 202 Accepted
async def upload_file(
    file: UploadFile,
    user: dict = Depends(require_premium),  # JWT, Premium only
):
    # 1. Validar tipo MIME (python-magic sobre bytes, no extensión)
    # 2. Validar tamaño (max 10MB) → 413
    # 3. Guardar binario en MongoDB GridFS
    # 4. Publicar Kafka file.uploaded {correlation_id, file_id, user_id}
    # 5. Retornar 202 {correlation_id} — el cliente hace polling GET /tasks/:id
```

`triples_count` llega cuando el ETL publica `task.response` y el Router actualiza `task_status`.

---

## 🔄 Flujo completo

```
1. Usuario sube "receta.pdf" vía POST /api/upload
2. JWT validado (¿está autenticado?)
3. python-magic detecta: application/pdf
4. distill("receta.pdf") se ejecuta
5. Se selecciona el loader LangChain: PyPDFLoader
6. PyPDFLoader.load() carga el contenido del PDF (OCR vía Unstructured si es escaneado)
7. El contenido se envía al LLM Service (8003, Qwen3.5-4B base)
8. El LLM razona y emite triples JSON: "Paciente tiene diabetes" → triple
9. Metadata enrichment: agrega source_file, page, timestamp
10. Escribe: data/triples/{user_id}/receta_123.jsonl
11. El binario original ya vive en MongoDB GridFS (local); se guarda metadata del documento en MongoDB
12. API Router responde HTTP 202 {correlation_id}; el cliente consulta GET /tasks/:id
    y recibe triples_count cuando Kafka task.response llega (success)
```

---

## 📐 Arquitectura resumida

```
┌───────────────────────────────────────────────────────────────┐
│                    ETL SERVICE (8001)                         │
│                                                               │
│  Kafka file.uploaded ──→ distill() ──→ LangChain Loaders      │
│       │                      │              │                 │
│       │                      │      ┌───────┼───────┐         │
│       │                      │      │   │   │   │   │         │
│       │                      │    PDF Text HTML EML Img/Vid   │
│       │                      │      └───────┼───────┘         │
│       │                      │              │                 │
│       │                      │      contenido cargado         │
│       │                      │              │                 │
│       │                      │   ──→ LLM Service (8003)       │
│       │                      │        Qwen3.5-4B base RAZONA  │
│       │                      │              │                 │
│       │                      │      Triples JSON (LLM-first)  │
│       │                      │              │                 │
│       ▼                      ▼              ▼                 │
│  MongoDB GridFS (local)   data/triples/{user_id}/             │
│  (binario original)       {doc_id}.jsonl                      │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Patrones de Diseño y Principios SOLID

### Patrones aplicados

#### Strategy (Estrategia)

Cada loader de LangChain es una **estrategia** diferente para cargar contenido:

```
LangChain loaders (langchain_community.document_loaders)
    ├── PyPDFLoader / PDFPlumberLoader → Estrategia para PDFs
    ├── TextLoader                     → Estrategia para texto
    ├── UnstructuredHTMLLoader         → Estrategia para HTML
    ├── UnstructuredEmailLoader        → Estrategia para emails
    ├── UnstructuredImageLoader        → Estrategia para imágenes (OCR)
    └── video loader                   → Estrategia para video
```

`distill()` **selecciona** la estrategia correcta en runtime por MIME type. Si mañana agregas un tipo (ej: DOCX), solo registras otro loader — `distill()` no cambia.

#### Factory Method (Método Factory)

`distill()` actúa como un **factory**: dado un archivo, selecciona el loader de LangChain correcto por MIME type:

```python
def distill(file_path: str) -> list[Triple]:
    loader = select_loader(file_path)        # elige loader LangChain por MIME
    content = loader(file_path).load()       # carga el contenido
    return llm_client.extract_triples(content)  # el LLM razona y emite triples
```

No instancia `PyPDFLoader()` directamente en todos lados — pregunta "¿qué loader va con este MIME?" y usa el que corresponda.

#### Adapter (Adaptador)

El **cliente del LLM Service** (`llm_client`) envuelve la API HTTP del LLM Service (8003) detrás de un método simple `extract_triples(content)`. El resto del ETL no sabe de HTTP ni de prompts — solo pide triples y el adapter se encarga de hablar con Qwen3.5-4B (modelo base).

#### Facade (Fachada)

`upload.py` es una **fachada**: esconde toda la complejidad del ETL detrás de un solo endpoint:

```
Usuario solo ve:    POST /api/upload
Lo que pasa adentro: validación → MIME detection → loader LangChain → load → LLM razona → triples → storage
```

El usuario no necesita saber qué es un loader, un triple, o JSONL. Solo sube un archivo.

---

### Principios SOLID

#### S — Single Responsibility (Responsabilidad Única)

Cada módulo hace **UNA sola cosa**:

| Módulo | Responsabilidad |
|--------|-----------------|
| `upload.py` (API Router) | Solo maneja HTTP (recibe archivo, retorna respuesta) |
| `pipeline.py` | Solo selecciona el loader LangChain y orquesta la extracción |
| `base.py` | Solo mapea MIME → loader LangChain y carga contenido |
| `llm_client.py` | Solo habla con el LLM Service para extraer triples |

Si un loader falla, solo tocas el mapeo del loader. No tocas el upload, ni el orquestador, ni el cliente del LLM.

#### O — Open/Closed (Abierto para extensión, cerrado para modificación)

Para agregar un tipo nuevo (ej: Word .docx):

```
1. Registras el loader de LangChain (ej: UnstructuredWordDocumentLoader)
2. Agregas: una línea en el mapeo MIME → loader
```

**NO** modificas los loaders existentes ni el `llm_client`. El código existente no cambia — solo agregas.

#### L — Liskov Substitution (Sustitución de Liskov)

Cualquier loader de LangChain puede reemplazar a otro detrás de la capa de selección sin romper el sistema:

```python
# Esto funciona con CUALQUIER loader LangChain
def load_content(loader_cls, file: str):
    return loader_cls(file).load()
```

No importa si es `PyPDFLoader`, `UnstructuredImageLoader`, o uno futuro — todos exponen `.load()`.

#### I — Interface Segregation (Segregación de Interfaz)

La capa de selección expone una interfaz mínima (`select` + `load`), y el cliente del LLM expone solo `extract_triples(content)`. Nadie está forzado a depender de métodos que no usa.

#### D — Dependency Inversion (Inversión de Dependencia)

`distill()` depende de **abstracciones** (la capa de loaders y el cliente del LLM), no de clases concretas:

```python
# distill() NO acopla a un loader concreto en todo el flujo:
from langchain_community.document_loaders import PyPDFLoader  # ❌ acoplamiento directo

# distill() SÍ hace esto:
def distill(select_loader, llm_client, file: str):  # ✅ depende de abstracciones
    content = select_loader(file)(file).load()
    return llm_client.extract_triples(content)
```

Esto permite cambiar loaders o el backend del LLM sin tocar el orquestador.

---

## 📋 Logging Estructurado — ETL Service

### Formato de log

```
{timestamp} [{correlation_id}] {level} {service}: {message}
```

### CorrelationFilter

```python
class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = getattr(record, "correlation_id", "no-id")
        return True
```

### Helper log_with_correlation

```python
def log_with_correlation(correlation_id: str, level: str, message: str):
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)
```

---

## 📨 Logs por Kafka Consumer

### Consumer: file.uploaded

```
2026-08-31T10:00:01 [abc-123] INFO etl-service: Consumed from Kafka: file.uploaded
2026-08-31T10:00:01 [abc-123] INFO etl-service: Processing file: receta.pdf (user_id=user1)
```

### Consumer: procesamiento exitoso

```
2026-08-31T10:00:01 [abc-123] INFO etl-service: Fetching file from MongoDB GridFS (local)
2026-08-31T10:00:01 [abc-123] INFO etl-service: File fetched successfully
2026-08-31T10:00:02 [abc-123] INFO etl-service: Starting ETL pipeline
2026-08-31T10:00:02 [abc-123] INFO etl-service: LangChain loader selected: PyPDFLoader (mime=application/pdf)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Loaded content from page 1 (1250 chars)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Loaded content from page 2 (980 chars)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Calling LLM Service (8003, Qwen3.5-4B base) for triple extraction
2026-08-31T10:00:03 [abc-123] INFO etl-service: LLM returned 15 triples
2026-08-31T10:00:03 [abc-123] INFO etl-service: Saved 15 triples to data/triples/user1/abc-123.jsonl
2026-08-31T10:00:03 [abc-123] INFO etl-service: Published to Kafka: task.response (success)
```

### Consumer: procesamiento con error

```
2026-08-31T10:00:01 [abc-789] INFO etl-service: Consumed from Kafka: file.uploaded
2026-08-31T10:00:01 [abc-789] INFO etl-service: Processing file: scanned.pdf (user_id=user2)
2026-08-31T10:00:01 [abc-789] INFO etl-service: Fetching file from MongoDB GridFS
2026-08-31T10:00:02 [abc-789] INFO etl-service: Starting ETL pipeline
2026-08-31T10:00:02 [abc-789] INFO etl-service: LangChain loader selected: UnstructuredPDFLoader (scanned PDF, OCR out-of-the-box)
2026-08-31T10:00:05 [abc-789] INFO etl-service: Loader extracted 850 chars via Unstructured OCR
2026-08-31T10:00:05 [abc-789] INFO etl-service: Calling LLM Service (8003, Qwen3.5-4B base) for triple extraction
2026-08-31T10:00:05 [abc-789] INFO etl-service: LLM returned 8 triples
2026-08-31T10:00:05 [abc-789] INFO etl-service: Published to Kafka: task.response (success)
```

### Consumer: error fatal

```
2026-08-31T10:00:01 [abc-456] INFO etl-service: Consumed from Kafka: file.uploaded
2026-08-31T10:00:01 [abc-456] INFO etl-service: Processing file: corrupt.pdf (user_id=user3)
2026-08-31T10:00:01 [abc-456] INFO etl-service: Fetching file from MongoDB GridFS
2026-08-31T10:00:02 [abc-456] ERROR etl-service: Processing failed: PDF is corrupted
2026-08-31T10:00:02 [abc-456] ERROR etl-service: Published error response (http_code=500)
```

---

## 📨 Logs por Kafka Producer

### Producer: task.response (success)

```
2026-08-31T10:00:03 [abc-123] INFO etl-service: Publishing to Kafka: task.response
2026-08-31T10:00:03 [abc-123] DEBUG etl-service: Message: {correlation_id: abc-123, status: success, triples_count: 15}
```

### Producer: task.response (error)

```
2026-08-31T10:00:02 [abc-456] ERROR etl-service: Publishing to Kafka: task.response (error)
2026-08-31T10:00:02 [abc-456] DEBUG etl-service: Message: {correlation_id: abc-456, status: error, http_code: 500, error_message: PDF is corrupted}
```

---

## 🔍 Logs por LangChain Loader

### PyPDFLoader

```
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: PyPDFLoader.load(): receta.pdf
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: Page 1: 1250 chars loaded
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: Page 2: 980 chars loaded
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: Total: 2230 chars from 2 pages
```

### UnstructuredHTMLLoader

```
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: UnstructuredHTMLLoader.load(): page.html
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: Loaded 1800 chars of text content
```

### UnstructuredEmailLoader

```
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: UnstructuredEmailLoader.load(): email.eml
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: Headers + body loaded: 950 chars
```

### UnstructuredImageLoader (OCR out-of-the-box)

```
2026-08-31T10:00:02 [abc-123] DEBUG etl-loader: UnstructuredImageLoader.load(): foto.png
2026-08-31T10:00:04 [abc-123] DEBUG etl-loader: Loaded 850 chars via Unstructured OCR
```

---

## 🔗 Logs por Triple Extraction (LLM Service, Qwen3.5-4B base)

```
2026-08-31T10:00:03 [abc-123] DEBUG etl-llm-client: POST LLM Service (8003) /extract — model=Qwen3.5-4B (base)
2026-08-31T10:00:03 [abc-123] DEBUG etl-llm-client: Sent 2230 chars of loaded content for reasoning
2026-08-31T10:00:03 [abc-123] INFO  llm-service: Reasoning over content and extracting triples
2026-08-31T10:00:03 [abc-123] DEBUG etl-llm-client: LLM responded with JSON array (15 triples)
2026-08-31T10:00:03 [abc-123] DEBUG etl-llm-client: Total: 15 triples extracted (LLM-first)
```

---

## 📁 Logs por Pipeline (distill)

```
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: File: receta.pdf (2.5 MB)
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: MIME type: application/pdf
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: Selecting LangChain loader: PyPDFLoader
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: Content loaded: 2230 chars
2026-08-31T10:00:03 [abc-123] DEBUG pipeline: LLM Service returned: 15 triples
2026-08-31T10:00:03 [abc-123] DEBUG pipeline: Output: data/triples/user1/abc-123.jsonl
```

---

## 📊 Flujo Completo con Logs

### Upload exitoso (PDF simple)

```
T+0.000s  [abc-123] INFO  api-gateway: POST /api/upload
T+0.001s  [abc-123] INFO  api-gateway: JWT validated: user_id=user1, tier=premium
T+0.002s  [abc-123] INFO  api-gateway: File saved to GridFS: receta.pdf
T+0.003s  [abc-123] INFO  api-gateway: Published to Kafka: file.uploaded
T+0.004s  [abc-123] INFO  api-gateway: Response: 202 Accepted
T+1.000s  [abc-123] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.001s  [abc-123] INFO  etl-service: Fetching file from GridFS (local)
T+1.500s  [abc-123] DEBUG pipeline: Selecting LangChain loader: PyPDFLoader
T+2.000s  [abc-123] DEBUG etl-loader: Page 1: 1250 chars
T+2.500s  [abc-123] DEBUG etl-loader: Page 2: 980 chars
T+3.000s  [abc-123] DEBUG etl-llm-client: LLM Service (Qwen3.5-4B base) returned 15 triples
T+3.001s  [abc-123] INFO  etl-service: Published to Kafka: task.response (success)
T+3.500s  [abc-123] INFO  api-gateway: Task completed successfully
```

### Upload con OCR fallback

```
T+0.000s  [abc-456] INFO  api-gateway: POST /api/upload
T+0.003s  [abc-456] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-456] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.500s  [abc-456] DEBUG pipeline: Selecting LangChain loader: UnstructuredPDFLoader (scanned)
T+4.000s  [abc-456] DEBUG etl-loader: Loaded 850 chars via Unstructured OCR
T+4.200s  [abc-456] DEBUG etl-llm-client: LLM Service (Qwen3.5-4B base) returned 8 triples
T+4.501s  [abc-456] INFO  etl-service: Published to Kafka: task.response (success)
```

### Upload con error

```
T+0.000s  [abc-789] INFO  api-gateway: POST /api/upload
T+0.003s  [abc-789] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-789] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.500s  [abc-789] DEBUG pipeline: Selecting LangChain loader: PyPDFLoader
T+2.000s  [abc-789] ERROR etl-service: Processing failed: PDF is corrupted (loader error)
T+2.001s  [abc-789] ERROR etl-service: Published error response (http_code=500)
T+2.500s  [abc-789] WARNING api-gateway: Retrying (1/3)
```
