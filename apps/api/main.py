"""FastAPI application skeleton for the platform foundation."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.routers import auth, health, profile


def create_app() -> FastAPI:
    """Build the FastAPI app. Validates configuration at import/startup."""
    settings = get_settings()

    application = FastAPI(
        title="llm-brain",
        description="AI-Augmented Digital Brain — platform foundation",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(profile.router)
    application.state.settings = settings
    return application


app = create_app()
