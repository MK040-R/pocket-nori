from pydantic import BaseModel, Field
from typing import Optional


class Topic(BaseModel):
    label: str = Field(description="Short descriptive label for the topic")
    summary: str = Field(description="1-2 sentence summary of what was discussed")
    status: str = Field(description="open or resolved")
    key_quotes: list[str] = Field(default=[], description="Up to 2 verbatim quotes from transcript")


class TopicList(BaseModel):
    topics: list[Topic]


class Commitment(BaseModel):
    text: str = Field(description="Exact commitment text, as stated or closely paraphrased")
    owner: str = Field(description="Person who made the commitment")
    due_date: Optional[str] = Field(default=None, description="Due date if mentioned, ISO format")
    status: str = Field(default="open", description="open or resolved")


class CommitmentExtraction(BaseModel):
    commitments: list[Commitment]


class Entity(BaseModel):
    name: str
    type: str = Field(description="person, project, company, or product")
    mentions: int = Field(description="Number of times mentioned in transcript")


class EntityList(BaseModel):
    entities: list[Entity]
