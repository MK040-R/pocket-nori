from __future__ import annotations

import uuid
import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TopicBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    label: str = Field(description="Short descriptive label for the topic")
    summary: str = Field(description="1-2 sentence summary of what was discussed")
    status: Literal["open", "resolved"] = Field(description="open or resolved")
    key_quotes: list[str] = Field(default_factory=list, description="Up to 2 verbatim quotes from transcript")
    segment_ids: list[uuid.UUID] = Field(default_factory=list)


class TopicCreate(TopicBase):
    pass


class Topic(TopicBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
