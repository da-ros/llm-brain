# Correr el LLM Service localmente (puerto 8003)

El LLM Service corre **en el host**, no en Docker Compose. Los contenedores lo
alcanzan por `host.docker.internal:8003`. Qué runtime usa lo decide cada máquina
con una sola variable: `LLM_BACKEND`.

| `LLM_BACKEND` | Runtime | Se usa en |
| --- | --- | --- |
| `qwen_local` (default) | Qwen3.5-4B bfloat16 in-process vía torch + transformers | Mac (Metal) |
| `ollama` | Server local de [Ollama](https://ollama.com) por HTTP | Linux / Windows |

`QWEN_MOCK=true` **gana sobre cualquier backend**: CI y unit tests nunca cargan
pesos ni abren un socket, sin importar lo que diga `.env`. El default en `config.py`
es `QWEN_MOCK=true`, así que una máquina sin `.env` siempre queda en el mock.

## Setup por máquina

Elige el preset de tu máquina, cópialo a `.env` en la raíz del repo (nunca
commitees `.env`) y ajusta:

```bash
# Mac (in-process Metal)
cp .env.example-mac .env

# Linux / Windows (Ollama)
cp .env.example-linux .env
```

### Mac — `qwen_local`

1. Instala los GPU requirements (aquí es el único lugar donde se instala torch):
   ```bash
   pip install -r services/llm/requirements-gpu.txt
   ```
2. El checkpoint debe existir (raíz del repo `Qwen3.5-4B/`, ~9.3 GB, 2 shards).
3. Preset `.env`: `LLM_BACKEND=qwen_local`, `QWEN_DEVICE=mps`, `QWEN_MOCK=false`.

### Linux / Windows — `ollama`

No hace falta torch: el backend solo habla HTTP con Ollama.

1. Instala Ollama (Linux — necesita sudo):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
   En Windows: instalador desde [ollama.com/download](https://ollama.com/download).
2. Descarga el modelo una vez (~4 GB):
   ```bash
   ollama pull qwen3.5:4b
   ```
3. Preset `.env`: `LLM_BACKEND=ollama`, `OLLAMA_URL=http://127.0.0.1:11434`,
   `QWEN_MOCK=false`.
4. El server de Ollama debe estar corriendo (`ollama serve` — el instalador
   normalmente lo deja como servicio del SO).

## Arrancar el service

```bash
cd services/llm
uvicorn main:app --host 0.0.0.0 --port 8003
```

Smoke test:

```bash
curl http://localhost:8003/health      # muestra el backend + provider en uso
curl -X POST http://localhost:8003/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "hola", "user_id": "u1"}'
```

`/health` reporta el backend **real**, por ejemplo:

```json
{"status": "ok", "backend": "ollama", "provider": "ollama", "model": "qwen3.5:4b"}
```

Con el mock activo (default, o `QWEN_MOCK=true`) reporta
`"provider": "mock"`.

## Notas

- **Tests / CI:** siempre en mock. `test_llm.py` fuerza `QWEN_MOCK=true` al
  importar; GitHub Actions instala solo `services/*/requirements.txt` (sin torch).
- **Multimedia:** las imágenes se envían a Ollama en base64 (el tag `qwen3.5:4b`
  trae un encoder CLIP de visión); los videos **no** están soportados por Ollama
  y degradan a un marker de texto `[video]`.
- **Windows:** cubierto por el preset `ollama` (el contenido es agnóstico de SO,
  solo cambia cómo se instala Ollama). El backend `qwen_local` teóricamente
  funcionaría con `QWEN_DEVICE=cuda` o CPU, pero está sin probar.