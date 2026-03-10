from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CommitmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    text: str = Field(description="Exact commitment text, as stated or closely paraphrased")
    owner: str = Field(description="Person who made the commitment")
    due_date: datetime.datetime | None = None
    status: Literal["open", "done", "cancelled"] = Field(
        default="open", description="open, done, or cancelled"
    )
    segment_ids: list[uuid.UUID] = Field(default_factory=list)


class CommitmentCreate(CommitmentBase):
    pass


class Commitment(CommitmentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
