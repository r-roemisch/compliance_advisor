"""Answer Models offered in the interface (config/models.yaml), reached through OpenRouter."""

from pathlib import Path

import httpx
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
        stream_usage=True,  # token counts also when the answer is streamed
    )


_PRICES: dict[str, tuple[float, float]] = {}


def list_price(model_id: str) -> tuple[float, float] | None:
    """OpenRouter's per-token list prices (input, output) in dollars, fetched once."""
    if not _PRICES:
        try:
            data = httpx.get("https://openrouter.ai/api/v1/models", timeout=15).json()["data"]
            for m in data:
                pricing = m.get("pricing") or {}
                _PRICES[m["id"]] = (
                    float(pricing.get("prompt") or 0),
                    float(pricing.get("completion") or 0),
                )
        except (httpx.HTTPError, ValueError, KeyError):
            return None
    return _PRICES.get(model_id)


def chat_models(settings: Settings) -> dict[str, ChatOpenAI]:
    return {m.id: chat_model(m, settings) for m in load_models(settings.models_file)}
