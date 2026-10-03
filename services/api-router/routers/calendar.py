"""Calendar notes. These are not ingested into document memory."""

from __future__ import annotations

from datetime import date

from auth import require_premium
from brain_client import list_notes, put_note
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class NoteBody(BaseModel):
    note: str = Field(default="", max_length=2000)


def _day(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date must be YYYY-MM-DD",
        ) from exc


@router.get("")
async def get_notes(
    request: Request,
    start: str = Query(...),
    end: str = Query(...),
    user: dict = Depends(require_premium),
):
    start_day = _day(start)
    end_day = _day(end)
    if start_day > end_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start must be on or before end",
        )
    notes = await list_notes(
        user["user_id"], start_day, end_day, correlation_id=request.state.correlation_id
    )
    return {"notes": notes}


@router.put("/{day}")
async def save_note(
    day: str,
    body: NoteBody,
    request: Request,
    user: dict = Depends(require_premium),
):
    await put_note(
        user["user_id"], _day(day), body.note, correlation_id=request.state.correlation_id
    )
    return {"date": _day(day), "saved": bool(body.note.strip())}
