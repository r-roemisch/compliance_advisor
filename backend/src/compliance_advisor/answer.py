"""Answering: pre-check, translate the question, retrieve, one tool round, call the Answer Model
under its own system prompt, assemble the response."""

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

from .logs import prompt_failed
from .precheck import redact, screen
from .profile import FirmProfile
from .prompt import DISCLAIMER, build_messages
from .query_translation import translate
from .retriever import Retriever
from .schemas import AskResponse, PassageOut, ToolRun, Trace, Usage

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


def _usage(*replies, prices: tuple[float, float] | None = None) -> Usage:
    """Token counts and cost. Streamed replies carry no cost, so it is computed from OpenRouter's
    per-token list prices (input, output); output tokens include the model's reasoning."""
    total = Usage()
    for reply in replies:
        meta = getattr(reply, "usage_metadata", None) or {}
        input_tokens, output_tokens = meta.get("input_tokens", 0), meta.get("output_tokens", 0)
        total.input_tokens += input_tokens
        total.output_tokens += output_tokens
        reported = (getattr(reply, "response_metadata", None) or {}).get("token_usage") or {}
        cost = float(reported.get("cost") or 0.0)
        if not cost and prices:  # per reply: a streamed answer next to a priced screening call
            cost = input_tokens * prices[0] + output_tokens * prices[1]
        total.cost_usd += cost
    total.cost_usd = round(total.cost_usd, 6)
    return total


_COVERAGE = re.compile(r"\s*[*_]*\s*Coverage:\s*[*_]*\s*(full|partial|none)\W*\s*$", re.IGNORECASE)


def split_coverage(answer: str) -> tuple[str, str]:
    """Removes the model's closing "Coverage: …" line and returns it separately."""
    match = _COVERAGE.search(answer)
    if not match:
        return answer.strip(), "unknown"
    return answer[: match.start()].rstrip(), match.group(1).lower()


def format_problems(
    answer: str, coverage: str, cited: int, passages: int, finish: str | None
) -> list[str]:
    """How an answer misses the format every system prompt asks for: stopped by the provider,
    empty, without the Coverage line, or without a citation though it claims to cover the
    question."""
    problems = []
    if finish == "length":
        problems.append("cut off at the output limit")
    elif finish == "content_filter":
        problems.append("stopped by the provider's content filter")
    if not answer:
        problems.append("empty answer")
    elif coverage == "unknown":
        problems.append("no Coverage line")
    if answer and passages and not cited and coverage != "none":
        problems.append("no citation")
    return problems


Stage = Callable[[str, dict], None]

# The step a question fails in, from the last stage it reported; from the Passages on, it is the
# Answer Model's round.
_STEPS = {"precheck": "precheck", "refused": "precheck", "search": "search"}


def usage_reported(replies) -> bool:
    return any(
        ((getattr(r, "response_metadata", None) or {}).get("token_usage") or {}).get("cost")
        for r in replies
    )


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
        prices: Callable[[str], tuple[float, float] | None] | None = None,
        strategy: str = "vector",
        screeners: dict[str, BaseChatModel] | None = None,
        prompts: dict[str, str] | None = None,
        translators: dict[str, BaseChatModel] | None = None,
    ):
        """`models` maps model ids to chat models; `model_id` is the default, and `strategy` the
        default Search Strategy. `prompts` maps each model id to its own system prompt
        (config/models.yaml); without one, as in tests, the model gets the Passages and the
        question only. `screeners` and `translators` map each Answer Model id to the model that
        screens its questions (ADR 0007) and the one that translates them for the search
        (ADR 0008); without them, questions are not screened or not translated."""
        self.retriever = retriever
        self.strategy = strategy
        self.screeners = screeners or {}
        self.prompts = prompts or {}
        self.translators = translators or {}
        self.models = models if isinstance(models, dict) else {model_id: models}
        self.model_id = model_id
        self.top_k = top_k
        self.tools = tools
        self.prices = prices or (lambda model_id: None)

    @staticmethod
    def _call(runnable, messages, on_stage: Stage):
        """Calls the model; when it can stream, the answer text is passed on as it arrives and
        the "writing" step is reported the moment the first words come in."""
        if not hasattr(runnable, "stream"):
            return runnable.invoke(messages)
        reply = None
        writing = False
        for chunk in runnable.stream(messages):
            reply = chunk if reply is None else reply + chunk
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                if not writing:
                    on_stage("writing", {})
                    writing = True
                on_stage("delta", {"text": text})
        return reply

    def _tool_round(self, model, messages, profile: FirmProfile | None, on_stage: Stage):
        """One round: the model may call tools once, then answers without further tool calls.
        Returns the final reply, all replies (for token usage) and the tool runs."""
        tools = self.tools(profile, date.today()) if self.tools else []
        on_stage("model", {})
        if not tools:
            reply = self._call(model, messages, on_stage)
            return reply, [reply], []
        first = self._call(model.bind_tools(tools), messages, on_stage)
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
        final = self._call(model.bind_tools(tools, tool_choice="none"), follow_up, on_stage)
        return final, [first, final], runs

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        profile: FirmProfile | None = None,
        model_id: str | None = None,
        on_stage: Stage = _quiet,
        strategy: str | None = None,
    ) -> AskResponse:
        """Answers a question. If it fails on the way, the step it failed in is logged before
        the error goes on to the caller (logs.py)."""
        started = time.monotonic()
        model_id = model_id or self.model_id
        strategy = strategy or self.strategy
        if model_id not in self.models:
            raise ValueError(f"unknown model {model_id!r}; choose one of {', '.join(self.models)}")
        step = "precheck"

        def report(stage: str, data: dict) -> None:
            nonlocal step
            step = _STEPS.get(stage, "answer")
            on_stage(stage, data)

        try:
            return self._answer(question, top_k, profile, model_id, report, strategy, started)
        except Exception as e:
            seconds = round(time.monotonic() - started, 1)
            prompt_failed(step, e, model=model_id, strategy=strategy, seconds=seconds)
            raise

    def _answer(
        self,
        question: str,
        top_k: int | None,
        profile: FirmProfile | None,
        model_id: str,
        on_stage: Stage,
        strategy: str,
        started: float,
    ) -> AskResponse:
        question, redactions = redact(question)
        on_stage("precheck", {"redactions": redactions})
        screener = self.screeners.get(model_id)
        screening_reply = None
        if screener is not None:
            verdict, screening_reply = screen(question, screener)
            if verdict != "ok":
                on_stage("refused", {"reason": verdict})
                usage = _usage(screening_reply, prices=self.prices(model_id))
                log.info("ask refused reason=%s model=%s", verdict, model_id)
                return AskResponse(
                    question=question,
                    redactions=redactions,
                    answer="",
                    passages=[],
                    cited=[],
                    coverage="none",
                    model=model_id,
                    strategy=strategy,
                    usage=usage,
                    disclaimer=DISCLAIMER,
                    refusal=verdict,
                    trace=Trace(
                        strategy=strategy,
                        seconds={"total": round(time.monotonic() - started, 2)},
                    ),
                )
        on_stage("search", {"redactions": redactions})
        translation, translation_reply = None, None
        if (translator := self.translators.get(model_id)) is not None:
            translating = time.monotonic()
            translation, translation_reply = translate(question, translator)
            translation_seconds = round(time.monotonic() - translating, 2)
        translated = {"translation": translation.query} if translation else {}
        try:
            if hasattr(self.retriever, "search"):
                passages, trace = self.retriever.search(
                    question, top_k or self.top_k, strategy, **translated
                )
            else:  # a retriever without an Answer Trace, as in tests
                passages = self.retriever.retrieve(
                    question, top_k or self.top_k, strategy, **translated
                )
                trace = {"strategy": strategy, "vector": []}
            trace["seconds"] = {"search": round(time.monotonic() - started, 2)}
        except openai.APIError as e:
            raise UpstreamError(f"the embedding service did not respond: {e}") from e
        except SQLAlchemyError as e:
            raise DatabaseError("the database is not reachable") from e
        if translation and trace.get("translation"):
            trace["translation"]["language"] = translation.language
            trace["seconds"]["translation"] = translation_seconds
        on_stage(
            "found",
            {
                "count": len(passages),
                "sources": list(
                    dict.fromkeys(p.document.metadata["short_title"] for p in passages)
                ),
            },
        )
        messages = build_messages(
            question,
            passages,
            profile.describe() if profile else "",
            self.prompts.get(model_id, ""),
        )
        answering = time.monotonic()
        try:
            reply, replies, runs = self._tool_round(
                self.models[model_id], messages, profile, on_stage
            )
        except openai.APIError as e:
            raise UpstreamError(f"the answer model did not respond: {e}") from e
        trace["seconds"]["answer"] = round(time.monotonic() - answering, 2)
        trace["seconds"]["total"] = round(time.monotonic() - started, 2)

        answer, coverage = split_coverage(_text(reply))
        if not usage_reported(replies):
            log.debug("cost computed from list prices for %s", model_id)
        # the screening and translation calls are part of the cost
        replies = [r for r in (screening_reply, translation_reply) if r is not None] + replies
        usage = _usage(*replies, prices=self.prices(model_id))
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
            strategy=strategy,
            trace=Trace.model_validate(trace),
            usage=usage,
            disclaimer=DISCLAIMER,
        )
        finish = (getattr(reply, "response_metadata", None) or {}).get("finish_reason")
        if problems := format_problems(
            answer, coverage, len(response.cited), len(passages), finish
        ):
            prompt_failed(
                "answer", "; ".join(problems), logging.WARNING, model=model_id, strategy=strategy
            )
        log.info(  # counts only: no subject leaves the audit trail
            "ask duration=%.1fs model=%s strategy=%s translated=%s input_tokens=%d "
            "output_tokens=%d tools=%d redactions=%d passages=%d cited=%d",
            time.monotonic() - started,
            model_id,
            strategy,
            translation is not None,
            usage.input_tokens,
            usage.output_tokens,
            len(runs),
            len(redactions),
            len(response.passages),
            len(response.cited),
        )
        return response
