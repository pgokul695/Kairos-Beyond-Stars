"""Pydantic schemas for the chat endpoint."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single turn in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Body for POST /chat — sent by the Frontend."""

    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[ChatMessage] = Field(default_factory=list)
