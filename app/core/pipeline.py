"""
End-to-End Meeting Intelligence Pipeline.

Ties together audio processing, transcription, summarization,
extraction, and vector-store indexing into a single orchestrated
workflow. This is the module application code (CLI, API, etc.)
should call - individual `core.*` modules can still be used directly
for finer-grained control.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import ensure_directories, settings, validate_settings
from app.core.exceptions import MeetingIntelligenceError
from app.services.extractor import extract_action_items, extract_key_decisions, extract_questions
from app.services.summarizer import generate_title, summarize
from app.services.transcriber import transcribe_audio
from app.services.vector_store import build_vector_store

logger = logging.getLogger(__name__)


@dataclass
class MeetingAnalysis:
    """Structured result of running the full pipeline on one meeting."""

    meeting_id: str
    title: str
    transcript: str
    summary: str
    action_items: str
    key_decisions: str
    open_questions: str
    language: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "language": self.language,
            "transcript": self.transcript,
            "summary": self.summary,
            "action_items": self.action_items,
            "key_decisions": self.key_decisions,
            "open_questions": self.open_questions,
            "warnings": self.warnings,
        }


def run_pipeline(
    source: str,
    language: str = "english",
    chunk_minutes: int | None = None,
    build_index: bool = True,
    cleanup_audio: bool = True,
) -> MeetingAnalysis:
    """
    Run the full pipeline on a local audio/video file or a YouTube URL:

        audio -> transcript -> title + summary + extraction (+ vector index)

    Args:
        source: Local file path or YouTube URL.
        language: "english" (Whisper) or "hinglish" (Sarvam).
        chunk_minutes: Override the default audio chunk length.
        build_index: If True, also build a per-meeting vector store so
            `core.rag_engine` can answer follow-up questions later.
        cleanup_audio: If True, delete the downloaded/converted audio
            artifacts once transcription succeeds.

    Raises:
        MeetingIntelligenceError (or a subclass): If any stage fails.
    """
    # Local import to avoid a hard dependency on audio libraries for
    # callers that only need text-based stages (e.g. re-processing an
    # existing transcript).
    from services.audio_processor import process_input

    ensure_directories()
    validate_settings(
        require_mistral=True,
        require_sarvam=(language.strip().lower() == "hinglish"),
    )

    warnings: list[str] = []

    logger.info("Pipeline started for source: %s", source)

    job_id, chunk_paths = process_input(source, chunk_minutes=chunk_minutes)

    try:
        transcript = transcribe_audio(chunk_paths, language=language)
    finally:
        if cleanup_audio:
            _cleanup_job_artifacts(job_id, chunk_paths)

    if not transcript.strip():
        raise MeetingIntelligenceError(
            "Transcription produced an empty transcript; aborting pipeline."
        )

    title = generate_title(transcript)
    summary = summarize(transcript)
    action_items = extract_action_items(transcript)
    key_decisions = extract_key_decisions(transcript)
    open_questions = extract_questions(transcript)

    if build_index:
        try:
            build_vector_store(transcript, job_id)
        except MeetingIntelligenceError as exc:
            # Indexing is a "nice to have" for follow-up Q&A - don't
            # fail the whole pipeline if only this step breaks.
            logger.warning("Vector store indexing failed: %s", exc)
            warnings.append(f"Vector indexing failed: {exc}")

    logger.info("Pipeline completed for meeting_id=%s", job_id)

    return MeetingAnalysis(
        meeting_id=job_id,
        title=title,
        transcript=transcript,
        summary=summary,
        action_items=action_items,
        key_decisions=key_decisions,
        open_questions=open_questions,
        language=language,
        warnings=warnings,
    )


def _cleanup_job_artifacts(job_id: str, chunk_paths: list[Path]) -> None:
    """Best-effort removal of temporary audio artifacts for a job."""
    job_dir = settings.download_dir / job_id

    for chunk in chunk_paths:
        Path(chunk).unlink(missing_ok=True)

    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
