"""Chat threads. A thread is a session, not a weekly-focus object."""

from __future__ import annotations

from auth import verify_token
from brain_client import create_chat, list_chats, list_turns
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("")
async def get_chats(request: Request, user: dict = Depends(verify_token)):
    return {"chats": await list_chats(user["user_id"], correlation_id=request.state.correlation_id)}


@router.post("", status_code=201)
async def post_chat(request: Request, user: dict = Depends(verify_token)):
    return await create_chat(user["user_id"], correlation_id=request.state.correlation_id)


@router.get("/{chat_id}/turns")
async def get_turns(chat_id: str, request: Request, user: dict = Depends(verify_token)):
    turns = await list_turns(user["user_id"], chat_id, correlation_id=request.state.correlation_id)
    if turns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return {"turns": turns}
