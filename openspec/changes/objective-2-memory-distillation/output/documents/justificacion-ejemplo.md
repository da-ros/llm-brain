# Justificación — Memory Distillation (Frame 2)

Explicación de los componentes clave del módulo ETL.

## El problema que resuelve

El usuario sube documentos (PDFs de recetas médicas, facturas, fotos) y el sistema debe **entender** qué hay ahí dentro para que el LLM pueda razonar sobre eso. No puedes pasar un PDF entero a un LLM — necesitas convertirlo en datos estructurados.

---

## 📋 base.py — El contrato (Protocol)

```python
class DocumentParser(Protocol):
    def supports(self, file_path: str) -> bool: ...
    def parse(self, file_path: str) -> list[Triple]: ...
```

Esto es como una **interfaz** en Python. Dice: "Cualquier parser que quieras crear, DEBE tener estos dos métodos".

- `supports()` → ¿Puedo manejar este archivo? (devuelve True/False)
- `parse()` → Extráeme el contenido y dame triples

**¿Por qué?** Porque así puedes agregar un parser nuevo (ej: parser de Word) sin tocar el resto del código. Solo creas una clase que implemente estos dos métodos. Es el **Open/Closed Principle** — abierto para extensión, cerrado para modificación.

---

## 🔄 pipeline.py — El orquestador (distill())

```
Usuario sube archivo
        │
        ▼
   distill(file_path)
        │
        ├─ pdf_parser.supports("doc.pdf")? → SÍ → pdf_parser.parse()
        ├─ html_parser.supports("page.html")? → SÍ → html_parser.parse()
        ├─ eml_parser.supports("email.eml")? → SÍ → eml_parser.parse()
        └─ ocr_parser.supports("foto.png")? → SÍ → ocr_parser.parse()
        │
        ▼
   Recolecta todos los triples
        │
        ▼
   Escribe archivo JSONL
```

El orquestador **no sabe** cómo parsear cada tipo — solo sabe **enrutar** al parser correcto. Es como un switch case inteligente.

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

Esto es lo que el LLM puede razonar. Si tienes 100 triples de un paciente, el LLM puede decir "Este paciente tiene diabetes, toma metformina, y su presión es alta".

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

## 📡 upload.py — El router FastAPI

```python
@router.post("/api/upload")
async def upload_file(
    file: UploadFile,
    user: dict = Depends(get_current_user)  # JWT auth
):
    # 1. Validar tipo MIME (python-magic, no solo extensión)
    # 2. Validar tamaño (max 10MB)
    # 3. Llamar distill(file)
    # 4. Guardar metadata en MongoDB
    # 5. Retornar {triples_count: N}
```

Es el **punto de entrada** — el único lugar donde el usuario interactúa con el ETL.

---

## 🔄 Flujo completo

```
1. Usuario sube "receta.pdf" vía POST /api/upload
2. JWT validado (¿está autenticado?)
3. python-magic detecta: application/pdf
4. distill("receta.pdf") se ejecuta
5. pdf_parser.supports() → True
6. pdf_parser.parse() extrae texto del PDF
7. Si el PDF tiene imágenes escaneadas → fallback a OCR (Tesseract)
8. Triple extraction: "Paciente tiene diabetes" → triple
9. Metadata enrichment: agrega source_file, page, timestamp
10. Escribe: data/triples/{user_id}/receta_123.jsonl
11. Guarda metadata del documento en MongoDB
12. Retorna HTTP 201 {triples_count: 15}
```

---

## 📐 Arquitectura resumida

```
┌─────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                       │
│                                                         │
│  POST /api/upload ──→ distill() ──→ Parser Protocol     │
│       │                   │              │              │
│       │                   │         ┌────┼────┐        │
│       │                   │         │    │    │        │
│       │                   │       PDF  HTML  EML  OCR  │
│       │                   │         │    │    │    │    │
│       │                   │         └────┼────┘        │
│       │                   │              │              │
│       │                   │         Triple Extraction  │
│       │                   │              │              │
│       │                   │         JSONL Output       │
│       │                   │              │              │
│       ▼                   ▼              ▼              │
│    MongoDB          data/triples/{user_id}/             │
│  (doc metadata)     {doc_id}.jsonl                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🏗️ Patrones de Diseño y Principios SOLID

### Patrones aplicados

#### Strategy (Estrategia)

Cada parser es una **estrategia** diferente para extraer texto:

```
DocumentParser (Protocol)
    ├── PdfParser      → Estrategia para PDFs
    ├── HtmlParser     → Estrategia para HTML
    ├── EmlParser      → Estrategia para emails
    └── OcrParser      → Estrategia para imágenes
```

`distill()` **selecciona** la estrategia correcta en runtime sin saber cómo funciona internamente. Si mañana agregas un parser de Word, solo creas la clase — `distill()` no cambia.

#### Factory Method (Método Factory)

`distill()` actúa como un **factory**: dado un archivo, crea (o selecciona) el parser correcto:

```python
def distill(file_path: str) -> list[Triple]:
    for parser in [pdf_parser, html_parser, eml_parser, ocr_parser]:
        if parser.supports(file_path):
            return parser.parse(file_path)
```

No dice `PdfParser()` directamente — pregunta "¿quién puede con esto?" y usa al que responda.

#### Facade (Fachada)

`upload.py` es una **fachada**: esconde toda la complejidad del ETL detrás de un solo endpoint:

```
Usuario solo ve:    POST /api/upload
Lo que pasa adentro: validación → MIME detection → routing → parsing → extraction → storage
```

El usuario no necesita saber qué es un parser, un triple, o JSONL. Solo sube un archivo.

---

### Principios SOLID

#### S — Single Responsibility (Responsabilidad Única)

Cada módulo hace **UNA sola cosa**:

| Módulo | Responsabilidad |
|--------|-----------------|
| `upload.py` | Solo maneja HTTP (recibe archivo, retorna respuesta) |
| `pipeline.py` | Solo enruta al parser correcto |
| `pdf_parser.py` | Solo extrae texto de PDFs |
| `triples.py` | Solo extrae triples del texto |

Si el parser de PDF falla, solo tocas `pdf_parser.py`. No tocas el upload, ni el orquestador, ni los triples.

#### O — Open/Closed (Abierto para extensión, cerrado para modificación)

Para agregar un parser nuevo (ej: Word .docx):

```
1. Creas: services/etl/parsers/docx.py
2. Implementas: supports() y parse()
3. Agregas: una línea en distill() para registrar el parser
```

**NO** modificas `pdf_parser.py`, `html_parser.py`, ni `triples.py`. El código existente no cambia — solo agregas.

#### L — Liskov Substitution (Sustitución de Liskov)

Cualquier implementación de `DocumentParser` puede reemplazar a otra sin romper el sistema:

```python
# Esto funciona con CUALQUIER parser
def process(parser: DocumentParser, file: str) -> list[Triple]:
    if parser.supports(file):
        return parser.parse(file)
```

No importa si es `PdfParser`, `OcrParser`, o uno futuro — todos son intercambiables.

#### I — Interface Segregation (Segregación de Interfaz)

El `DocumentParser` protocol tiene solo **2 métodos**:

```python
class DocumentParser(Protocol):
    def supports(self, file_path: str) -> bool: ...
    def parse(self, file_path: str) -> list[Triple]: ...
```

No fuerza a los parsers a implementar métodos que no necesitan. Si un parser no necesita `supports()` (ej: un parser que siempre procesa), igual puede implementarlo como `return True`.

#### D — Dependency Inversion (Inversión de Dependencia)

`distill()` depende de la **abstracción** (`DocumentParser`), no de las **clases concretas**:

```python
# distill() NO hace esto:
from services.etl.parsers.pdf import PdfParser  # ❌ Dependencia concreta

# distill() SÍ hace esto:
def distill(parsers: list[DocumentParser], file: str):  # ✅ Depende de la abstracción
    for parser in parsers:
        if parser.supports(file):
            return parser.parse(file)
```

Esto permite cambiar los parsers sin tocar el orquestador.

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
2026-08-31T10:00:01 [abc-123] INFO etl-service: Fetching file from MongoDB GridFS
2026-08-31T10:00:01 [abc-123] INFO etl-service: File fetched successfully
2026-08-31T10:00:02 [abc-123] INFO etl-service: Starting ETL pipeline
2026-08-31T10:00:02 [abc-123] INFO etl-service: PDF parser selected (supports: True)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Extracted text from page 1 (1250 chars)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Extracted text from page 2 (980 chars)
2026-08-31T10:00:03 [abc-123] INFO etl-service: Triple extraction: 15 triples found
2026-08-31T10:00:03 [abc-123] INFO etl-service: Saved 15 triples to data/triples/user1/abc-123.jsonl
2026-08-31T10:00:03 [abc-123] INFO etl-service: Published to Kafka: task.response (success)
```

### Consumer: procesamiento con error

```
2026-08-31T10:00:01 [abc-789] INFO etl-service: Consumed from Kafka: file.uploaded
2026-08-31T10:00:01 [abc-789] INFO etl-service: Processing file: scanned.pdf (user_id=user2)
2026-08-31T10:00:01 [abc-789] INFO etl-service: Fetching file from MongoDB GridFS
2026-08-31T10:00:02 [abc-789] INFO etl-service: Starting ETL pipeline
2026-08-31T10:00:02 [abc-789] INFO etl-service: PDF parser selected (supports: True)
2026-08-31T10:00:02 [abc-789] WARNING etl-service: No text extracted from page 1 — attempting OCR
2026-08-31T10:00:05 [abc-789] INFO etl-service: OCR extracted 850 chars from page 1
2026-08-31T10:00:05 [abc-789] INFO etl-service: Triple extraction: 8 triples found
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

## 🔍 Logs por Parser

### PDF Parser

```
2026-08-31T10:00:02 [abc-123] DEBUG pdf-parser: Opening PDF: receta.pdf
2026-08-31T10:00:02 [abc-123] DEBUG pdf-parser: Page 1: 1250 chars extracted
2026-08-31T10:00:02 [abc-123] DEBUG pdf-parser: Page 2: 980 chars extracted
2026-08-31T10:00:02 [abc-123] DEBUG pdf-parser: Total: 2230 chars from 2 pages
```

### HTML Parser

```
2026-08-31T10:00:02 [abc-123] DEBUG html-parser: Opening HTML: page.html
2026-08-31T10:00:02 [abc-123] DEBUG html-parser: Stripped 15 tags, 3 scripts
2026-08-31T10:00:02 [abc-123] DEBUG html-parser: Extracted 1800 chars
```

### EML Parser

```
2026-08-31T10:00:02 [abc-123] DEBUG eml-parser: Opening EML: email.eml
2026-08-31T10:00:02 [abc-123] DEBUG eml-parser: Headers: From, To, Subject, Date
2026-08-31T10:00:02 [abc-123] DEBUG eml-parser: Body: 950 chars (text/plain)
2026-08-31T10:00:02 [abc-123] DEBUG eml-parser: Attachments: 2 files
```

### OCR Parser

```
2026-08-31T10:00:02 [abc-123] DEBUG ocr-parser: Opening image: foto.png
2026-08-31T10:00:02 [abc-123] DEBUG ocr-parser: Preprocessing: grayscale + contrast + sharpen
2026-08-31T10:00:04 [abc-123] DEBUG ocr-parser: OCR extracted 850 chars (confidence: 0.92)
```

---

## 🔗 Logs por Triple Extraction

```
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Processing 2230 chars
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Pattern "is": 5 matches
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Pattern "has": 4 matches
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Pattern "takes": 3 matches
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Pattern "performs": 2 matches
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Pattern "diagnosed_with": 1 match
2026-08-31T10:00:03 [abc-123] DEBUG triple-extraction: Total: 15 triples extracted
```

---

## 📁 Logs por Pipeline (distill)

```
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: File: receta.pdf (2.5 MB)
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: MIME type: application/pdf
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: Selecting parser: PdfParser
2026-08-31T10:00:02 [abc-123] DEBUG pipeline: Parser supports: True
2026-08-31T10:00:03 [abc-123] DEBUG pipeline: Parser returned: 15 triples
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
T+1.001s  [abc-123] INFO  etl-service: Fetching file from GridFS
T+1.500s  [abc-123] DEBUG pipeline: Selecting parser: PdfParser
T+2.000s  [abc-123] DEBUG pdf-parser: Page 1: 1250 chars
T+2.500s  [abc-123] DEBUG pdf-parser: Page 2: 980 chars
T+3.000s  [abc-123] DEBUG triple-extraction: 15 triples extracted
T+3.001s  [abc-123] INFO  etl-service: Published to Kafka: task.response (success)
T+3.500s  [abc-123] INFO  api-gateway: Task completed successfully
```

### Upload con OCR fallback

```
T+0.000s  [abc-456] INFO  api-gateway: POST /api/upload
T+0.003s  [abc-456] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-456] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.500s  [abc-456] DEBUG pipeline: Selecting parser: PdfParser
T+2.000s  [abc-456] WARNING pdf-parser: No text on page 1 — OCR fallback
T+2.001s  [abc-456] DEBUG ocr-parser: Preprocessing: grayscale + contrast
T+4.000s  [abc-456] DEBUG ocr-parser: OCR extracted 850 chars (confidence: 0.92)
T+4.500s  [abc-456] DEBUG triple-extraction: 8 triples extracted
T+4.501s  [abc-456] INFO  etl-service: Published to Kafka: task.response (success)
```

### Upload con error

```
T+0.000s  [abc-789] INFO  api-gateway: POST /api/upload
T+0.003s  [abc-789] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-789] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.500s  [abc-789] DEBUG pipeline: Selecting parser: PdfParser
T+2.000s  [abc-789] ERROR etl-service: Processing failed: PDF is corrupted
T+2.001s  [abc-789] ERROR etl-service: Published error response (http_code=500)
T+2.500s  [abc-789] WARNING api-gateway: Retrying (1/3)
```
