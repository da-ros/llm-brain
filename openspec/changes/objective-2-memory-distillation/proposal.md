## Proposal: One-Tap Memory Distillation

### Context

Users need to load personal documents (medical recipes, invoices, photos, emails)
into the platform and have them automatically processed into structured knowledge
triples (subject-predicate-object) that the LLM can reason over.

### Why

1. **Knowledge extraction**: Raw documents are not directly usable by LLMs.
   Distillation converts unstructured data into structured triples.
2. **Thesis OE2**: The anteproyecto specifies an ETL pipeline with Tesseract OCR,
   PDF/HTML/EML parsers producing JSON triples.
3. **>=100 items**: The pipeline must handle at least 100 documents for validation.

### Deliverables

- Python ETL pipeline with modular parsers
- OCR integration (Tesseract) for images
- PDF, HTML, EML parser modules
- JSON triple output (subject-predicate-object + metadata)
- >=100 sample documents processed
- Pipeline configuration and error handling

### Non-Deliverables

- Real-time streaming ingestion (batch only in MVP)
- Audio/video transcription
- Multi-language OCR (Spanish + English only)

### References

- Anteproyecto: Objetivo Específico 2 (ETL pipeline)
- Depends on: Frame 1 (Architecture & Repo Foundation)
- Parallel with: Frame 3 (Hybrid Store + RAG)
