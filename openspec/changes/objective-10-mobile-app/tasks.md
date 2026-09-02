## Tasks

### A. Project Setup

- [ ] A.1 Initialize React Native project with TypeScript template
      — `npx react-native init llm-brain-mobile --template react-native-template-typescript`
- [ ] A.2 Configure ESLint + Prettier (match web app conventions)
- [ ] A.3 Set up project structure: `src/screens/`, `src/components/`, `src/services/`, `src/store/`, `src/types/`
- [ ] A.4 Add dependencies: zustand, react-navigation, axios, react-native-keychain, llama-rn

### B. Authentication

- [ ] B.1 Implement API client with Axios (`src/services/api.ts`)
      — Base URL from env, JWT interceptor, token refresh pattern
- [ ] B.2 Implement auth store (`src/store/authStore.ts`)
      — login(), register(), logout(), token management via Keychain
- [ ] B.3 Create LoginScreen with email/password form
- [ ] B.4 Create RegisterScreen with email/password/confirm form
- [ ] B.5 Implement auth guard in navigation (conditional Stack rendering)

### C. Navigation

- [ ] C.1 Set up React Navigation with Stack Navigator (Auth + Main stacks)
- [ ] C.2 Create Tab Navigator for main screens (Chat, Upload, Profile)
- [ ] C.3 Implement deep link configuration (future-ready)

### D. LLM Integration (Free Tier)

- [ ] D.1 Integrate llama.rn binding (`src/services/llm.ts`)
      — loadModel(), infer(), unloadModel()
- [ ] D.2 Implement model downloader with progress tracking
      — Download Llama 3.2 3B Q4_K_M GGUF on first launch
- [ ] D.3 Create ChatScreen with local inference mode
- [ ] D.4 Add token count display and generation speed metrics

### E. Premium Features (Cloud)

- [ ] E.1 Implement cloud chat endpoint (`POST /api/chat`)
      — Send prompt, receive streaming response
- [ ] E.2 Implement file upload (`POST /api/upload`)
      — Image picker, PDF picker, compression, upload with progress
- [ ] E.3 Create UploadScreen with file selection and upload flow
- [ ] E.4 Implement subscription tier check and UI gating

### F. UI/UX

- [ ] F.1 Design and implement ChatScreen (message list, input, send)
- [ ] F.2 Design and implement ProfileScreen (user info, subscription status)
- [ ] F.3 Add loading states, error handling, retry logic
- [ ] F.4 Implement offline detection and fallback messaging

### G. Security

- [ ] G.1 Store JWT in Keychain (iOS) / Keystore (Android) via react-native-keychain
- [ ] G.2 Implement token expiry detection and automatic logout
- [ ] G.3 Validate server certificate (no self-signed in production)

### H. Testing

- [ ] H.1 Unit tests for auth store (login, register, logout flows)
- [ ] H.2 Unit tests for API client (error handling, token injection)
- [ ] H.3 Integration test for navigation flow (login → main tabs)
- [ ] H.4 Manual test: llama.rn model load + inference on device
