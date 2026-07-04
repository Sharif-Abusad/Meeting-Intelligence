"""
Tests for core.vector_store.

These focus on the bug fix (per-meeting scoping) and input validation,
using a fake embeddings object so no model download or network access
is required.
"""

from __future__ import annotations

import pytest

from app.services import vector_store
from app.core.exceptions import VectorStoreError


class _FakeEmbeddings:
    """Minimal stand-in so Chroma doesn't try to download a real model."""

    def embed_documents(self, texts):
        return [[float(len(t))] for t in texts]

    def embed_query(self, text):
        return [float(len(text))]


@pytest.fixture(autouse=True)
def _patch_embeddings(monkeypatch):
    monkeypatch.setattr(vector_store, "get_embeddings", lambda: _FakeEmbeddings())


@pytest.fixture(autouse=True)
def _isolated_chroma_dir(tmp_path):
    # Settings is a frozen dataclass; bypass immutability for the
    # duration of the test and restore the original value after.
    original = vector_store.settings.chroma_root_dir
    object.__setattr__(vector_store.settings, "chroma_root_dir", tmp_path)
    yield
    object.__setattr__(vector_store.settings, "chroma_root_dir", original)


def test_build_and_load_round_trip():
    transcript = "Alice will send the report by Friday. " * 20
    vector_store.build_vector_store(transcript, meeting_id="meeting-1")

    loaded = vector_store.load_vector_store(meeting_id="meeting-1")
    assert loaded is not None


def test_meetings_are_isolated_from_each_other():
    """
    Regression test for the original bug: every meeting shared one
    fixed Chroma collection/persist directory, so a second meeting's
    build would mix into (and be retrievable alongside) the first.
    """
    vector_store.build_vector_store("Meeting one content about budgets.", "meeting-a")
    vector_store.build_vector_store("Meeting two content about hiring.", "meeting-b")

    dir_a = vector_store._persist_directory("meeting-a")
    dir_b = vector_store._persist_directory("meeting-b")

    assert dir_a != dir_b
    assert vector_store._collection_name("meeting-a") != vector_store._collection_name("meeting-b")


def test_load_nonexistent_meeting_raises():
    with pytest.raises(VectorStoreError):
        vector_store.load_vector_store(meeting_id="does-not-exist")


def test_invalid_meeting_id_rejected():
    with pytest.raises(VectorStoreError):
        vector_store.build_vector_store("some transcript text", meeting_id="../../etc")


def test_empty_transcript_rejected():
    with pytest.raises(VectorStoreError):
        vector_store.build_vector_store("   ", meeting_id="meeting-x")
