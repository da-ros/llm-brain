# Encefalus MVP interface

## What I’ll build

- A responsive premium application shell with a persistent 220px desktop sidebar, mobile drawer navigation, central workspace, and contextual right inspector.
- Seven working screens: Brain, Memory, Decisions, Analytics, Shield, Learning, and Settings.
- A warm off-white, taupe, and brown design system with thin borders, restrained shadows, compact controls, and spacious typography matching the supplied references without copying their branding.

## Screen behavior

- **Brain:** Personal-memory-aware conversation, cited memory cards, evidence/assumptions inspector, mode selection, attachments, shortcuts, feedback, and new-chat controls.
- **Memory:** Search, media filters, selectable memory table, document preview, processing states, and an upload dialog for documents, images, audio, and video.
- **Decisions:** Editable premises, scenario simulation, comparison cards, assumptions, and cited memories.
- **Analytics:** Date-range control, key metrics, interactive data-point inspection, the two requested correlations, and careful non-causal insight copy.
- **Shield:** Suspicious-content input, source selection, upload control, risk result, evidence, and recent scan history.
- **Learning:** Personalization metrics, explicit training lifecycle, learned preferences, and manual fine-tuning action.
- **Settings:** Account, privacy controls, local/cloud inference choice, system health, storage, export, and destructive-data confirmation.

## Technical details

- Use TanStack Router with one route per screen and route-specific metadata.
- Reuse the existing interface controls and semantic design tokens; add only focused shared Encefalus components.
- Keep the MVP frontend-only with realistic seeded content and local interactive state; persistence, real AI, RAG, uploads, and authentication are not connected in this pass.
- Validate desktop and mobile layouts in the running preview and confirm navigation and primary interactions work.
