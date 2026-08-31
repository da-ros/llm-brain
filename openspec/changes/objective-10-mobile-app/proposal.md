## Proposal: Mobile App (React Native)

### Context

The llm-brain platform requires a mobile client to deliver the free-tier experience
(on-device LLM via llama.rn) and premium features (cloud LLM + RAG) to users on
iOS and Android. The mobile app is the primary touchpoint for the majority of users
who interact with personal knowledge management on their phones.

### Why

1. **Free-tier delivery**: llama.rn runs on-device — only a mobile app can deliver
   the free-tier LLM experience without a server.
2. **User reach**: Mobile-first market; most personal document interactions happen
   on phones (photos, PDFs, receipts).
3. **Thesis objective**: OE1 (architecture) and OE4 (LLM on-device) both require
   a mobile component as the runtime for llama.rn.

### Deliverables

- React Native project structure with TypeScript
- JWT authentication flow (register, login, token storage)
- Navigation architecture (Stack + Tab navigators)
- llama.rn integration for on-device inference (free tier)
- API client for backend communication (premium tier)
- Secure token storage (react-native-keychain)
- File handling (image picker, PDF metadata)
- Subscription tier UI (free/premium gates)

### Non-Deliverables (out of scope)

- App Store / Play Store publishing
- Push notifications
- Offline-first data sync
- Biometric authentication
- Deep linking (initial version)

### References

- Anteproyecto: Objetivo Específico 1 (architecture) + OE4 (LLM on-device)
- Depends on: Frame 4 (LLM Cloud Fine-Tune + On-Device)
