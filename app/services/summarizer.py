"""
Meeting Summarization Module.

This module provides utilities to:
- Split meeting transcripts
- Generate professional meeting summaries (map-reduce)
- Generate concise meeting titles

using Mistral AI and LangChain.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.exceptions import SummarizationError
from app.core.llm_factory import get_llm
from app.core.prompts import (
    MAP_SUMMARY_PROMPT,
    FINAL_SUMMARY_PROMPT,
    TITLE_PROMPT
)
logger = logging.getLogger(__name__)

# ==============================================================================
# Transcript Utilities
# ==============================================================================

def split_transcript(transcript: str) -> list[str]:
    """
    Split a meeting transcript into overlapping chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.summary_chunk_size,
        chunk_overlap=settings.summary_chunk_overlap,
    )
    return splitter.split_text(transcript)


# ==============================================================================
# Chain Builders
# ==============================================================================

def build_summary_chain():
    prompt = ChatPromptTemplate.from_messages(
        [("system", MAP_SUMMARY_PROMPT), ("human", "{text}")]
    )
    return prompt | get_llm(temperature=settings.temperature_summary) | StrOutputParser()


def build_final_summary_chain():
    prompt = ChatPromptTemplate.from_messages(
        [("system", FINAL_SUMMARY_PROMPT), ("human", "{text}")]
    )
    return prompt | get_llm(temperature=settings.temperature_summary) | StrOutputParser()


def build_title_chain():
    prompt = ChatPromptTemplate.from_messages(
        [("system", TITLE_PROMPT), ("human", "{text}")]
    )
    return prompt | get_llm(temperature=settings.temperature_summary) | StrOutputParser()


# ==============================================================================
# Public API
# ==============================================================================

def summarize(transcript: str) -> str:
    """
    Generate a professional meeting summary using a map-reduce workflow.

    Raises:
        SummarizationError: If the transcript is empty or the LLM calls fail.
    """
    if not transcript or not transcript.strip():
        raise SummarizationError("Transcript cannot be empty.")

    summary_chain = build_summary_chain()
    final_chain = build_final_summary_chain()

    chunks = split_transcript(transcript)
    logger.info("Summarizing transcript in %d chunk(s).", len(chunks))

    try:
        partial_summaries = [
            summary_chain.invoke({"text": chunk}) for chunk in chunks
        ]
        combined_summary = "\n\n".join(partial_summaries)
        return final_chain.invoke({"text": combined_summary})
    except Exception as exc:  # noqa: BLE001
        raise SummarizationError(f"Failed to generate summary: {exc}") from exc


def generate_title(transcript: str) -> str:
    """
    Generate a concise title for a meeting transcript.

    Raises:
        SummarizationError: If the transcript is empty or the LLM call fails.
    """
    if not transcript or not transcript.strip():
        raise SummarizationError("Transcript cannot be empty.")

    title_chain = build_title_chain()

    try:
        return title_chain.invoke({"text": transcript[:2000]}).strip()
    except Exception as exc:  # noqa: BLE001
        raise SummarizationError(f"Failed to generate title: {exc}") from exc
