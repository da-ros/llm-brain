"""User registration and login."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.auth import create_access_token, hash_password, verify_password
from apps.api.store import DuplicateEmailError, store

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    subscription_tier: Literal["free", "premium"] = "free"


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    subscription_tier: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    subscription_tier: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> RegisterResponse:
    try:
        user = store.create_user(
            email=body.email,
            password_hash=hash_password(body.password),
            subscription_tier=body.subscription_tier,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    return RegisterResponse(
        user_id=user.user_id,
        email=user.email,
        subscription_tier=user.subscription_tier,
    )


@router.post("/login")
def login(body: LoginRequest) -> LoginResponse:
    user = store.get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user.user_id, user.subscription_tier)
    return LoginResponse(
        access_token=token,
        user_id=user.user_id,
        subscription_tier=user.subscription_tier,
    )
