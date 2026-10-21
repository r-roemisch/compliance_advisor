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
    answer_model: str = "openai/gpt-6-luna"
    top_k: int = 6
    chunk_size: int = 1000
    chunk_overlap: int = 150
    api_host: str = "127.0.0.1"
    api_port: int = 8010

    config_dir: Path = PROJECT_ROOT / "config"
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def sources_file(self) -> Path:
        return self.config_dir / "sources.yaml"

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
