## 1. On-device packs

- [x] 1.1 Add `services/finetune/export_on_device.py` with `--fixture`. It writes `models/on-device/base/manifest.json` and a small weight file for `qwen3.5-4b-base-q4` (family `Qwen3.5-4B`, tier `free`, quantization `Q4`, parameters `4.0B`, lowercase `sha256` of the file). A checksum mismatch marks the pack not ready. Document `--real` as the laptop Q4 export of base Qwen3.5-4B, and that it does not write the LLM container weights. (≤2h)
- [x] 1.2 Extend the same script with `premium --user-id`. Read `ADAPTER_OUTPUT_DIR/{user_id}/adapter`. With `--fixture`, write `models/on-device/users/{user_id}/` for `qwen3.5-4b-finetuned-q4` including `user_id`. No adapter means no premium file and the base pack stays. Do not add a download route on port 8004. (≤2h)

## 2. API Router download

- [x] 2.1 Add `ONDEVICE_MODEL_DIR`, `GET /api/models/on-device`, and `GET /api/models/on-device/file`. Plan comes from the JWT. Ignore a client `tier` query. Free metadata and file are the base pack. Premium metadata is that user's pack (`ready` false, empty `filename` and `sha256`, `bytes` 0 when missing). Premium file is HTTP 404 when not ready, and never another user's bytes or the base file. Log `X-Request-ID` and the path, not the bytes. No LLM call and no Kafka. Rate limits 30/min metadata and 5/min file (HTTP 429). `GET /health` stays public. (≤2h)
- [x] 2.2 Router tests: free base file, free query cannot select the premium pack, premium 404 without a pack, user B does not receive user A's file, 401 without a JWT, checksum mismatch is not ready, web `POST /api/chat` still behaves as before. (≤2h)

## 3. App shell and auth

- [x] 3.1 Scaffold `apps/mobile/` (React Native, TypeScript, iOS). Native stack: auth when there is no token, otherwise Local AI Chat. Warm off-white background, brown primary, Encefalus mark. `API_BASE_URL` defaults to `http://localhost:8000`. (≤2h)
- [x] 3.2 Auth screen: Sign in / Sign up, Continue, the privacy card, and the footer "Free local AI on iPhone" / "Premium Digital Brain on web". No Apple, Google, Forgot password, or "or continue with". Sign in sends email and password to `POST /api/auth/signin`. Sign up sends name, email, password, and `plan: "free"` to `POST /api/auth/signup`. Store `access_token` and `user` in the Keychain. HTTP 401 and 409 stay on auth and show the router detail. (≤2h)

## 4. Local chat and the engine

- [x] 4.1 Local AI Chat: title, menu to the three secondary screens, new empty thread, composer placeholder "Ask anything...", attach and image, no microphone. A question accepts at most five text or PDF files. Extracted text stays in the thread and is included in later on-device questions. A sixth file, an image, or a file with no text is refused on the phone. Persist threads in the sandbox keyed by user id. A second account does not see the first account's threads. (≤2h)
- [x] 4.2 Add `OnDeviceEngine` (`load`, `generate`, `cancel`, `stats`). Ship a fake engine for tests and a native iOS module (ExecuTorch with the Core ML / Metal delegate, or MLC on Metal behind the same interface). Free always loads the base Q4 pack, never a LoRA pack, shows "On Device" and "Runs completely on your iPhone. No cloud required.", and does not call `POST /api/chat`. The local prompt includes the thread's extracted file text. No installed base pack does not call `POST /api/chat`. Record elapsed time and output token count. (≤2h)

## 5. Model status and storage

- [x] 5.1 Model & Device Status: "Qwen 3.5 4B", "Open source LLM · 4.0B parameters", the description line, measured model bytes and cache bytes against a 4.1 GB budget, ready, offline, and the average time of short replies (≤64 output tokens) from engine stats. Premium with no personal pack says the personal model is not built yet and uses the base pack when it is installed. (≤2h)
- [x] 5.2 Reinstall reads `GET /api/models/on-device` then streams `GET /api/models/on-device/file` with the bearer token and `X-Request-ID`. Replace the installed pack only after `sha256` matches. A failed download keeps the old pack. Clear Cache drops cache bytes and keeps the pack and threads. (≤2h)

## 6. Plan, settings, and premium cloud

- [x] 6.1 Free vs Premium: the seven-row table, the two headlines, and "Use the web app for memory, RAG, analytics and more." Free Upgrade calls `PATCH /api/account` with `{ "plan": "premium" }` and stores the new session. Premium does not call that route and points Memory, Simulator, Analytics, and Shield at the web app. (≤2h)
- [x] 6.2 Settings: Theme System / Light / Dark (default System, persisted), "Keep data on device" default on. On device, the line is "Conversations and files stay on this iPhone. Nothing is sent to the cloud." Free cannot turn the toggle off. On Premium the toggle and the chat pill are one switch: on is the LoRA pack, off is Digital Brain. Measured App Storage, Clear All Data after confirmation (local threads, cache, and model files only — no `DELETE /api/data`), Help & FAQ and About Encefalus v1.0.0 with no `/api` call, the premium footer, and sign out. Sign out drops the token and that user's threads and fine-tuned pack, returns to auth, and may keep the base pack. (≤2h)
- [x] 6.3 Premium On device loads `qwen3.5-4b-finetuned-q4` for that user, or the base pack with "personal model is not built yet" when the LoRA pack is missing. Local files follow the five-file rule and do not call `/api/chat`. Premium Digital Brain: first cloud question calls `POST /api/chats` and stores `session_id`; the question calls `POST /api/chat` with `use_rag: true` and up to five `attachments`. No `POST /api/upload` from the composer. Pill and footer show Digital Brain. Requests stay on the router `/api` origin. (≤2h)

## 7. Tests

- [x] 7.1 App tests with the fake engine: no token shows auth; sign-up body is plan free; Apple, Google, and Forgot password are absent; the composer has no microphone; Free send uses the base pack and does not fetch `/api/chat` or `/api/upload`; five local files are included in the prompt and a sixth is refused; an image is refused on device; missing base pack does not fetch `/api/chat`; Free toggle stays on; Clear All Data does not call `DELETE /api/data`; Premium On device uses the LoRA pack; Premium Digital Brain send uses `use_rag: true` and chat attachments, not `/api/upload`; status shows the fake engine's average time. (≤2h)
- [x] 7.2 Device check, written into the export experiment note: on an iPhone with a real Q4 pack, a short reply finishes within 2 seconds and above 18 tokens per second. Jest does not claim that number. (≤2h)

## F. Documentation (output/)

- [x] 8.1 Create `output/diagrams/mobile-architecture.drawio`. Phone and the Q4 pack in green. API Router, LLM container, and Fine-Tune adapter directory in blue. The phone's only server edge is the router. Free chat ends on the device. (≤2h)
- [x] 8.2 Create `output/diagrams/mobile-dataflow.drawio`. Auth, on-device generate with up to five local files, pack download with checksum, the Premium switch, Digital Brain chat with RAG, and the error paths (401, 404 pack, bad checksum, missing pack, sixth file). No OAuth and no microphone. (≤2h)
- [x] 8.3 Create `output/diagrams/README.md` with the arrow legend and the colour scheme.
- [x] 8.4 Create `output/documents/justificacion-ejemplo.md`. Cover Free base-on-device versus Premium LoRA versus Digital Brain, the five local files, the per-user pack, the engine interface, and the patterns in `design.md`. Include structured logs for `POST /api/auth/signin`, `GET /api/models/on-device/file`, an on-device generate line, and a premium `POST /api/chat`, using `{timestamp} [{correlation_id}] {level} {service}: {message}`.
