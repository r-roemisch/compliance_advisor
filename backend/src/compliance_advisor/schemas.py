"""Request and response shapes of the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .profile import FirmProfile


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    model: str | None = None  # an id from config/models.yaml; default: the first
    top_k: int | None = Field(default=None, ge=1, le=20)
    strategy: Literal["vector", "hybrid"] | None = None  # Search Strategy; default from settings
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


class TraceHit(BaseModel):
    passage_id: str
    provision: str
    short_title: str = ""
    score: float | None = None  # cosine similarity
    rank: int | None = None  # position in the keyword ranking


class Trace(BaseModel):
    """The Answer Trace (CONTEXT.md): every step from question to answer, stored with it."""

    strategy: str
    named: list[str] = []  # Provisions the question named, looked up directly
    named_hits: list[TraceHit] = []
    vector: list[TraceHit] = []  # candidates of the vector search, best first
    keyword: list[TraceHit] = []  # candidates of the keyword search (hybrid only)
    merged: list[str] = []  # passage ids after rank fusion (hybrid only)
    max_per_source: int = 0
    capped_out: int = 0  # candidates the per-Source cap held back
    found_by: dict[str, str] = {}  # final passage id -> named | vector | keyword | both
    seconds: dict[str, float] = {}  # search, answer (model and Rule Checks), total


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
    strategy: str = "vector"  # the Search Strategy; answers stored before it existed used vector
    usage: Usage
    disclaimer: str
    trace: Trace | None = None  # missing on answers stored before the Answer Trace existed
    refusal: str | None = None  # manipulation | off_topic when the Pre-Check refused the question


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class KeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProfileUpdate(BaseModel):
    profile: FirmProfile | None = None


class TimelineRequest(BaseModel):
    profile: FirmProfile | None = None
    upcoming_only: bool = False


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
