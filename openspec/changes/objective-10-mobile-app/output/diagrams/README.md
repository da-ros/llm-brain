# Frame 10 — Mobile app diagrams

> **Current runtime.** This file keeps the decision text of this frame. Before citing it as the running system, read `docs/architecture/current-runtime.md`.


Solid arrow: a call or a write. The head is on the callee. `startArrow=none`, `endArrow=classic`.

Dashed arrow: a response. The head is on the caller.

Green is this frame (the iPhone, the on-device engine, the Q4 export and packs). Blue is an earlier frame (API Router, LLM, RAG, the Fine-Tune adapter directory).

A red box is an error or a refusal. It has no outgoing edge.

The phone's only server edge is the API Router. There is no edge from the phone to ports 8001–8008. There is no edge from the export into the LLM container. There is no Apple sign-in, Google sign-in, password reset, microphone, Kafka, or `POST /api/upload`.

## mobile-architecture.drawio

| From | To | Line | Meaning |
|------|----|------|---------|
| iPhone app | OnDeviceEngine | solid green | Free, and Premium with the switch On device. Head on the engine. |
| iPhone app | API Router | solid green | The phone's only server edge: auth, plan, pack download, Digital Brain chat. Head on the router. |
| API Router | iPhone app | dashed blue | JWT and pack bytes. Head on the phone. |
| API Router | LLM :8003 | solid blue | Digital Brain only. Head on the LLM. The phone does not take this hop. |
| API Router | RAG :8002 | solid blue | Digital Brain retrieval. Head on RAG. |
| Adapter directory | export script | solid blue | That user's LoRA adapter. Head on the export. |
| export script | Q4 packs | solid green | Manifest and weight file. Head on the pack. |
| API Router | Q4 packs | solid blue | Read the caller's ready pack. Head on the files. |

The red note has no edges.

## mobile-dataflow.drawio

| From | To | Line | Meaning |
|------|----|------|---------|
| Auth | API Router | solid green | `POST /api/auth/signin` or `POST /api/auth/signup`. Head on the router. |
| API Router | Auth | dashed blue | JWT. Head on Auth, the caller. |
| Auth | Keychain | solid green | Store `access_token` and `user`. Head on the Keychain. |
| API Router | 401 | dashed red | Bad credentials. The red box has no outgoing edge. |
| On-device question | OnDeviceEngine | solid green | Local prompt, including up to five extracted files. Head on the engine. No router on this path. |
| OnDeviceEngine | On-device question | dashed green | The reply. Head on the question, the caller. |
| On-device question | Sixth file refused | solid red | The red box has no outgoing edge. |
| On-device question | On-device image refused | solid red | The red box has no outgoing edge. |
| On-device question | No base pack | solid red | The phone asks for a download. There is no edge to `POST /api/chat`. |
| Reinstall Model | API Router | solid green | `GET /api/models/on-device`, then `GET /api/models/on-device/file`. Head on the router. |
| API Router | Reinstall Model | dashed blue | Pack bytes. Head on Reinstall, the caller. |
| Reinstall Model | sha256 on the phone | solid green | Verify before replacing. Head on the checksum. |
| sha256 on the phone | Swap installed pack | solid green | Checksum matches. Head on the swap. |
| sha256 on the phone | Keep the old pack | dashed red | Checksum mismatch. The red box has no outgoing edge. |
| API Router | 404 | dashed red | Premium pack is not ready. The base file and another user's file are not sent. No outgoing edge. |
| Premium switch | OnDeviceEngine | solid green | On device: that user's LoRA Q4, or the base Q4 when the personal pack is missing. Head on the engine. |
| Premium switch | POST /api/chats | solid green | Digital Brain, first cloud question in the thread. Head on the chat create. |
| POST /api/chats | POST /api/chat | solid green | Reuse the id as `session_id`. Head on the chat call. |
| POST /api/chat | API Router | solid green | `use_rag: true` and up to five attachments. Head on the router. Not `POST /api/upload`. |
| API Router | POST /api/chat | dashed blue | Cloud reply. Head on the chat call, the caller. |
| API Router | RAG :8002 | solid blue | Digital Brain retrieval. Head on RAG. |
| API Router | LLM :8003 | solid blue | Digital Brain generation. Head on the LLM. |
