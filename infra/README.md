# Infra

Docker Compose and the root `Dockerfile` live at the repository root.

- Local MVP: `docker compose up --build`
- Frame 1 API image: `Dockerfile` → `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000`
- AWS ECS Fargate + API Gateway: future / out of scope
