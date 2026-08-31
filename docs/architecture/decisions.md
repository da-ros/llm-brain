# Architecture Decisions — llm-brain

This document records architectural decisions and deviations from the original
design (anteproyecto and C4 diagrams). Each decision includes the rationale
and any implications for the thesis defense.

## Decision 1: Multi-tenant from MVP (not single-tenant)

**Original (anteproyecto)**: Single-tenant, 1 user.

**Decision**: Multi-tenant from MVP with JWT authentication and per-user data isolation.

**Rationale**:
- Real-world applications require multi-user support
- The anteproyecto mentions "un usuario" referring to the data inputter for fine-tuning, not the platform limit
- Multi-tenant architecture is more realistic and defensible

**Implications**:
- JWT + bcrypt authentication required
- All data queries include user_id filter
- Subscription tiers (free/premium) per user
- Updated C4 diagrams to reflect multi-tenant labels

## Decision 2: AWS Bedrock for cloud LLM (not OpenRouter)

**Original (anteproyecto)**: OpenRouter for cloud LLM.

**Decision**: AWS Bedrock for cloud inference and fine-tuning.

**Rationale**:
- Managed service, no infrastructure
- Native LoRA fine-tuning support
- Same provider for training and inference
- Free tier 750h/mes

**Implications**:
- Updated .env.example with AWS credentials
- BedrockProvider implements LLMProvider protocol
- Fine-tuning pipeline will use Bedrock

## Decision 3: llama.rn for on-device (not ollama)

**Original (anteproyecto)**: ollama for on-device inference.

**Decision**: llama.rn for mobile on-device inference.

**Rationale**:
- Native React Native bindings
- GGUF model format (quantized, efficient)
- 18-25 tok/s on modern phones
- Free tier requires no server

**Implications**:
- Updated mobile component diagram
- LocalProvider implements LLMProvider protocol
- Model downloaded on first launch

## Decision 4: JWT authentication (not basic auth)

**Original (anteproyecto)**: Basic authentication.

**Decision**: JWT + bcrypt for user authentication.

**Rationale**:
- Stateless authentication (no session storage)
- Per-user data isolation via user_id in token
- Industry standard for multi-tenant APIs
- Supports subscription tier in token

**Implications**:
- Updated spec.md with JWT requirements
- Auth dependency in FastAPI
- Token validation on each request

## Decision 5: Frame 10 (Mobile App) as dedicated frame

**Original**: Mobile app was unassigned.

**Decision**: Create Frame 10 for React Native mobile app.

**Rationale**:
- llama.rn integration requires dedicated mobile app
- Free tier delivery requires mobile app
- Thesis objectives OE1 and OE4 both require mobile component

**Implications**:
- Created objective-10-mobile-app directory
- Added to config.yaml with dependencies on Frame 4
- Execution order: after Frame 4 (LLM Cloud + On-Device)

## Decision 6: i18n support (English UI, Spanish documents)

**Original (anteproyecto)**: English UI, Spanish document support.

**Decision**: Implement i18n with language files for future localization.

**Rationale**:
- Anteproyecto specifies English UI
- Spanish document support is automatic (LLM infers)
- i18n architecture allows future language additions

**Implications**:
- Will use react-i18next for React/React Native
- Language files in `src/locales/`
- Spanish document support via LLM inference
