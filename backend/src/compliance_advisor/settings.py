"""Settings read from the environment and from the `.env` file at the project root."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# src/compliance_advisor/settings.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    openrouter_api_key: str = ""
    database_url: str = "postgresql+psycopg://advisor:advisor@localhost:5433/advisor"
    embedding_model: str = "openai/text-embedding-3-small"
    top_k: int = 6
    # At most this many Passages from one Source; 0 = no cap. Off since 2026-10-23: the evaluation
    # (docs/EVALUATION.md) showed the cap costs hits; the direct lookup of named Provisions stays.
    max_per_source: int = 0
    candidates: int = 24  # Passages fetched before the cap is applied, and per search for hybrid
    # Search Strategy when the question does not choose one: vector | hybrid. The better one on the
    # Golden Set (docs/EVALUATION.md).
    search_strategy: str = "vector"
    # The Pre-Check's screening (ADR 0007): on by default; the model that screens unless the
    # chosen Answer Model is EU-hosted, which then screens itself.
    screening: bool = True
    screening_model: str = "openai/gpt-6-luna"
    # Query Translation (ADR 0008): the question is also searched in the Corpus's other language.
    # The model that translates, unless the chosen Answer Model is EU-hosted and translates itself.
    query_translation: bool = True
    translation_model: str = "openai/gpt-6-luna"
    log_format: str = "json"  # json (one object per line) | text
    # Update Runs: a nightly check of every Source for a new version, inside the backend.
    update_runs: bool = False
    update_hour: int = 3  # UTC
    # Weight of the keyword ranks in hybrid search. 0.5 beat 1.0 and re-sorting only the vector
    # candidates on the tuning half of the Golden Set; vector search still did better (2026-10-28).
    keyword_weight: float = 0.5
    chunker: str = "provision"  # provision | fixed (the naive baseline)
    chunk_size: int = 1000  # fixed chunker
    chunk_overlap: int = 150  # fixed chunker
    provision_max_chars: int = 2500  # longer Provisions are split into parts
    provision_overlap: int = 200
    api_host: str = "127.0.0.1"
    cookie_secure: bool = False  # set true when served over HTTPS
    # Only behind a reverse proxy that sets x-forwarded-for (nginx, Traefik): then cookieless
    # requests are rate-limited by the address the proxy appended rather than the proxy's own.
    trust_x_forwarded_for: bool = False
    api_port: int = 8010

    config_dir: Path = PROJECT_ROOT / "config"
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def collection(self) -> str:
        """One collection per embedding model and chunker, so indexes never mix."""
        return f"{self.embedding_model}:{self.chunker}"

    @property
    def models_file(self) -> Path:
        return self.config_dir / "models.yaml"

    @property
    def sources_file(self) -> Path:
        return self.config_dir / "sources.yaml"

    @property
    def limits_file(self) -> Path:
        return self.config_dir / "limits.yaml"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def require_api_key(self) -> str:
        if not self.openrouter_api_key:
            raise SystemExit(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env at the project root "
                "and add your key."
            )
        return self.openrouter_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
