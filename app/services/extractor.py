"""
Meeting Analysis Module.

Provides utilities to extract:
- Action Items
- Key Decisions
- Open Questions

using Mistral AI through LangChain.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.exceptions import ExtractionError
from app.core.llm_factory import get_llm
from app.core.prompts import (
    ACTION_ITEMS_PROMPT,
    DECISIONS_PROMPT,
    QUESTIONS_PROMPT
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Chain Builder
# ==============================================================================

def build_chain(system_prompt: str):
    """
    Build an extraction chain using the supplied system prompt.
    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "{text}")]
    )
    return prompt | get_llm(temperature=settings.temperature_extraction) | StrOutputParser()


# ==============================================================================
# Generic Extractor
# ==============================================================================

def extract_information(transcript: str, system_prompt: str) -> str:
    """
    Extract structured information from a meeting transcript.

    Raises:
        ExtractionError: If the transcript is empty or the LLM call fails.
    """
    if not transcript or not transcript.strip():
        raise ExtractionError("Transcript cannot be empty.")

    chain = build_chain(system_prompt)

    try:
        return chain.invoke(transcript)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Failed to extract information: {exc}") from exc


# ==============================================================================
# Public APIs
# ==============================================================================

def extract_action_items(transcript: str) -> str:
    """Extract meeting action items."""
    return extract_information(transcript, ACTION_ITEMS_PROMPT)


def extract_key_decisions(transcript: str) -> str:
    """Extract key decisions from a meeting."""
    return extract_information(transcript, DECISIONS_PROMPT)


def extract_questions(transcript: str) -> str:
    """Extract unresolved questions and follow-up topics."""
    return extract_information(transcript, QUESTIONS_PROMPT)
