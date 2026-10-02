## Context

See proposal.md — Why. Frame 4 already serves base Qwen3.5-4B in the
LLM container and writes a LoRA adapter per user at
`ADAPTER_OUTPUT_DIR/{user_id}/adapter`. Frame 7 already signs people in
with `POST /api/auth/signup` and `POST /api/auth/signin`, and changes
plan with `PATCH /api/account`. Premium web modules stay in `apps/web/`.

This design adds the iPhone app and the Q4 packs it downloads. Behavior
is in the three specs. This file is the approach.

## Goals / Non-Goals

**Goals:**

- Five screens that follow the attached wireframes, in English, on
  iPhone.
- Free text answers from the base Q4 pack, with up to five local files.
- A shared base pack and a per-user LoRA pack, served only by the API Router.
- Premium can switch that chat to the cloud harness (`POST /api/chat` with RAG).

**Non-Goals:**

- Android, Expo Go, a PWA, or WebGPU.
- Apple sign-in, Google sign-in, a password-reset email, or a microphone.
- On-device image or video inference.
- Phone screens for Memory, Decisions, Analytics, Shield, or Learning.
- Replacing the container weights with the LoRA adapter.
- Quantizing the real 4B weights inside CI.

## Decisions

### 1. React Native app, iOS only, engine behind an interface

**Decision**: `apps/mobile/` is a React Native TypeScript app aimed at
iOS. Navigation is a native stack with two states: auth, and the app.
The app state opens on Local AI Chat. Model & Device Status, Free vs
Premium, and Settings are pushed screens. The JWT lives in the iOS
Keychain. Threads, theme, and the privacy toggle live in the app
sandbox, keyed by user id.

Generation goes through an `OnDeviceEngine` interface:
`load(path)`, `generate(prompt)` yielding tokens, `cancel()`, and
`stats()` returning elapsed milliseconds and output token count for the
last reply. The shipping engine is a native module that runs ExecuTorch
with the Core ML / Metal delegate. If Qwen3.5-4B cannot be lowered to
that runtime during implementation, the same interface is filled by
MLC LLM on Metal. UI code does not import either runtime. Tests use a
fake engine that yields a fixed reply and fixed stats.

**Alternatives considered**:

- Expo Go — rejected. It cannot ship a Metal inference module.
- Calling the LLM container for Free — rejected. Frame 4 and context
  put Free on the device.
- Bundling the 2.8 GB weights in the app binary — rejected. The
  wireframe downloads and reinstalls the pack.

### 2. Screens follow the wireframes

The visual language matches the wireframes and the Encefalus web mark:
warm off-white background, brown primary button, brain mark. Copy that
the specs quote is the copy on screen.

| Screen | Who | What the person can do |
| --- | --- | --- |
| Auth | no token | Sign in (email, password). Sign up (name, email, password, plan free). No Apple, Google, or Forgot password. |
| Local AI Chat | signed in | Transcript, new thread, menu, attach, image. Free pill is the label "On Device". Premium pill is the inference switch. |
| Model & Device Status | signed in | Measured model bytes, cache bytes, 4.1 GB budget, ready, offline, average short-reply time. Reinstall. Clear Cache. |
| Free vs Premium | signed in | The seven-row table. Free can upgrade. Premium is told the other rows are the web app. |
| Settings | signed in | Theme (System, Light, Dark). Keep data on device, which is the same Premium switch. Measured storage. Clear All Data. Help & FAQ. About v1.0.0. Sign out. |

Help & FAQ and About are local screens. They do not call the router.

The composer has attach, image, and the field "Ask anything...". There
is no microphone. Attach and image add files, up to five on a question.

### 3. One switch, two models for Premium

**Decision**: Free has no switch. Every question uses the base Q4 pack.
The pill is a label.

Premium has one boolean, default on-device. The chat pill and Settings
"Keep data on device" read and write it.

```
Free                         → base Q4 + up to 5 local files
Premium, On device           → that user's LoRA Q4 (else base Q4) + up to 5 local files
Premium, Digital Brain       → POST /api/chat { message, use_rag: true, session_id, attachments }
```

On-device files: the phone reads plain text and PDF text into the
thread and prepends it to this question and later questions in that
thread. Bytes never leave the phone. A sixth file is refused. An image,
or a file with no text, is refused locally.

Digital Brain files: the same cap of five. They are `attachments` on
`POST /api/chat` (`filename`, `content_base64`). Retrieval stays on, so
the cloud base model also sees that user's RAG memory. The composer
does not call `POST /api/upload`. Putting a file into lifelong memory
stays on the web Memory screen.

The first Digital Brain question in a thread calls `POST /api/chats`,
stores the id, and sends it as `session_id`. Later cloud questions in
that thread reuse it. On-device questions do not create a server chat.

A missing base pack does not switch a Free or On device question to
`POST /api/chat`. Until a user's LoRA pack exists, On device uses the
base pack and the status screen says the personal model is not built yet.

Cloud mode replaces the pill and the footer. "Runs completely on your
iPhone. No cloud required." is shown only while the engine is answering.

### 4. Packs on disk, download through the router

**Decision**: Directory `ONDEVICE_MODEL_DIR` (default `models/on-device/`,
gitignored):

```
models/on-device/
├── base/
│   ├── manifest.json
│   └── qwen3.5-4b-base-q4.pte
└── users/
    └── {user_id}/
        ├── manifest.json
        └── qwen3.5-4b-finetuned-q4.pte
```

`manifest.json` fields: `id`, `family`, `tier`, `quantization`,
`parameters`, `filename`, `bytes`, `sha256`, and `user_id` on a premium
manifest. `sha256` is lowercase hex. A mismatch means `ready: false`.

Export script: `services/finetune/export_on_device.py`.

- `base` writes the shared pack from base Qwen3.5-4B, Q4, no adapter.
- `premium --user-id` reads `ADAPTER_OUTPUT_DIR/{user_id}/adapter`,
  merges, quantizes, and writes `users/{user_id}/`. No adapter means no
  file.
- CI and unit tests run with `--fixture`. That writes a small weight
  file and a true checksum. It does not download or quantize 4B.
- `--real` is the laptop step that runs the actual Q4 export. It is
  documented in the frame justificacion and is not a CI job. The cloud
  container directory is not an output path.

Router:

- `GET /api/models/on-device` returns the manifest plus `ready`. Plan
  comes from the JWT. A `tier` query is ignored. Premium `ready: false`
  uses empty `filename` and `sha256` and `bytes: 0`.
- `GET /api/models/on-device/file` streams the weight file. Premium
  without a ready pack is HTTP 404. Free always gets `base/`.
- Both routes log `X-Request-ID` and the path. They do not log bytes.
  They do not call port 8003 and do not publish Kafka.
- Rate limit: 30 metadata requests per minute, 5 file starts per
  minute, HTTP 429 past that.

The phone downloads to a temporary file, checks `sha256`, then replaces
the installed pack. A failure leaves the old pack. Reinstall uses the
same path. Clear Cache deletes the cache directory only. Clear All Data
asks for confirmation, then deletes that user's threads, cache, and
installed packs on the phone. Sign out deletes the token, that user's
threads, and a fine-tuned pack; the shared base pack may remain so the
next Free sign-in can still run offline.

### 5. Latency

The engine records elapsed time and output tokens on every completed
reply. Model & Device Status shows the average elapsed time of the
latest short replies (replies at or under 64 output tokens). The device
check in the spec (≤2s and >18 tok/s) is run on an iPhone with a real
Q4 pack and written into the experiment note for that export. Jest
asserts that the screen prints the stats the fake engine returned.

### 6. Account and router base URL

The app reads `API_BASE_URL`. The iOS simulator uses
`http://localhost:8000`. A physical iPhone uses the laptop's LAN
address. Every router call sends `Authorization: Bearer` and a new
`X-Request-ID`. Sign-up and sign-in are the only calls without a
bearer token.

Upgrade sends `PATCH /api/account` with `{ "plan": "premium" }` and
stores the new session from the response. The web app's Free chat route
is not modified.

## Data Flow

```
Auth
  email + password ──POST /api/auth/signin|signup──► API Router :8000
  JWT ◄───────────────────────────────────────────── session JSON
  JWT → Keychain

Free question
  text + up to 5 local files → base Q4 on iPhone
  thread keeps the extracted text
  (no /api/chat, no LoRA pack, no Kafka)

Premium, On device
  text + up to 5 local files → user's LoRA Q4 (else base Q4)
  (no /api/chat)

Premium, Digital Brain
  POST /api/chats (first time in the thread)
  POST /api/chat { use_rag: true, session_id, attachments≤5 }
       ──► Router ──► Agents + RAG + cloud base model
  footer shows Digital Brain

Download / Reinstall
  GET /api/models/on-device ──► Router reads ONDEVICE_MODEL_DIR
  GET /api/models/on-device/file ──► stream bytes
  phone checks sha256 → replaces local pack
  Free → base/          Premium → users/{user_id}/ or 404

Export (laptop, not on the phone)
  base weights ──Q4──► models/on-device/base/
  ADAPTER_OUTPUT_DIR/{user_id}/adapter ──merge + Q4──► models/on-device/users/{user_id}/
  LLM container weights are not written

Clear All Data / Sign out
  local threads + local packs (sign out keeps base)
  account on the server stays (no DELETE /api/data)
```

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| Qwen3.5-4B does not lower to ExecuTorch | The UI depends on `OnDeviceEngine`. MLC on Metal can fill the same interface. |
| CI cannot quantize a 4B model | `--fixture` covers manifest, checksum, and router streaming. `--real` is a laptop step with an experiment note. |
| A 3 GB download fails halfway | The new file replaces the old one only after `sha256` matches. |
| Free question hits the cloud by mistake | Free has no switch. Tests assert no `/api/chat` and no LoRA pack on that path. |
| Premium pack is another user's adapter | Router selects `users/{token user_id}` only. Tests cover user A versus user B. |
| A sixth file or an image is attached on device | The phone refuses it and does not upload. |
| Physical iPhone cannot see `localhost` | `API_BASE_URL` is the laptop LAN address. On-device chat still runs after the pack is installed. |
| Personal pack does not exist yet | Premium On device uses the base pack and the status screen says the personal model is not built. |
| Cloud attachments are mistaken for memory ingest | Digital Brain sends them on `POST /api/chat` only. Lifelong memory stays the web Memory screen. |

## Migration Plan

1. Add the export script and `ONDEVICE_MODEL_DIR`. No Compose service is
   added. The router gains two routes.
2. Ship `apps/mobile` against the local router.
3. Rollback: stop using the app. The new routes are additive. Web chat,
   upload, and account routes stay as they are. Deleting
   `models/on-device/` removes packs only.

## Open Questions

None that change the specs or the task breakdown. The Metal runtime may
be ExecuTorch or MLC; the engine interface is the contract either way.

## Configuration

```
ONDEVICE_MODEL_DIR=models/on-device
ADAPTER_OUTPUT_DIR=          # already set by the Fine-Tune Service
API_BASE_URL=http://localhost:8000
```

Router rate limits: `RATE_LIMIT_MODEL_METADATA=30`,
`RATE_LIMIT_MODEL_FILE=5`.

The phone stores `access_token`, `user` `{id, name, email, plan}`,
theme, and the Premium switch (default On device). Threads, including
extracted file text, are files in the sandbox, not MongoDB documents.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
| --- | --- | --- |
| **Strategy** | Base pack, LoRA pack, or `POST /api/chat` | Free is always the base pack. The Premium switch picks LoRA or cloud chat. |
| **Adapter** | `OnDeviceEngine` over ExecuTorch or MLC | Screens do not depend on the Metal runtime |
| **Facade** | API Router | Auth, plan, pack download, and premium cloud use port 8000 only |
| **Gate** | Auth stack; Free plan; missing pack | No token stays on auth; Free cannot select Digital Brain; no pack never calls chat |
| **Repository** | Sandbox thread store | Threads stay on the phone and are keyed by user id |
| **DTO** | `manifest.json` | The phone verifies the same checksum the router advertises |

### SOLID Principles Applied

| Principle | Application |
| --- | --- |
| **S** | Screens render one wireframe each. Export writes packs. The router streams a pack. The engine generates text. |
| **O** | A new Metal runtime implements `OnDeviceEngine` without a screen change. A new manifest field can be added without a new route shape. |
| **L** | The fake engine and the native engine both load, generate, and report stats. |
| **I** | Chat depends on the engine interface. It does not take the router client. The router file route does not take the export code. |
| **D** | Screens depend on the engine and the router URL. The export depends on the adapter directory, not on the phone. |
