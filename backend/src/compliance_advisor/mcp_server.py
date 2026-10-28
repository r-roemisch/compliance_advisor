"""The MCP server: the four Rule Checks and a Corpus search over the Model Context Protocol
(streamable HTTP, mounted at /mcp), so other AI tools can use them.

An API key is required (Authorization: Bearer ca_...) and the key's Account pays into its own
rate limit. No answers are written here: the calling tool writes its own from the Passages, so
outside calls cost the app no Answer Model fees. Built to the remote standard but run locally;
publishing it on the internet is a hosting decision for later.
"""

import contextvars
import json
from collections.abc import Callable
from datetime import date
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .precheck import redact
from .profile import Activity, Customers, FirmProfile, FirmType, SizeClass
from .prompt import DISCLAIMER
from .tools import AIUseFacts, IncidentFacts

_caller: contextvars.ContextVar[dict] = contextvars.ContextVar("mcp_caller")

INSTRUCTIONS = (
    f"{DISCLAIMER} The tools apply rules from EU and German financial regulation to facts you "
    "state and search the Corpus of regulatory texts; they never give legal advice. Pass only "
    "facts the user stated; a Rule Check reports a missing fact instead of guessing it. Cite the "
    "Provision and link each result names."
)


class KeyAuth(BaseHTTPMiddleware):
    """Every MCP request needs an API key; the key's Account is handed to the tools."""

    def __init__(self, app, user_for: Callable[[str], dict | None]):
        super().__init__(app)
        self.user_for = user_for

    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return JSONResponse(
                {"detail": "An API key is required: Authorization: Bearer ca_..."}, 401
            )
        try:
            user = await run_in_threadpool(self.user_for, header[7:].strip())
        except Exception:  # noqa: BLE001 - the key store is the database; say so, not "bad key"
            return JSONResponse({"detail": "The database is not reachable"}, 503)
        if user is None:
            return JSONResponse({"detail": "Unknown or revoked API key"}, 401)
        token = _caller.set(user)
        try:
            return await call_next(request)
        finally:
            _caller.reset(token)


def build_mcp_app(
    tool_factory,
    retriever: Callable[[], object],
    user_for: Callable[[str], dict | None],
    allow: Callable[[str, bool], float | None],
):
    """`tool_factory(profile, today)` gives the app's Rule Checks, `retriever()` the Retriever,
    `user_for(key)` the Account behind a key, `allow(subject, guest)` the rate limiter."""
    server = MCPServer("Compliance Advisor", instructions=INSTRUCTIONS)

    def rule_check(name: str, args: dict, profile: FirmProfile | None = None) -> dict:
        tools = {t.name: t for t in tool_factory(profile, date.today())}
        return json.loads(tools[name].invoke(args))

    def throttle() -> None:
        user = _caller.get(None)
        subject = f"user:{user['id']}" if user else "mcp:anonymous"
        if allow(subject, False) is not None:
            raise ValueError("Rate limit reached for this account; try again later")

    @server.tool(
        name="check_applicability",
        description="Which Regimes in the Corpus (DORA, AML, payments, insurance, banking, digital) apply to a Firm supervised in Germany, with the deciding provisions. Describe the Firm: its type, size class, customers and activities.",
    )
    def check_applicability(
        firm_type: FirmType,
        size: SizeClass,
        customers: Customers = "both",
        activities: list[Activity] | None = None,
    ) -> dict:
        throttle()
        profile = FirmProfile(
            firm_type=firm_type, size=size, customers=customers, activities=activities or []
        )
        return rule_check("check_applicability", {}, profile)

    @server.tool(
        name="compliance_timeline",
        description="Dated milestones of the Sources (entry into force, application dates, versions), past and upcoming; optionally only some Regimes or only upcoming dates.",
    )
    def compliance_timeline(
        regimes: list[Literal["dora", "aml", "payments", "insurance", "banking", "digital"]]
        | None = None,
        upcoming_only: bool = False,
    ) -> dict:
        throttle()
        return rule_check(
            "compliance_timeline", {"regimes": regimes, "upcoming_only": upcoming_only}
        )

    @server.tool(
        name="classify_dora_incident",
        description="Classifies an ICT-related incident as major or not under DORA and RTS 2024/1772, with the reporting deadlines of RTS 2025/301. Pass only the facts stated; unknown facts are reported as missing.",
    )
    def classify_dora_incident(facts: IncidentFacts) -> dict:
        throttle()
        return rule_check("classify_dora_incident", facts.model_dump(exclude_none=True))

    @server.tool(
        name="check_ai_act_use_case",
        description="Risk class of an AI use case under the AI Act (Annex III, Art. 6(3), Art. 50) for a financial firm, with the resulting duties and application dates.",
    )
    def check_ai_act_use_case(facts: AIUseFacts) -> dict:
        throttle()
        return rule_check("check_ai_act_use_case", facts.model_dump(exclude_none=True))

    @server.tool(
        name="search_corpus",
        description="Finds the Passages of EU and German financial regulation (DORA, AMLR, GwG, ZAG, KWG, MaRisk, Solvency II, VAG, IDD, MaGo, CRR, CRD, AI Act, GDPR and others) most relevant to a question, in German or English, with Provision, link, legal status and similarity. Writes no answer: quote and cite the Passages yourself.",
    )
    def search_corpus(
        question: str, k: int = 6, strategy: Literal["vector", "hybrid"] = "vector"
    ) -> dict:
        throttle()
        question, _ = redact(question.strip())  # personal data never reaches the embedding model
        if not 3 <= len(question) <= 2000:
            raise ValueError("question must be 3 to 2000 characters")
        hits = retriever().retrieve(question, max(1, min(k, 12)), strategy)
        return {
            "passages": [
                {
                    "provision": h.document.metadata.get("provision", ""),
                    "source": h.document.metadata.get("short_title", ""),
                    "source_title": h.document.metadata.get("source_title", ""),
                    "language": h.document.metadata.get("language", ""),
                    "legal_status": h.document.metadata.get("legal_status", ""),
                    "link": h.document.metadata.get("link", ""),
                    "score": h.score,
                    "text": h.document.page_content,
                }
                for h in hits
            ],
            "disclaimer": DISCLAIMER,
        }

    app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.add_middleware(KeyAuth, user_for=user_for)
    return app
