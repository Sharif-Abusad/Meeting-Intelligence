"""
RAG Pipeline for Meeting Transcript Question Answering.

This module provides utilities to:

- Build a new vector store for a meeting and create a RAG chain
- Load an existing vector store for a meeting and create a RAG chain
- Answer questions using the meeting transcript

Note: the original version of this module called
`load_vector_store(transcript)`, but `vector_store.load_vector_store()`
took no arguments at all - that mismatch is fixed here. Both build and
load now consistently key off `meeting_id`.
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from app.core.config import settings
from app.core.exceptions import RAGError
from app.core.llm_factory import get_llm
from app.services.vector_store import build_vector_store, get_retriever, load_vector_store
from app.core.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions
# ==============================================================================

def format_documents(documents) -> str:
    """
    Convert retrieved LangChain documents into a single context string.
    """
    return "\n\n".join(doc.page_content for doc in documents)


def get_prompt() -> ChatPromptTemplate:
    """
    Return the chat prompt template used by the RAG chain.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{question}"),
        ]
    )


# ==============================================================================
# Internal Chain Builder
# ==============================================================================

def _create_rag_chain(vector_store):
    """
    Create a Retrieval-Augmented Generation chain.
    """
    retriever = get_retriever(vector_store, k=settings.retriever_top_k)

    return (
        {
            "context": retriever | RunnableLambda(format_documents),
            "question": RunnablePassthrough(),
        }
        | get_prompt()
        | get_llm(temperature=settings.temperature_rag)
        | StrOutputParser()
    )


# ==============================================================================
# Public API
# ==============================================================================

def build_rag_chain(transcript: str, meeting_id: str):
    """
    Build a new vector store for `meeting_id` from `transcript` and
    create a RAG chain over it.
    """
    vector_store = build_vector_store(transcript, meeting_id)
    return _create_rag_chain(vector_store)


def load_rag_chain(meeting_id: str):
    """
    Load an existing vector store for `meeting_id` and create a RAG chain.
    """
    vector_store = load_vector_store(meeting_id)
    return _create_rag_chain(vector_store)


def ask_question(rag_chain, question: str) -> str:
    """
    Ask a question against the meeting transcript.
    """
    if not question or not question.strip():
        raise RAGError("Question cannot be empty.")

    try:
        return rag_chain.invoke(question)
    except Exception as exc:  # noqa: BLE001
        raise RAGError(f"Failed to answer question: {exc}") from exc
