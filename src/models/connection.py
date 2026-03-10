from __future__ import annotations

import uuid
import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ConnectionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    linked_ids: list[uuid.UUID]
    linked_type: Literal["conversation", "topic"]
    summary: str

    @field_validator("linked_ids")
    @classmethod
    def linked_ids_min_two(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) < 2:
            raise ValueError("linked_ids must contain at least 2 items")
        return v


class ConnectionCreate(ConnectionBase):
    pass


class Connection(ConnectionBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
