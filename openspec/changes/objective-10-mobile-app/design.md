## Context

The mobile app is a React Native application that serves as the primary client for
llm-brain. It supports both free-tier (on-device LLM via llama.rn) and premium-tier
(cloud LLM via AWS Bedrock + RAG) experiences. Authentication is JWT-based, matching
the backend API.

## Goals / Non-Goals

**Goals:**
- React Native with TypeScript for cross-platform (iOS + Android)
- JWT authentication with secure token storage
- llama.rn integration for on-device inference (Llama 3.2 3B Q4_K_M)
- API client for backend communication (premium features)
- Navigation with auth guards
- File handling (image/PDF pickers)
- Subscription tier UI (free/premium feature gates)

**Non-Goals:**
- App Store publishing (MVP only)
- Push notifications
- Offline-first data sync
- Biometric authentication

## Architecture Decisions

### 1. Framework: React Native (not Flutter, not Expo)

**Decision**: React Native with TypeScript, bare workflow (not Expo managed).

**Rationale**:
- llama.rn has native bindings for React Native (C++ bridge)
- Expo managed workflow limits native module access
- Team familiarity with React ecosystem
- Code sharing with web app (React) via shared types

### 2. State Management: Zustand (not Redux, not Context API)

**Decision**: Zustand for global state management.

**Rationale**:
- Minimal boilerplate compared to Redux
- Built-in TypeScript support
- No providers needed (simpler navigation)
- Works well with React Navigation

### 3. Navigation: React Navigation 6

**Decision**: Stack Navigator + Tab Navigator with auth guards.

**Rationale**:
- Industry standard for React Native
- Deep linking support (future)
- Auth flow via conditional rendering

### 4. Secure Storage: react-native-keychain

**Decision**: Store JWT tokens in iOS Keychain / Android Keystore.

**Rationale**:
- OS-level encryption (not just AsyncStorage)
- Biometric protection available (future)
- Industry standard for credential storage

### 5. LLM Integration: llama.rn

**Decision**: llama.rn for on-device inference, loaded via GGUF model files.

**Rationale**:
- Native C++ backend via llama.cpp
- GPU/NPU acceleration on modern phones
- 18-25 tok/s on mid-range devices
- Free tier requires no server dependency

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| llama.rn model size (~2GB) | Lazy download on first use, cache manager |
| iOS/Android native module differences | Abstract platform services layer |
| Token expiry handling | Interceptor refresh pattern |
| Large file uploads on mobile | Compress before upload, chunked transfer |

## Decisions Made

- JWT stored in Keychain/Keystore (not AsyncStorage)
- llama.rn model downloaded on first launch (not bundled)
- API base URL configurable via .env (dev/prod switching)
- Subscription tier checked client-side for UI gating, enforced server-side
