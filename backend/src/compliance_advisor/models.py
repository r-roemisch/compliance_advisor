"""Answer Models offered in the interface (config/models.yaml), reached through OpenRouter."""

from pathlib import Path

import yaml
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from .settings import OPENROUTER_BASE_URL, Settings


class ModelOption(BaseModel, extra="forbid"):
    id: str
    label: str
    note: dict[str, str] = {}
    eu_hosted: bool = False
    provider_only: list[str] = []


def load_models(path: Path) -> list[ModelOption]:
    entries = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("models") or []
    models = [ModelOption.model_validate(e) for e in entries]
    if not models:
        raise SystemExit(f"{path} lists no models")
    return models


def chat_model(option: ModelOption, settings: Settings) -> ChatOpenAI:
    extra: dict = {"usage": {"include": True}}  # OpenRouter then reports the cost of each call
    if option.provider_only:
        extra["provider"] = {"only": option.provider_only, "allow_fallbacks": False}
    return ChatOpenAI(
        model=option.id,
        api_key=settings.require_api_key(),
        base_url=OPENROUTER_BASE_URL,
        timeout=90,
        max_retries=1,
        default_headers={"X-Title": "Compliance Advisor"},
        extra_body=extra,
    )


def chat_models(settings: Settings) -> dict[str, ChatOpenAI]:
    return {m.id: chat_model(m, settings) for m in load_models(settings.models_file)}
