# Ejecución local del proyecto (LLM local + Docker Compose)

> Referenciado desde `openspec/input/context.txt` (sección *Despliegue*).
> Este documento cubre el proyecto **completo**: requisitos, `.env`, descarga del
> modelo Qwen desde Hugging Face, LLM Service en el host y stack de Docker Compose.
> El detalle solo del servicio LLM está en [`running-llm-local.md`](running-llm-local.md).

---

## 1. Requisitos previos

| Requisito | Versión / nota |
|-----------|----------------|
| Docker Engine o Docker Desktop | Con plugin `docker compose` v2 |
| Python | ≥ 3.13 (CI usa 3.13; el venv local puede ser 3.14) |
| `git`, `curl` | Cualquier versión reciente |
| Espacio en disco | ~10 GB (modelo Qwen) + ~3 GB (imágenes Docker) + ~4 GB (Ollama, solo si aplica) |
| GPU | **No requerida.** Metal (Mac), iGPU/CPU con Ollama (Linux/Windows) o CPU con mock |
| Ollama | Solo si el equipo usa `LLM_BACKEND=ollama` — instalar con:<br>`curl -fsSL https://ollama.com/install.sh \| sh` (Linux) · [instalador Windows](https://ollama.com/download) |
| `huggingface_hub` (CLI `hf`) | Solo si descarga el modelo con el backend `qwen_local` |

**Puertos que deben estar libres** (ver §7 para qué tocar si alguno está ocupado):
`8000`–`8009`, `8003` (LLM en host), `9092` (Kafka), `27017` (MongoDB),
`3080` (Web), `11434` (Ollama, solo si aplica).

---

## 2. Paso 1 — Clonar e instalar dependencias Python

```bash
git clone <repo-url> llm-brain && cd llm-brain
python3 -m venv .venv && source .venv/bin/activate
for f in services/*/requirements.txt; do pip install -r "$f"; done
```

> **Nota:** el `README.md` dice `pip install -r requirements.txt`, pero **no existe**
> `requirements.txt` en la raíz — el loop anterior es la forma correcta (es lo que
> hace el CI). El LLM Service añade `httpx`; los servicios de inferencia real
> (solo Mac con `qwen_local`) agregan aparte `services/llm/requirements-gpu.txt`.

---

## 3. Paso 2 — Configurar el `.env` (ejemplo: `.env.example-linux`)

Copia el preset de tu equipo a `.env` en la **raíz** del repo (nunca se commitea):

```bash
# Equipo con Ollama (Linux / Windows / iGPU AMD) — este documento usa este como ejemplo
cp .env.example-linux .env

# Equipo Mac (torch + Metal)
cp .env.example-mac .env
```

Lo que cambia entre ambos presets es **solo el bloque LLM**:

```ini
# .env.example-linux (Ollama)
LLM_BACKEND=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_THINK=false
QWEN_MOCK=false

# .env.example-mac (in-process)
LLM_BACKEND=qwen_local
QWEN_DEVICE=mps
QWEN_MOCK=false
```

Reglas importantes:

- **`QWEN_MOCK=true` gana sobre cualquier backend** → todo corre en mock (es el
  default de `config.py`, así que sin `.env` nunca se carga un modelo por accidente).
- El `.env` de la raíz lo lee el **LLM Service** (usa ruta absoluta en `config.py`)
  y **Docker Compose** para las variables `${...}` de `docker-compose.yml`
  (`JWT_SECRET_KEY`, `FERNET_KEY`, `EMBEDDING_MOCK`, `LORA_MOCK`,
  `INFERENCE_TIMEOUT_SECONDS`, etc.).
- Los demás servicios **dentro de Compose** toman sus URLs de `docker-compose.yml`,
  no del `.env`. Si corres un servicio **fuera de Docker**, ese servicio busca
  `.env` en su **directorio de trabajo** (patrón `env_file=".env"`), no en la raíz.

---

## 4. Paso 3 — Descargar Qwen3.5-4B de Hugging Face

El LLM Service con `LLM_BACKEND=qwen_local` carga `Qwen/Qwen3.5-4B` (BF16, **~9.3 GB**,
2 shards) desde la caché de Hugging Face fijada en `config.py`:
`HF_HOME=<repo>/data/huggingface` (ese directorio está en `.gitignore`).

```bash
pip install -U huggingface_hub
HF_HOME=data/huggingface hf download Qwen/Qwen3.5-4B
```

- Si el repo pide licencia, acepta la licencia en Hugging Face y autentica una vez:
  `hf auth login`.
- El LLM Service **descarga solo automáticamente** al primer request real; hacerlo
  por CLI antes evita el timeout de 600 s del primer `/generate`.
- **Checkpoint ya existente:** si tienes la carpeta `Qwen3.5-4B/` en la raíz del
  repo (descargada manualmente, verificada completa), puedes apuntar a ella con una
  **ruta absoluta** en `.env` y evitar la descarga:
  `QWEN_HF_MODEL_ID=/ruta/absoluta/a/Qwen3.5-4B`.
- **Si tu equipo usa `LLM_BACKEND=ollama`**, este paso se sustituye por
  `ollama pull qwen3.5:4b` (~4 GB) — el servidor Ollama maneja su propio almacenamiento.
  La descarga de HF solo es obligatoria para `qwen_local` (y para el Fine-Tune
  Service cuando se desactive `LORA_MOCK`).
- **`OLLAMA_THINK=false` (default)** desactiva el razonamiento del modelo: en
  respuestas cortas y extracciones tarda **~10x menos** (con thinking, una
  respuesta de 3 oraciones genera ~1700 tokens de razonamiento; sin él, ~100).

**Rendimiento verificado** (2026-10-25, Ryzen 7 7730U 8C/16T, 64 GB RAM, CPU
solo — iGPU AMD `gfx90c` sin kernels ROCm): **~11 tok/s** de generación con
`qwen3.5:4b` vía Ollama. Tu equipo puede variar según CPU.

---

## 5. Paso 4 — Arrancar el LLM Service (en el host, puerto 8003)

**Antes** de Docker Compose: los contenedores llaman al LLM por
`host.docker.internal:8003`, así que el proceso debe estar escuchando primero.

```bash
source .venv/bin/activate
cd services/llm
uvicorn main:app --host 0.0.0.0 --port 8003
```

Verificación:

```bash
curl http://localhost:8003/health
```

```json
{"status": "ok", "backend": "ollama", "provider": "ollama", "model": "qwen3.5:4b", ...}
```

- `provider: "mock"` → `QWEN_MOCK=true` (esperado si no tocaste `.env`).
- `provider: "ollama"` → backend Ollama activo; requiere `ollama serve` corriendo.
- `provider: "qwen-local"` → backend in-process (torch), requiere el checkpoint del §4.

Mantén esta terminal abierta (o corrígelo con `nohup`/`tmux`).

---

## 6. Paso 5 — Docker Compose

En otra terminal, desde la raíz del repo:

```bash
docker compose up --build
```

Levanta 11 servicios: api-router (8000), etl (8001), rag (8002), finetune (8004),
agents (8006), simulator (8007), analytics (8008), shield (8009), mongo (27017),
kafka (9092), chroma (8005→8000) y web (3080→3000). **El LLM no está en Compose**
— es el proceso del §5.

### Verificación (smoke test)

```bash
curl http://localhost:8003/health   # LLM (host)
curl http://localhost:8000/health   # API Router
open http://localhost:3080          # Web app
```

Flujo mínimo end-to-end: `POST /api/auth/signup` → `POST /api/auth/signin` (JWT)
→ `POST /api/chat` en el API Router :8000.

---

## 7. Puertos requeridos y qué editar si están ocupados

| Puerto | Servicio | Dónde se publica | Si está ocupado, edita… |
|--------|----------|------------------|--------------------------|
| 8000 | API Router | `docker-compose.yml` | `ports:` lado izquierdo de `api-router` |
| 8001 | ETL | `docker-compose.yml` | idem `etl-service` |
| 8002 | RAG | `docker-compose.yml` | idem `rag-service` |
| **8003** | **LLM Service (host)** | **proceso uvicorn** | **`.env` → `LLM_PORT`** **+** `docker-compose.yml` → las 5 líneas `LLM_SERVICE_URL=http://host.docker.internal:8003` (⚠️ hardcodeadas, ver §8) |
| 8004 | Fine-Tune | `docker-compose.yml` | idem `finetune-service` |
| 8005 | Chroma (host) → 8000 (contenedor) | `docker-compose.yml` | idem `chroma`; si RAG corre fuera de Docker: `.env` → `CHROMA_HOST`/`CHROMA_PORT` |
| 8006 | Agents | `docker-compose.yml` | idem `agents-service` |
| 8007 | Simulator | `docker-compose.yml` | idem `simulator-service` |
| 8008 | Analytics | `docker-compose.yml` | idem `analytics-service` |
| 8009 | Shield | `docker-compose.yml` | idem `shield-service` |
| 27017 | MongoDB | `docker-compose.yml` | idem `mongo` (cuidado: rompe `MONGODB_URI` si otros servicios lo usan por host) |
| 9092 | Kafka | `docker-compose.yml` | ⚠️ **no recomendado**: exige cambiar también `KAFKA_ADVERTISED_LISTENERS` y el bootstrap de todos los servicios |
| 3080 | Web | `docker-compose.yml` | idem `web` |
| 11434 | Ollama (host) | servidor Ollama | `.env` → `OLLAMA_URL` **+** `OLLAMA_HOST` del servidor Ollama (p.ej. `OLLAMA_HOST=0.0.0.0:11435` en el servicio del SO) |

Regla general para los servicios en Compose: cambia **solo el lado izquierdo** del
mapeo (`"80XX:80XX"` → `"80YY:80XX"`). El lado derecho y los nombres DNS internos
(`rag-service:8002`, `kafka:9092`, `mongo:27017`) **no se tocan**: el tráfico
entre contenedores usa el puerto interno.

---

## 8. URLs: auditoría (nada funcional está quemado)

- **Capa de configuración (`config.py` de cada servicio):** todas las URLs son
  **defaults de pydantic-settings**, sobreescribibles por variable de entorno
  (`MONGODB_URI`, `KAFKA_BOOTSTRAP_SERVERS`, `LLM_SERVICE_URL`, `OLLAMA_URL`, …).
  ✔️ sin URLs quemadas.
- **`docker-compose.yml`:** usa nombres DNS de servicio (correcto) y
  `host.docker.internal:8003` para el LLM, **hardcodeado sin `${...}`** — es la
  única URL con riesgo funcional: si `LLM_PORT` cambia, hay que editar el compose
  a mano (5 apariciones: api-router, etl, agents, simulator, shield, analytics).
- **Excepción conocida:** `services/finetune/export_on_device.py` define
  `BASE_GGUF_URL` como constante a Hugging Face (`unsloth/Qwen3.5-4B-GGUF`) — URL
  externa fija, no configurable por entorno (solo afecta al export on-device).
- **Ollama:** la URL vive en `config.py` (`OLLAMA_URL`) y el default del parámetro
  de `OllamaProvider` es redundante pero inocuo — el resolver siempre pasa la de
  Settings.

---

## 9. Troubleshooting rápido

| Síntoma | Causa probable | Fix |
|---------|----------------|-----|
| `/health` → `provider: "mock"` | `QWEN_MOCK=true` o sin `.env` | Edita `.env` (`QWEN_MOCK=false`) y reinicia el LLM Service |
| `POST /api/chat` → 502/500 | Proceso 8003 no levantado o caído | Levanta uvicorn (§5) antes que Compose |
| 504 en `/generate` | Primera carga del modelo (descarga HF + load) | Descarga por CLI (§4) y reintenta |
| `Ollama server not reachable` | `ollama serve` no corriendo o URL distinta | `ollama serve` / revisa `OLLAMA_URL` |
| `Ollama model ... not found` | Modelo no descargado | `ollama pull qwen3.5:4b` |
| `ollama ps` → 100% CPU (sin GPU) | **Normal** en iGPU AMD sin kernels ROCm (p. ej. `gfx90c`) — Ollama cae a CPU | No es error; funciona igual. Verificado: ~11 tok/s en CPU |
| Genera tokens "de más" o muy lento | Thinking del modelo activo | `.env` → `OLLAMA_THINK=false` (default) y reinicia el LLM Service |
| `port is already allocated` | Conflicto de puertos | Tabla §7 — archivo a editar según el puerto |