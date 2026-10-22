"""Answering: pre-check, retrieve, one tool round, call the Answer Model, assemble the response."""

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import date

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .precheck import redact
from .profile import FirmProfile
from .prompt import DISCLAIMER, build_messages
from .retriever import Retriever
from .schemas import AskResponse, PassageOut, ToolRun, Usage

log = logging.getLogger("compliance_advisor.ask")

_BRACKETS = re.compile(r"\[([^\[\]]*)\]")  # innermost [...] groups
MAX_TOOL_CALLS = 4


class UpstreamError(RuntimeError):
    """OpenRouter (embeddings or Answer Model) failed or did not respond."""


class DatabaseError(RuntimeError):
    """Postgres is not reachable."""


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


def _usage(*replies) -> Usage:
    total = Usage()
    for reply in replies:
        meta = getattr(reply, "usage_metadata", None) or {}
        total.input_tokens += meta.get("input_tokens", 0)
        total.output_tokens += meta.get("output_tokens", 0)
        reported = (getattr(reply, "response_metadata", None) or {}).get("token_usage") or {}
        total.cost_usd += float(reported.get("cost") or 0.0)
    total.cost_usd = round(total.cost_usd, 6)
    return total


_COVERAGE = re.compile(r"\s*[*_]*\s*Coverage:\s*(full|partial|none)\W*\s*$", re.IGNORECASE)


def split_coverage(answer: str) -> tuple[str, str]:
    """Removes the model's closing "Coverage: …" line and returns it separately."""
    match = _COVERAGE.search(answer)
    if not match:
        return answer.strip(), "unknown"
    return answer[: match.start()].rstrip(), match.group(1).lower()


Stage = Callable[[str, dict], None]


def _quiet(stage: str, data: dict) -> None:
    pass


def _text(reply) -> str:
    return reply.content if isinstance(reply.content, str) else str(reply.content)


ToolFactory = Callable[[FirmProfile | None, date], list[StructuredTool]]


class AnswerService:
    def __init__(
        self,
        retriever: Retriever,
        models: BaseChatModel | dict[str, BaseChatModel],
        model_id: str,
        top_k: int,
        tools: ToolFactory | None = None,
    ):
        """`models` maps model ids to chat models; `model_id` is the default."""
        self.retriever = retriever
        self.models = models if isinstance(models, dict) else {model_id: models}
        self.model_id = model_id
        self.top_k = top_k
        self.tools = tools

    def _tool_round(self, model, messages, profile: FirmProfile | None, on_stage: Stage):
        """One round: the model may call tools once, then answers without further tool calls.
        Returns the final reply, all replies (for token usage) and the tool runs."""
        tools = self.tools(profile, date.today()) if self.tools else []
        on_stage("model", {})
        if not tools:
            reply = model.invoke(messages)
            return reply, [reply], []
        first = model.bind_tools(tools).invoke(messages)
        if not getattr(first, "tool_calls", None):
            return first, [first], []
        on_stage("tools", {"tools": [call["name"] for call in first.tool_calls[:MAX_TOOL_CALLS]]})
        by_name = {tool.name: tool for tool in tools}
        runs: list[ToolRun] = []
        follow_up = list(messages) + [first]
        for call in first.tool_calls[:MAX_TOOL_CALLS]:
            tool = by_name.get(call["name"])
            try:
                output = (
                    tool.invoke(call["args"]) if tool else json.dumps({"error": "unknown tool"})
                )
            except (ValidationError, ValueError, TypeError) as e:
                output = json.dumps({"error": f"invalid arguments: {e}"})
            runs.append(
                ToolRun(name=call["name"], arguments=call["args"], result=json.loads(output))
            )
            follow_up.append(ToolMessage(content=output, tool_call_id=call["id"]))
        for call in first.tool_calls[MAX_TOOL_CALLS:]:
            follow_up.append(
                ToolMessage(content='{"error": "too many tool calls"}', tool_call_id=call["id"])
            )
        on_stage("writing", {})
        final = model.bind_tools(tools, tool_choice="none").invoke(follow_up)
        return final, [first, final], runs

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        profile: FirmProfile | None = None,
        model_id: str | None = None,
        on_stage: Stage = _quiet,
    ) -> AskResponse:
        started = time.monotonic()
        model_id = model_id or self.model_id
        if model_id not in self.models:
            raise ValueError(f"unknown model {model_id!r}; choose one of {', '.join(self.models)}")
        question, redactions = redact(question)
        on_stage("search", {"redactions": redactions})
        try:
            passages = self.retriever.retrieve(question, top_k or self.top_k)
        except openai.APIError as e:
            raise UpstreamError(f"the embedding service did not respond: {e}") from e
        except SQLAlchemyError as e:
            raise DatabaseError("the database is not reachable") from e
        messages = build_messages(question, passages, profile.describe() if profile else "")
        try:
            reply, replies, runs = self._tool_round(
                self.models[model_id], messages, profile, on_stage
            )
        except openai.APIError as e:
            raise UpstreamError(f"the answer model did not respond: {e}") from e

        answer, coverage = split_coverage(_text(reply))
        usage = _usage(*replies)
        response = AskResponse(
            question=question,
            redactions=redactions,
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
            tools=runs,
            coverage=coverage,
            model=model_id,
            usage=usage,
            disclaimer=DISCLAIMER,
        )
        log.info(
            "ask duration=%.1fs model=%s input_tokens=%d output_tokens=%d tools=%s redactions=%s "
            "passages=%s cited=%s",
            time.monotonic() - started,
            model_id,
            usage.input_tokens,
            usage.output_tokens,
            [r.name for r in runs],
            redactions,
            ",".join(p.passage_id for p in response.passages),
            response.cited,
        )
        return response
