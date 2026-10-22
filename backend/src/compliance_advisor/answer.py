"""Answering: retrieve, build the prompt, call the Answer Model, assemble the response."""

import logging
import re
import time

import openai
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from sqlalchemy.exc import SQLAlchemyError

from .prompt import DISCLAIMER, build_messages
from .retriever import Retriever
from .schemas import AskResponse, PassageOut, Usage
from .settings import OPENROUTER_BASE_URL, Settings

log = logging.getLogger("compliance_advisor.ask")

_BRACKETS = re.compile(r"\[([^\[\]]*)\]")  # innermost [...] groups


class UpstreamError(RuntimeError):
    """OpenRouter (embeddings or Answer Model) failed or did not respond."""


class DatabaseError(RuntimeError):
    """Postgres is not reachable."""


def get_answer_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.answer_model,
        api_key=settings.require_api_key(),
        base_url=OPENROUTER_BASE_URL,
        timeout=90,
        max_retries=1,
        default_headers={"X-Title": "Compliance Advisor"},
    )


def cited_numbers(answer: str, available: int) -> list[int]:
    """The passage numbers the answer cites, in order, ignoring numbers it was not given.

    Handles "[1]", "[1, 2]", "[1; 3]" and "[1, Art. 32 Abs. 1]": inside a bracket, every part
    between commas or semicolons that is a bare number counts.
    """
    found: list[int] = []
    for group in _BRACKETS.findall(answer):
        for part in re.split(r"[,;]", group):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= available and int(part) not in found:
                found.append(int(part))
    return found


class AnswerService:
    def __init__(self, retriever: Retriever, model: BaseChatModel, model_id: str, top_k: int):
        self.retriever = retriever
        self.model = model
        self.model_id = model_id
        self.top_k = top_k

    def ask(self, question: str, top_k: int | None = None) -> AskResponse:
        started = time.monotonic()
        try:
            passages = self.retriever.retrieve(question, top_k or self.top_k)
        except openai.APIError as e:
            raise UpstreamError(f"the embedding service did not respond: {e}") from e
        except SQLAlchemyError as e:
            raise DatabaseError("the database is not reachable") from e
        try:
            reply = self.model.invoke(build_messages(question, passages))
        except openai.APIError as e:
            raise UpstreamError(f"the answer model did not respond: {e}") from e

        answer = reply.content if isinstance(reply.content, str) else str(reply.content)
        usage = Usage(**{k: (reply.usage_metadata or {}).get(k, 0) for k in Usage.model_fields})
        response = AskResponse(
            question=question,
            answer=answer,
            passages=[
                PassageOut(
                    n=n,
                    score=hit.score,
                    text=hit.document.page_content,
                    **{
                        k: v
                        for k, v in hit.document.metadata.items()
                        if k in PassageOut.model_fields and k not in ("n", "score", "text")
                    },
                )
                for n, hit in enumerate(passages, start=1)
            ],
            cited=cited_numbers(answer, len(passages)),
            model=self.model_id,
            usage=usage,
            disclaimer=DISCLAIMER,
        )
        log.info(
            "ask duration=%.1fs model=%s input_tokens=%d output_tokens=%d passages=%s cited=%s",
            time.monotonic() - started,
            self.model_id,
            usage.input_tokens,
            usage.output_tokens,
            ",".join(p.passage_id for p in response.passages),
            response.cited,
        )
        return response
