"""
Tests for core.rag_engine.

Verifies the fix for the original signature mismatch bug: previously
`load_rag_chain(transcript)` called `load_vector_store(transcript)`,
but `load_vector_store()` took no arguments - so loading a chain by
transcript could never actually work. Now both build and load take a
`meeting_id`.
"""

from __future__ import annotations

import pytest

from app.services import rag_engine
from app.core.exceptions import RAGError


class _StubChain:
    def __init__(self, answer="stub answer"):
        self.answer = answer
        self.last_question = None

    def invoke(self, question):
        self.last_question = question
        return self.answer


def test_build_rag_chain_uses_meeting_id(monkeypatch):
    captured = {}

    def fake_build_vector_store(transcript, meeting_id):
        captured["transcript"] = transcript
        captured["meeting_id"] = meeting_id
        return "fake-vector-store"

    monkeypatch.setattr(rag_engine, "build_vector_store", fake_build_vector_store)
    monkeypatch.setattr(rag_engine, "_create_rag_chain", lambda vs: _StubChain())

    chain = rag_engine.build_rag_chain("some transcript", meeting_id="meeting-123")

    assert captured == {"transcript": "some transcript", "meeting_id": "meeting-123"}
    assert isinstance(chain, _StubChain)


def test_load_rag_chain_uses_meeting_id_not_transcript(monkeypatch):
    """This is the specific case that was broken before the fix."""
    captured = {}

    def fake_load_vector_store(meeting_id):
        captured["meeting_id"] = meeting_id
        return "fake-vector-store"

    monkeypatch.setattr(rag_engine, "load_vector_store", fake_load_vector_store)
    monkeypatch.setattr(rag_engine, "_create_rag_chain", lambda vs: _StubChain())

    rag_engine.load_rag_chain(meeting_id="meeting-123")

    assert captured == {"meeting_id": "meeting-123"}


def test_ask_question_rejects_empty_question():
    with pytest.raises(RAGError):
        rag_engine.ask_question(_StubChain(), "   ")


def test_ask_question_returns_chain_output():
    chain = _StubChain(answer="Alice owns the report task.")
    result = rag_engine.ask_question(chain, "Who owns the report task?")

    assert result == "Alice owns the report task."
    assert chain.last_question == "Who owns the report task?"
