# Justificación — Hybrid Store + RAG (Frame 3)

Explicación de los componentes clave del módulo RAG.

## El problema que resuelve

El usuario tiene documentos procesados por el ETL (Frame 2) como triples JSONL.
Pero para que el LLM pueda **responder preguntas** sobre esos documentos, necesita
**buscar** los triples más relevantes y **eticalarlos** como contexto en el prompt.

RAG (Retrieval-Augmented Generation) resuelve esto: busca información relevante
en los documentos del usuario y la inyecta en la consulta al LLM.

---

## 🗄️ document_store.py — Almacén de documentos

```python
class DocumentStore:
    def insert_document(self, doc: dict, user_id: str) -> str: ...
    def get_document(self, doc_id: str, user_id: str) -> dict: ...
    def list_documents(self, user_id: str) -> list[dict]: ...
```

Es la capa de acceso a MongoDB. Cada operación filtra por `user_id` — un usuario
nunca ve los documentos de otro.

**¿Por qué MongoDB?**
- Schema flexible: cada documento puede tener campos diferentes
- Free tier (M0) suficiente para MVP
- Motor async (motor) para no bloquear el event loop de FastAPI

---

## 🔍 vector_store.py — Almacén de vectores

```python
class VectorStore(Protocol):
    def add(self, vectors: list, metadata: list) -> None: ...
    def search(self, query_vector: list, k: int) -> list: ...
    def delete(self, filter: dict) -> None: ...
```

Dos implementaciones:
- **ChromaVectorStore**: para desarrollo local (corre en Docker, zero-config)
- **PineconeVectorStore**: para producción (managed, escala)

El `VectorStore` protocol es como el `DocumentParser` de Frame 2 — una abstracción
que permite cambiar la implementación sin tocar el resto del código.

---

## 🧮 Embedding Pipeline

```
Triple JSONL
    │
    ▼
Chunking (1000 chars, 200 overlap)
    │
    ▼
sentence-transformers (384 dimensions)
    │
    ▼
Fernet encryption
    │
    ▼
Store in Chroma/Pinecone
```

### ¿Qué es un embedding?

Un **embedding** es un vector numérico que representa el significado semántico del texto:

```
"Paciente tiene diabetes" → [0.12, -0.45, 0.78, ..., 0.33]  (384 números)
```

Dos textos con significado similar tendrán vectores cercanos en el espacio vectorial.
Esto permite buscar por **significado**, no solo por palabras exactas.

### ¿Qué es chunking?

Los LLMs tienen límite de contexto. No puedes enviar un documento entero.
**Chunking** divide el documento en trozos pequeños:

```
Documento de 5000 caracteres
    │
    ▼
Chunk 1: caracteres 0-1000
Chunk 2: caracteres 800-1800 (overlap de 200)
Chunk 3: caracteres 1600-2600
Chunk 4: caracteres 2400-3400
Chunk 5: caracteres 3200-4200
Chunk 6: caracteres 4000-5000
```

El **overlap** de 200 caracteres asegura que no se pierda contexto entre chunks.

---

## 🤖 rag_service.py — Servicio RAG

```python
class RAGService:
    def semantic_search(self, query: str, user_id: str, k: int = 3) -> list: ...
    def context_injection(self, query: str, user_id: str) -> str: ...
```

### ¿Cómo funciona la búsqueda semántica?

```
1. Usuario pregunta: "¿Qué medicamentos tomo?"
2. Embed query: "¿Qué medicamentos tomo?" → vector
3. Buscar en Chroma: Top-k=3 vectores más similares
4. Resultados: [
     {"text": "Paciente toma metformina", "score": 0.92},
     {"text": "Paciente toma losartán", "score": 0.87},
     {"text": "Paciente tiene diabetes", "score": 0.81}
   ]
5. Inyectar en prompt del LLM
```

### ¿Qué es context injection?

Es agregar los resultados de la búsqueda al prompt del LLM:

```
Sin RAG:
  User: "¿Qué medicamentos tomo?"
  LLM: "No tengo esa información."

Con RAG:
  Context: "Paciente toma metformina. Paciente toma losartán."
  User: "¿Qué medicamentos tomo?"
  LLM: "Según tus registros, tomas metformina y losartán."
```

---

## 🔐 Fernet Encryption

Los vectores se **encriptan** antes de guardarse:

```
Vector original: [0.12, -0.45, 0.78, ...]
        │
        ▼  Fernet.encrypt()
Vector encriptado: "gAAAAABh..." (texto cifrado)
        │
        ▼  Store in Chroma
```

Al recuperar:
```
Vector encriptado: "gAAAAABh..."
        │
        ▼  Fernet.decrypt()
Vector original: [0.12, -0.45, 0.78, ...]
```

**¿Por qué?** Porque los embeddings contienen información sensible del usuario.
Si alguien accede a la base de datos, no puede leer los vectores sin la clave Fernet.

---

## 🔄 Flujo completo

### Ingestión (después de upload)

```
1. Usuario sube "receta.pdf"
2. Frame 2: ETL extrae triples → JSONL
3. Frame 3: Lee JSONL
4. Frame 3: Chunking del texto
5. Frame 3: Genera embeddings (sentence-transformers)
6. Frame 3: Encripta con Fernet
7. Frame 3: Guarda en Chroma/Pinecone
8. Frame 3: Guarda metadata en MongoDB
```

### Retrieval (cuando usuario pregunta)

```
1. Usuario pregunta: "¿Cuál es mi diagnóstico?"
2. Embed la pregunta
3. Busca Top-k=3 en Chroma
4. Desencripta resultados
5. Inyecta contexto en prompt del LLM
6. LLM responde con información del usuario
```

---

## 🏗️ Patrones de Diseño y Principios SOLID

### Patrones aplicados

#### Strategy (Estrategia)

Cada vector store es una **estrategia** diferente:

```
VectorStore (Protocol)
    ├── ChromaVectorStore    → Estrategia para desarrollo
    └── PineconeVectorStore  → Estrategia para producción
```

`create_vector_store()` **selecciona** la estrategia correcta según la config.

#### Factory Method (Método Factory)

```python
def create_vector_store(provider: str) -> VectorStore:
    if provider == "chroma":
        return ChromaVectorStore()
    elif provider == "pinecone":
        return PineconeVectorStore()
```

#### Adapter (Adaptador)

Los wrappers de Chroma y Pinecone **adaptan** APIs diferentes a una interfaz común:

```
Chroma API     → ChromaVectorStore     → VectorStore (Protocol)
Pinecone API   → PineconeVectorStore   → VectorStore (Protocol)
```

#### Facade (Fachada)

`rag_service.py` esconde toda la complejidad detrás de `semantic_search()`:

```
Usuario solo ve:    rag_service.semantic_search(query)
Lo que pasa adentro: embed → search → decrypt → rank → return
```

#### Repository (Repositorio)

`document_store.py` encapsula el acceso a MongoDB:

```
rag_service no sabe nada de MongoDB
Solo llama: document_store.list_documents(user_id)
```

---

### Principios SOLID

| Principio | Aplicación |
|-----------|------------|
| **S** | Cada módulo hace UNA cosa: `document_store` solo MongoDB, `vector_store` solo embeddings, `rag_service` solo orquesta |
| **O** | Agregar Weaviate = crear clase nueva, cero cambios en RAG service |
| **L** | Cualquier `VectorStore` reemplaza a otra sin romper `rag_service` |
| **I** | `VectorStore` protocol tiene solo 3 métodos: `add`, `search`, `delete` |
| **D** | `rag_service` depende de `VectorStore` (abstracción), no de Chroma/Pinecone (concreto) |

---

## 📋 Logging Estructurado — RAG Service

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

## 📡 Logs por Endpoint

### GET /health

```
2026-08-31T10:00:00 [no-id] INFO rag-service: GET /health
```

### GET /search

```
2026-08-31T10:00:00 [def-456] INFO rag-service: GET /search
2026-08-31T10:00:00 [def-456] INFO rag-service: Semantic search: query='diabetes treatment' user=user1
2026-08-31T10:00:01 [def-456] INFO rag-service: Search returned 3 results
```

### GET /context

```
2026-08-31T10:00:00 [def-456] INFO rag-service: GET /context
2026-08-31T10:00:00 [def-456] INFO rag-service: Context injection: query='diabetes treatment' user=user1
2026-08-31T10:00:01 [def-456] INFO rag-service: Context returned: 3 sources
```

### POST /ingest

```
2026-08-31T10:00:00 [abc-123] INFO rag-service: POST /ingest
2026-08-31T10:00:00 [abc-123] INFO rag-service: Ingesting triples: user=user1 doc=doc1
2026-08-31T10:00:02 [abc-123] INFO rag-service: Ingested 15 triples
```

### DELETE /embeddings/:doc_id

```
2026-08-31T10:00:00 [abc-123] INFO rag-service: DELETE /embeddings/doc1
2026-08-31T10:00:00 [abc-123] INFO rag-service: Deleting embeddings: doc=doc1 user=user1
2026-08-31T10:00:01 [abc-123] INFO rag-service: Deleted embeddings for doc doc1
```

### Errores

```
2026-08-31T10:00:00 [def-456] ERROR rag-service: Search failed: Connection timeout
2026-08-31T10:00:00 [def-456] ERROR rag-service: Context injection failed: Vector store unavailable
```

---

## 🔍 Logs por Semantic Search

### Búsqueda exitosa

```
2026-08-31T10:00:00 [def-456] DEBUG rag-service: Embedding query: 'diabetes treatment'
2026-08-31T10:00:00 [def-456] DEBUG rag-service: Query embedding: [0.12, -0.45, 0.78, ...] (384 dims)
2026-08-31T10:00:00 [def-456] DEBUG rag-service: Searching Chroma with k=3, user_id=user1
2026-08-31T10:00:01 [def-456] DEBUG rag-service: Found 3 results (scores: 0.92, 0.87, 0.81)
2026-08-31T10:00:01 [def-456] DEBUG rag-service: Decrypting results with Fernet
2026-08-31T10:00:01 [def-456] DEBUG rag-service: Results decrypted successfully
```

### Búsqueda sin resultados

```
2026-08-31T10:00:00 [def-456] DEBUG rag-service: Embedding query: 'quantum physics'
2026-08-31T10:00:00 [def-456] DEBUG rag-service: Searching Chroma with k=3, user_id=user1
2026-08-31T10:00:01 [def-456] DEBUG rag-service: Found 0 results
2026-08-31T10:00:01 [def-456] INFO rag-service: No relevant context found
```

---

## 🧮 Logs por Embedding Pipeline

### Embedding generation

```
2026-08-31T10:00:00 [abc-123] DEBUG rag-service: Loading embedding model: sentence-transformers/all-MiniLM-L6-v2
2026-08-31T10:00:01 [abc-123] DEBUG rag-service: Embedding model loaded (384 dims)
2026-08-31T10:00:01 [abc-123] DEBUG rag-service: Embedding 15 text chunks
2026-08-31T10:00:02 [abc-123] DEBUG rag-service: Embeddings generated: 15 vectors (384 dims each)
```

### Chunking

```
2026-08-31T10:00:00 [abc-123] DEBUG rag-service: Chunking text: 2230 chars
2026-08-31T10:00:00 [abc-123] DEBUG rag-service: Chunk size: 1000, overlap: 200
2026-08-31T10:00:00 [abc-123] DEBUG rag-service: Created 3 chunks
```

---

## 🗄️ Logs por Document Store

### Insert document

```
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Inserting document: user=user1, type=pdf
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Document inserted: doc_id=ObjectId(...)
```

### List documents

```
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Listing documents: user=user1
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Found 5 documents
```

### Get document

```
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Getting document: doc_id=doc1, user=user1
2026-08-31T10:00:00 [abc-123] DEBUG document-store: Document found
```

---

## 🔍 Logs por Vector Store

### Add vectors

```
2026-08-31T10:00:01 [abc-123] DEBUG vector-store: Adding 15 vectors to Chroma
2026-08-31T10:00:01 [abc-123] DEBUG vector-store: Vectors encrypted with Fernet
2026-08-31T10:00:02 [abc-123] DEBUG vector-store: 15 vectors stored successfully
```

### Search vectors

```
2026-08-31T10:00:00 [def-456] DEBUG vector-store: Searching Chroma: k=3, user_id=user1
2026-08-31T10:00:01 [def-456] DEBUG vector-store: Found 3 results
2026-08-31T10:00:01 [def-456] DEBUG vector-store: Decrypting results
```

### Delete vectors

```
2026-08-31T10:00:00 [abc-123] DEBUG vector-store: Deleting 15 vectors for doc=doc1
2026-08-31T10:00:01 [abc-123] DEBUG vector-store: 15 vectors deleted
```

---

## 📊 Flujo Completo con Logs

### Ingesta de triples

```
T+0.000s  [abc-123] INFO  api-gateway: POST /api/upload
T+0.003s  [abc-123] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-123] INFO  etl-service: Consumed from Kafka: file.uploaded
T+3.000s  [abc-123] INFO  etl-service: Published to Kafka: task.response (success)
T+3.500s  [abc-123] INFO  api-gateway: Task completed successfully
T+4.000s  [abc-123] INFO  rag-service: POST /ingest
T+4.001s  [abc-123] DEBUG rag-service: Loading embedding model
T+4.500s  [abc-123] DEBUG rag-service: Embedding 15 text chunks
T+5.000s  [abc-123] DEBUG vector-store: Adding 15 vectors to Chroma
T+5.500s  [abc-123] DEBUG vector-store: 15 vectors stored successfully
T+5.501s  [abc-123] INFO  rag-service: Ingested 15 triples
```

### Búsqueda semántica

```
T+0.000s  [def-456] INFO  api-gateway: POST /api/chat
T+0.001s  [def-456] INFO  api-gateway: Calling RAG Service for context
T+0.500s  [def-456] INFO  rag-service: GET /context
T+0.501s  [def-456] DEBUG rag-service: Embedding query: 'diabetes treatment'
T+1.000s  [def-456] DEBUG rag-service: Searching Chroma with k=3
T+1.500s  [def-456] DEBUG rag-service: Found 3 results (scores: 0.92, 0.87, 0.81)
T+1.501s  [def-456] INFO  rag-service: Context returned: 3 sources
T+2.000s  [def-456] INFO  api-gateway: Calling LLM Service for response
T+3.500s  [def-456] INFO  api-gateway: LLM response received
T+3.501s  [def-456] INFO  api-gateway: Response: 200 OK
```
