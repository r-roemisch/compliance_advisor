"""Audit trail: every answer is stored with the exact Source versions it used."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .schemas import AskResponse

metadata = MetaData()
answers = Table(
    "answers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("question", Text, nullable=False),  # after the pre-check
    Column("profile", JSONB),
    Column("model", String(200), nullable=False),
    Column("response", JSONB, nullable=False),  # the full response as the interface saw it
    Column("source_versions", JSONB, nullable=False),
    Column("obligations", JSONB),  # rows from "Extract Obligations", if run
    Column("user_id", String(36), index=True),  # the account that asked; empty for guests
)


def source_versions(raw_dir: Path, source_ids: set[str]) -> dict[str, dict]:
    """Download date and checksum of each Source file used, from data/raw/<id>/meta.json."""
    versions = {}
    for source_id in sorted(source_ids):
        try:
            meta = json.loads((raw_dir / source_id / "meta.json").read_text())
            versions[source_id] = {"fetched_at": meta["fetched_at"], "sha256": meta["sha256"]}
        except (OSError, ValueError, KeyError):
            versions[source_id] = {}
    return versions


class AuditStore:
    def __init__(self, engine: Engine, raw_dir: Path):
        self.engine = engine
        self.raw_dir = raw_dir
        metadata.create_all(engine, checkfirst=True)
        with engine.begin() as connection:  # tables created before the obligations column existed
            connection.execute(
                text("alter table answers add column if not exists obligations jsonb")
            )
            connection.execute(
                text("alter table answers add column if not exists user_id varchar(36)")
            )
            connection.execute(
                text("create index if not exists ix_answers_user_id on answers (user_id)")
            )

    def save(
        self, response: AskResponse, profile: dict | None, user_id: str | None = None
    ) -> AskResponse:
        response = response.model_copy(
            update={"id": str(uuid.uuid4()), "created_at": datetime.now(UTC)}
        )
        versions = source_versions(self.raw_dir, {p.source_id for p in response.passages})
        with self.engine.begin() as connection:
            connection.execute(
                answers.insert().values(
                    id=response.id,
                    created_at=response.created_at,
                    question=response.question,
                    profile=profile,
                    model=response.model,
                    response=json.loads(response.model_dump_json()),
                    source_versions=versions,
                    user_id=user_id,
                )
            )
        return response

    def save_obligations(self, answer_id: str, rows: list[dict]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(answers).where(answers.c.id == answer_id).values(obligations=rows)
            )

    @staticmethod
    def _owned_by(user_id: str | None):
        """Answers of this account, or the shared guest answers when nobody is logged in."""
        return answers.c.user_id == user_id if user_id else answers.c.user_id.is_(None)

    def recent(self, user_id: str | None = None, search: str = "", limit: int = 50) -> list[dict]:
        query = select(
            answers.c.id,
            answers.c.created_at,
            answers.c.question,
            answers.c.model,
            (answers.c.obligations.isnot(None)).label("has_obligations"),
        ).where(self._owned_by(user_id))
        if search.strip():
            query = query.where(answers.c.question.ilike(f"%{search.strip()}%"))
        query = query.order_by(answers.c.created_at.desc()).limit(limit)
        with self.engine.connect() as connection:
            return [dict(row._mapping) for row in connection.execute(query)]

    def stats(self, user_id: str) -> dict:
        """Key figures for the dashboard."""
        owned = self._owned_by(user_id)
        cost = answers.c.response["usage"]["cost_usd"].as_float()
        with self.engine.connect() as connection:
            count, total_cost, first, last = connection.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(cost), 0.0),
                    func.min(answers.c.created_at),
                    func.max(answers.c.created_at),
                ).where(owned)
            ).one()
            rows = connection.execute(
                select(answers.c.obligations).where(owned, answers.c.obligations.isnot(None))
            ).all()
        return {
            "questions": count,
            "cost_usd": round(float(total_cost), 4),
            "obligations": sum(len(r[0] or []) for r in rows),
            "answers_with_obligations": len(rows),
            "first_question_at": first,
            "last_question_at": last,
        }

    def get(self, answer_id: str) -> dict | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(answers).where(answers.c.id == answer_id)).first()
            return dict(row._mapping) if row else None


def to_markdown(record: dict) -> str:
    """A readable export of one stored answer, with its Passages and Source versions."""
    r = record["response"]
    lines = [
        "# Compliance Advisor: answer record",
        "",
        f"- Asked: {record['created_at'].isoformat(timespec='seconds')}",
        f"- Model: {r['model']}",
        f"- Tokens: {r['usage']['input_tokens']} in, {r['usage']['output_tokens']} out"
        + (f"; cost {r['usage']['cost_usd']:.4f} $" if r["usage"].get("cost_usd") else ""),
    ]
    if record.get("profile"):
        p = record["profile"]
        lines.append(
            f"- Firm Profile: {p['firm_type']}, {p['size']}, activities: {', '.join(p['activities']) or 'none'}"
        )
    if r.get("redactions"):
        lines.append(f"- Removed by the pre-check: {', '.join(r['redactions'])}")
    lines += ["", "## Question", "", r["question"], "", "## Answer", "", r["answer"], ""]
    if r.get("tools"):
        lines += ["## Rule checks", ""]
        for t in r["tools"]:
            lines += [
                f"### {t['name']}",
                "",
                "```json",
                json.dumps(t["result"], indent=2, ensure_ascii=False),
                "```",
                "",
            ]
    lines += ["## Passages", ""]
    for p in r["passages"]:
        cited = "cited" if p["n"] in r["cited"] else "not cited"
        lines += [
            (
                f"**[{p['n']}] {p.get('provision') or p['short_title']}** "
                f"({p['issuer']}, {p['layer']}, {p.get('legal_status', '')}, {cited}) "
                f"{p.get('link') or p['url']}"
            ),
            "",
            "> " + p["text"].replace("\n", "\n> "),
            "",
        ]
    if record.get("obligations"):
        lines += [
            "## Obligations",
            "",
            "| Addressee | Action | Deadline | Provision |",
            "|---|---|---|---|",
        ]
        for o in record["obligations"]:
            cells = [
                o["addressee"],
                o["action"],
                o["deadline"] or "–",
                f"[{o['provision']}]({o['link']})",
            ]
            lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        lines.append("")
    lines += ["## Source versions", ""]
    for source_id, v in record["source_versions"].items():
        lines.append(
            f"- {source_id}: downloaded {v.get('fetched_at', '?')}, sha256 {v.get('sha256', '?')}"
        )
    lines += ["", f"_{r['disclaimer']}_", ""]
    return "\n".join(lines)
