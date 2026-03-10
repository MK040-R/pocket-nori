from __future__ import annotations

import uuid
import datetime

from pydantic import BaseModel, ConfigDict


class TranscriptSegmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    speaker_id: str
    speaker_name: str | None = None
    start_ms: int
    end_ms: int
    text: str
    embedding: list[float] | None = None


class TranscriptSegmentCreate(TranscriptSegmentBase):
    pass


class TranscriptSegment(TranscriptSegmentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
