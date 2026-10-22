"""Request and response shapes of the API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .profile import FirmProfile


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    model: str | None = None  # an id from config/models.yaml; default: the first
    top_k: int | None = Field(default=None, ge=1, le=20)
    profile: FirmProfile | None = None

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
    url: str  # the Source's reading page
    provision: str = ""  # "Art. 17 DORA", "§ 10 GwG"; empty for the naive baseline index
    provision_title: str = ""
    link: str = ""  # opens exactly this Provision in the official text
    legal_status: str = "in_force"
    version: str = ""
    as_of: str = ""  # date the app's copy of the Source was downloaded
    score: float
    text: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0  # as reported by OpenRouter


class ToolRun(BaseModel):
    name: str
    arguments: dict
    result: dict


class AskResponse(BaseModel):
    id: str | None = None  # set when stored in the audit trail
    created_at: datetime | None = None
    question: str  # as sent to the model, after the pre-check
    redactions: list[str] = []  # kinds of personal data the pre-check removed
    answer: str
    passages: list[PassageOut]
    cited: list[int]
    tools: list[ToolRun] = []
    coverage: str = "full"  # full | partial | none: how far the Passages answer the question
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
    legal_status: str
    version: str
    milestones: list[dict]
    as_of: str
    passages: int


class SourcesResponse(BaseModel):
    sources: list[SourceOut]
    disclaimer: str
