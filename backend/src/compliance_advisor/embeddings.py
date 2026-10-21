"""The embedding model, reached through OpenRouter's OpenAI-compatible API."""

from langchain_openai import OpenAIEmbeddings

from .settings import OPENROUTER_BASE_URL, Settings


def get_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.require_api_key(),
        base_url=OPENROUTER_BASE_URL,
        # The token-length check needs OpenAI's own model names; OpenRouter ids like
        # "openai/text-embedding-3-small" are sent as plain text instead.
        check_embedding_ctx_length=False,
        chunk_size=128,  # Passages per request
        default_headers={"X-Title": "Compliance Advisor"},
    )
