# Encefalus web

Copied from [da-ros/encefalus-your-cognitive-os](https://github.com/da-ros/encefalus-your-cognitive-os) at `1885e11`. In this repo it lives in `apps/web/`.

```bash
cd apps/web
npm install
npm run dev
```

`vite dev` proxies `/api` to `http://localhost:8000`. After `npm run build`, `docker compose --profile web up web` serves `dist/` and proxies `/api` through `nginx.conf`.

# Encefalus: Your Cognitive OS

I’m building **AI-Augmented Digital Brain is a consumer web application that builds a persistent personal memory from a user’s documents, notes and life data, then combines RAG, personalized LLM inference, agentic workflows and explainable reasoning to help the user remember, cross-reference information, discover patterns and make better decisions. The MVP explores practical Brain–LLM symbiosis by allowing the system to learn from the user over time while preserving privacy through optional local inference.**, **
Build a responsive Premium web application called Encefalus — AI-Augmented Digital Brain. The visual language should be inspired by high-end cognitive/productivity software like Zo.computer: warm off-white backgrounds, restrained taupe/brown accents, thin borders, spacious typography, subtle shadows and a persistent left navigation. Do not copy Zo branding or exact layouts.

Encefalus is not a generic chatbot. It is a Personal LLM/OS with persistent memory, RAG, decision support, life analytics, scam detection and symbiotic model learning. The interface should communicate “cognitive operating system.”

Desktop architecture: persistent 220px left sidebar + flexible central workspace + contextual right inspector when appropriate. Navigation: Brain, Memory, Decisions, Analytics, Shield, Learning, Settings.

Use one dominant task per screen. Avoid clutter, neon AI aesthetics, excessive gradients and generic SaaS dashboard appearance. Prioritize clarity, explainability, personal context and privacy.

Memory supports documents, images, audio and video. Do not implement a knowledge-graph visualization in the MVP.


You have the wireframes attached and a reference images of how it should look


**,

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/2ad00544-3ca2-48f2-9486-741073e2cf42).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
