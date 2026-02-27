"""
Chat endpoint — called by the Frontend with X-User-ID header.
Returns a Server-Sent Events stream with thinking steps and the final UI payload.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.chat import ChatRequest
from app.services.orchestrator import orchestrate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Process a user chat message and stream the Agent's response.

    The Frontend passes the authenticated user's uid in the X-User-ID header.
    The Agent trusts this header — JWT verification is the Backend's responsibility.

    Streams Server-Sent Events:
      {"event": "thinking", "data": {"step": "..."}}  — reasoning progress
      {"event": "result",   "data": <GenerativeUIPayload>}  — final UI payload
    """
    # Validate uid format
    try:
        uid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format — must be UUID v4",
            headers={"X-Error-Code": "MISSING_USER_ID"},
        )

    return StreamingResponse(
        orchestrate(uid=uid, message=body.message, history=body.conversation_history, db=db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
