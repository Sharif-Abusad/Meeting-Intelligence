"""
Application-specific exception hierarchy.

Using dedicated exception types (instead of letting raw exceptions
from yt-dlp, pydub, requests, etc. propagate) lets callers catch
failures at the right granularity and lets the CLI / API layer return
meaningful error messages instead of stack traces.
"""

from __future__ import annotations


class MeetingIntelligenceError(Exception):
    """Base class for all application errors."""


class ConfigurationError(MeetingIntelligenceError):
    """Raised when required configuration/credentials are missing or invalid."""


class AudioProcessingError(MeetingIntelligenceError):
    """Raised when downloading, converting, or chunking audio fails."""


class TranscriptionError(MeetingIntelligenceError):
    """Raised when speech-to-text transcription fails."""


class SummarizationError(MeetingIntelligenceError):
    """Raised when generating a summary or title fails."""


class ExtractionError(MeetingIntelligenceError):
    """Raised when extracting action items/decisions/questions fails."""


class VectorStoreError(MeetingIntelligenceError):
    """Raised when building, loading, or querying the vector store fails."""


class RAGError(MeetingIntelligenceError):
    """Raised when a retrieval-augmented question-answer call fails."""
