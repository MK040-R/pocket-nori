from __future__ import annotations

import uuid
import datetime

from pydantic import BaseModel, ConfigDict


class ConversationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    source: str
    meeting_date: datetime.datetime
    duration_seconds: int | None = None
    calendar_event_id: str | None = None


class ConversationCreate(ConversationBase):
    pass


class Conversation(ConversationBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
