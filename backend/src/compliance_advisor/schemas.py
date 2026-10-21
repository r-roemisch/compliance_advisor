"""Request and response shapes of the API."""

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("question", mode="before")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class PassageOut(BaseModel):
    n: int
    passage_id: str
    source_id: str
    source_title: str
    short_title: str
    regime: str
    layer: str
    issuer: str
    language: str
    url: str
    score: float
    text: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AskResponse(BaseModel):
    question: str
    answer: str
    passages: list[PassageOut]
    cited: list[int]
    model: str
    usage: Usage
    disclaimer: str


class SourceOut(BaseModel):
    id: str
    title: str
    short_title: str
    regime: str
    layer: str
    issuer: str
    language: str
    url: str
    passages: int


class SourcesResponse(BaseModel):
    sources: list[SourceOut]
    disclaimer: str
