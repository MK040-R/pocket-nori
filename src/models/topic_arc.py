from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TopicArcBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: uuid.UUID
    cluster_id: uuid.UUID | None = None
    conversation_ids: list[uuid.UUID]
    summary: str
    trend: Literal["growing", "stable", "resolved"]


class TopicArcCreate(TopicArcBase):
    pass


class TopicArc(TopicArcBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
