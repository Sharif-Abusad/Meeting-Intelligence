"""
Shared LLM client factory.

Every module that previously defined its own `get_llm()` now goes
through here. Clients are cached per-temperature so the pipeline
doesn't construct a fresh client object for every single call.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_mistralai import ChatMistralAI

from app.core.config import settings
from app.core.exceptions import ConfigurationError


@lru_cache(maxsize=8)
def get_llm(temperature: float = 0.2) -> ChatMistralAI:
    """
    Return a cached, configured Mistral chat model for the given
    temperature. Raises ConfigurationError if no API key is set.
    """
    if not settings.mistral_api_key:
        raise ConfigurationError(
            "MISTRAL_API_KEY is not configured. Set it in your environment "
            "or .env file."
        )

    return ChatMistralAI(
        model=settings.mistral_model,
        mistral_api_key=settings.mistral_api_key,
        temperature=temperature,
    )
