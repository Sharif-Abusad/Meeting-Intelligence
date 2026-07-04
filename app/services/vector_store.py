"""
Vector Store Service.

Provides utilities for:

- Creating embeddings
- Building a per-meeting Chroma vector store
- Loading an existing vector store
- Creating retrievers

for meeting transcript retrieval.

Note: each meeting gets its own Chroma collection/persist directory,
keyed by `meeting_id`. The original implementation used one fixed
collection for every transcript, which meant every new meeting's
chunks were mixed into (and retrievable alongside) every previous
meeting's chunks - this is fixed here.
"""

from __future__ import annotations

import logging
import re
import threading

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.exceptions import VectorStoreError

logger = logging.getLogger(__name__)

_VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


# ==============================================================================
# Embedding Model (lazy, thread-safe singleton)
# ==============================================================================

_embeddings: HuggingFaceBgeEmbeddings | None = None
_embeddings_lock = threading.Lock()


def get_embeddings() -> HuggingFaceBgeEmbeddings:
    """
    Lazily initialize and return the embedding model.
    """
    global _embeddings

    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                logger.info("Loading embedding model: %s", settings.embedding_model)
                try:
                    _embeddings = HuggingFaceBgeEmbeddings(
                        model_name=settings.embedding_model,
                        model_kwargs={"device": settings.embedding_device},
                    )
                except Exception as exc:  # noqa: BLE001
                    raise VectorStoreError(
                        f"Failed to load embedding model '{settings.embedding_model}': {exc}"
                    ) from exc

    return _embeddings


# ==============================================================================
# Helpers
# ==============================================================================

def _validate_meeting_id(meeting_id: str) -> None:
    if not meeting_id or not _VALID_ID_PATTERN.match(meeting_id):
        raise VectorStoreError(
            f"Invalid meeting_id '{meeting_id}'. Use only letters, digits, "
            "hyphens, and underscores."
        )


def _collection_name(meeting_id: str) -> str:
    return f"meeting_{meeting_id}"


def _persist_directory(meeting_id: str) -> str:
    return str(settings.chroma_root_dir / meeting_id)


# ==============================================================================
# Document Processing
# ==============================================================================

def split_transcript(transcript: str) -> list[str]:
    """
    Split the transcript into overlapping chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.vector_chunk_size,
        chunk_overlap=settings.vector_chunk_overlap,
    )
    return splitter.split_text(transcript)


def create_documents(transcript: str) -> list[Document]:
    """
    Convert a transcript into LangChain documents.
    """
    if not transcript or not transcript.strip():
        raise VectorStoreError("Transcript cannot be empty.")

    chunks = split_transcript(transcript)

    return [
        Document(page_content=chunk, metadata={"chunk_index": index})
        for index, chunk in enumerate(chunks)
    ]


# ==============================================================================
# Vector Store
# ==============================================================================

def build_vector_store(transcript: str, meeting_id: str) -> Chroma:
    """
    Build and persist a Chroma vector store from a transcript, scoped to
    a single meeting so different meetings never share retrieval results.
    """
    _validate_meeting_id(meeting_id)

    logger.info("Building vector store for meeting_id=%s", meeting_id)

    documents = create_documents(transcript)

    try:
        vector_store = Chroma.from_documents(
            documents=documents,
            embedding=get_embeddings(),
            collection_name=_collection_name(meeting_id),
            persist_directory=_persist_directory(meeting_id),
        )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(
            f"Failed to build vector store for meeting_id='{meeting_id}': {exc}"
        ) from exc

    logger.info(
        "Vector store created for meeting_id=%s with %d chunk(s).",
        meeting_id,
        len(documents),
    )
    return vector_store


def load_vector_store(meeting_id: str) -> Chroma:
    """
    Load an existing persisted Chroma vector store for a given meeting.
    """
    _validate_meeting_id(meeting_id)

    persist_directory = settings.chroma_root_dir / meeting_id
    if not persist_directory.exists():
        raise VectorStoreError(
            f"No vector store found for meeting_id='{meeting_id}'. "
            "Build it first with build_vector_store()."
        )

    logger.info("Loading vector store for meeting_id=%s", meeting_id)

    try:
        return Chroma(
            collection_name=_collection_name(meeting_id),
            embedding_function=get_embeddings(),
            persist_directory=str(persist_directory),
        )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(
            f"Failed to load vector store for meeting_id='{meeting_id}': {exc}"
        ) from exc


# ==============================================================================
# Retriever
# ==============================================================================

def get_retriever(vector_store: Chroma, k: int = settings.retriever_top_k):
    """
    Create a similarity retriever from a vector store.
    """
    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )
