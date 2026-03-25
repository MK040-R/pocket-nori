from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TopicArcBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    topic_id: uuid.UUID
    topic_node_id: uuid.UUID | None = Field(default=None, alias="cluster_id")
    conversation_ids: list[uuid.UUID]
    summary: str
    trend: Literal["growing", "stable", "resolved"]


class TopicArcCreate(TopicArcBase):
    pass


class TopicArc(TopicArcBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
