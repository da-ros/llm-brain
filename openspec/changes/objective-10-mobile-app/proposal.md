## Why

The thesis client for Qwen3.5-4B on the iPhone does not exist yet. Frame 4
serves the **base** model in a local container and writes a LoRA adapter for
a later on-device build. Frame 7 is the Encefalus web app, where Memory,
Decisions, Analytics, Shield, and Learning already live. Frame 10 is the
React Native app: Free runs the base model quantized on the phone, and
Premium adds the fine-tuned on-device build plus the Digital Brain that
Frame 7 already exposes on the web.

## Context from Frame 4 and Frame 7

- **Frame 4 (LLM Service, port 8003)**: the container serves **base**
  Qwen3.5-4B for Premium cloud inference. Free chat is specified as
  on-device and is not handled by that container. Target for a short
  on-device reply: ≤2s and >18 tok/s. Weights are about 2.5–3 GB at Q4.
- **Frame 4 (Fine-Tune Service, port 8004)**: local LoRA writes an
  adapter. This frame merges that adapter and quantizes it to Q4 for the
  Premium phone build. The container stays base.
- **Frame 1.1**: JWT, `X-Request-ID`, and the router on port 8000. The
  phone uses the same account routes as the web app:
  `POST /api/auth/signup`, `POST /api/auth/signin`, `GET /api/account`,
  `PATCH /api/account`.
- **Frame 7**: Encefalus (mark, name, English copy). A new account is
  free. Premium screens for lifelong memory, RAG, the decision simulator,
  analytics, and the shield are the web app. Sign-up is name, email, and
  password. OAuth federado is out of scope there.
- **Frames 2, 3, 5, 6, and 8** stay on the server. The phone does not
  embed Chroma, LangGraph, the simulator, or the shield. Context says
  this frame depends on Frame 4 for the on-device model.

The attached wireframes are the screen contract for this frame. These
controls from those drawings are left out: Continue with Apple, Continue
with Google, Forgot password, and the microphone on the composer.

1. **Sign in / Sign up** — Encefalus, "AI-Augmented Brain", the line
   "Your memories. Sharper decisions. A more intentional you.", email and
   password, Continue, and the privacy card.
2. **Local AI Chat** — mode pill, a local thread, composer with one
   attach control, and, while on-device, the line "Runs completely on
   your iPhone. No cloud required."
3. **Model & Device Status** — "Qwen 3.5 4B", 4-bit files, cache, ready /
   offline / average response time, Reinstall Model, Clear Cache.
4. **Free vs Premium** — the seven-row comparison and Upgrade to Premium.
5. **Settings** — Theme, Keep data on device, local storage, Clear All
   Data, Help & FAQ, About Encefalus v1.0.0, Upgrade to Premium.

## What Changes

- Add `apps/mobile/`, a React Native iPhone app (English). Android, a
  PWA, and WebGPU are out of scope.
- **Auth.** Sign in with email and password. Sign up adds the name the
  account API already requires, with `plan: "free"`. The session is the
  JWT from the router. No Apple, Google, or password-reset control.
- **Free chat** always runs **Qwen3.5-4B base, Q4**, on the phone. No
  LoRA. No `POST /api/chat`. A question may include up to five files.
  Those files stay on the phone and are text context for the local
  model, including later questions in the same thread.
- **Model pack.** An offline export writes a shared base Q4 pack,
  `qwen3.5-4b-base-q4`, and a per-user premium pack,
  `qwen3.5-4b-finetuned-q4`, merged from that user's LoRA adapter
  (`ADAPTER_OUTPUT_DIR/{user_id}/adapter`). Until that user's file
  exists, Premium on-device keeps the base pack and says the personal
  model is not built yet. The cloud container is not replaced.
- **Model & Device Status** shows measured sizes against a 4.1 GB budget,
  model-ready, offline-ready, and the average time of short replies.
  Reinstall downloads again. Clear Cache removes cache only.
- **Free vs Premium** uses the wireframe rows. Checks for Lifelong
  Memory, RAG over files, Decision Simulator, Analytics & Insights, and
  Shield mean the web Digital Brain (Frame 7), not new phone screens.
  Upgrade calls `PATCH /api/account` with `plan: "premium"`.
- **Premium switch.** One control, default **On device**. The chat pill
  and Settings "Keep data on device" are the same switch. **On device**
  runs that user's LoRA Q4 pack (base Q4 until the pack exists) and
  accepts the same five local files. **Digital Brain** calls
  `POST /api/chat` with retrieval on, so the turn uses the cloud base
  model, RAG, stored memory, and the agent harness. Up to five files on
  that question are sent as chat attachments. Free cannot move the
  switch. Lifelong Memory, the simulator, analytics, and shield stay
  web screens.
- **Settings.** Theme is System, Light, or Dark (default System). Clear
  All Data removes conversations, cache, and model files **on this
  iPhone** and does not call `DELETE /api/data`. Sign out returns to
  the auth screen; a fine-tuned pack and local threads for that account
  are removed, the base pack may stay.
- The phone does not call ports 8001–8008.
- Out of scope: voice, the microphone, Apple or Google sign-in,
  password-reset email, Android, on-device image or video inference,
  reimplementing Frame 7 screens, and changing Free web chat.

## Capabilities

### New Capabilities

- `mobile-app`: React Native iPhone app. Auth, Local AI Chat, Model &
  Device Status, Free vs Premium, and Settings. Free is the base
  on-device model plus up to five local files. Premium switches between
  that user's LoRA pack and cloud chat with RAG and memory.
- `on-device-model`: Q4 export of base Qwen3.5-4B, and the Premium pack
  that merges the Frame 4 LoRA adapter before the same quantization.
  Manifest, checksum, and the rule that the cloud container stays base.

### Modified Capabilities

- `api-router`: authenticated download of the on-device pack for the
  caller's plan. Free receives the shared base pack. Premium receives
  that user's fine-tuned pack when it has been built, and never another
  user's pack.

## Output

```
openspec/changes/objective-10-mobile-app/
├── output/
│   ├── diagrams/
│   │   ├── mobile-architecture.drawio
│   │   ├── mobile-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── mobile-app/spec.md
    ├── on-device-model/spec.md
    └── api-router/spec.md
```

## Impact

- New app: `apps/mobile/` (React Native, TypeScript, iOS). A native
  inference module sits behind an engine interface so tests can run
  without an iPhone.
- New export: a Python script next to the Fine-Tune Service. It reads
  the base weights and, for Premium, the LoRA adapter Frame 4 already
  writes. CI checks the manifest and a small fixture file. Quantizing
  the real 4B weights is a documented local step, not a CI job.
- API Router: `GET /api/models/on-device` and
  `GET /api/models/on-device/file`. Existing chat, upload, and account
  routes stay as they are. Free web chat is unchanged.
- Phone storage: threads, up to five local files per on-device thread,
  theme, the inference switch, and the installed pack. No new MongoDB
  collection. No Kafka topic.
- Docker Compose is unchanged except for the model directory the router
  reads (`ONDEVICE_MODEL_DIR`).

## Execution Order

1. Q4 manifest and base-pack contract, then the router download.
2. App shell: auth screen, session, and the five wireframe screens with
   a fake engine.
3. Local threads and on-device text generation behind the engine.
4. Model status, measured storage, download, reinstall, and cache.
5. Plan comparison, upgrade, and the Premium switch. On device uses the
   LoRA pack and local files. Digital Brain uses cloud chat with RAG.
6. Premium merge-and-quantize pack when an adapter is present.
7. Tests for the app gates, the export manifest, and the router file.
8. `output/` diagrams and justificacion.
