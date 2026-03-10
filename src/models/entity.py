from __future__ import annotations

import uuid
import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EntityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    name: str
    type: Literal["person", "project", "company", "product"] = Field(
        description="person, project, company, or product"
    )
    mentions: int = Field(description="Number of times mentioned in transcript")
    segment_ids: list[uuid.UUID] = Field(default_factory=list)


class EntityCreate(EntityBase):
    pass


class Entity(EntityBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
