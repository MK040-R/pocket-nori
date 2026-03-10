from __future__ import annotations

import uuid
import datetime

from pydantic import BaseModel, ConfigDict


class BriefBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    calendar_event_id: str | None = None
    topic_arc_ids: list[uuid.UUID]
    commitment_ids: list[uuid.UUID]
    connection_ids: list[uuid.UUID]
    content: str
    generated_at: datetime.datetime


class BriefCreate(BriefBase):
    pass


class Brief(BriefBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
