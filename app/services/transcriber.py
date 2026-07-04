"""
Speech-to-Text Service.

Supports:

- Whisper (English)
- Sarvam AI (Hinglish -> English)

The module automatically routes requests based on the requested language.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import requests
from faster_whisper import WhisperModel
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import TranscriptionError

logger = logging.getLogger(__name__)


# ==============================================================================
# Whisper Model (lazy, thread-safe singleton)
# ==============================================================================

_MODEL: WhisperModel | None = None
_MODEL_LOCK = threading.Lock()


def get_whisper_model() -> WhisperModel:
    """
    Lazily initialize and return the Whisper model. Safe to call
    concurrently from multiple threads.
    """
    global _MODEL

    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                logger.info("Loading Whisper model: %s", settings.whisper_model_name)
                try:
                    _MODEL = WhisperModel(
                        settings.whisper_model_name,
                        device=settings.whisper_device,
                        compute_type=settings.whisper_compute_type,
                    )
                except Exception as exc:  # noqa: BLE001 - surface as our own type
                    raise TranscriptionError(
                        f"Failed to load Whisper model '{settings.whisper_model_name}': {exc}"
                    ) from exc
                logger.info("Whisper model loaded successfully.")

    return _MODEL


# ==============================================================================
# Whisper Transcription
# ==============================================================================

def transcribe_with_whisper(audio_path: str | Path) -> str:
    """
    Transcribe an audio file using Faster Whisper.
    """
    path = Path(audio_path)
    if not path.exists():
        raise TranscriptionError(f"Audio file does not exist: {path}")

    model = get_whisper_model()

    try:
        segments, _ = model.transcribe(str(path), task="transcribe")
        return " ".join(segment.text for segment in segments).strip()
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError(f"Whisper transcription failed for '{path}': {exc}") from exc


# ==============================================================================
# Sarvam API
# ==============================================================================

@retry(
    reraise=True,
    stop=stop_after_attempt(settings.sarvam_max_retries),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(requests.RequestException),
)
def _post_to_sarvam(audio_path: Path) -> requests.Response:
    headers = {"api-subscription-key": settings.sarvam_api_key}
    data = {"model": settings.sarvam_model, "with_diarization": "false"}

    with open(audio_path, "rb") as audio_file:
        response = requests.post(
            settings.sarvam_url,
            headers=headers,
            files={"file": (audio_path.name, audio_file, "audio/wav")},
            data=data,
            timeout=settings.request_timeout_seconds,
        )

    response.raise_for_status()
    return response


def send_to_sarvam(audio_path: str | Path) -> str:
    """
    Send an audio file to the Sarvam Speech-to-Text API and return the
    transcript. Retries transient network errors with backoff.
    """
    if not settings.sarvam_api_key:
        raise TranscriptionError("SARVAM_API_KEY is not configured.")

    path = Path(audio_path)

    try:
        response = _post_to_sarvam(path)
    except requests.RequestException as exc:
        raise TranscriptionError(f"Sarvam API request failed for '{path}': {exc}") from exc

    try:
        return response.json().get("transcript", "")
    except ValueError as exc:
        raise TranscriptionError(f"Sarvam API returned an invalid response: {exc}") from exc


# ==============================================================================
# Sarvam Transcription (with chunking for long audio + guaranteed cleanup)
# ==============================================================================

def transcribe_with_sarvam(audio_path: str | Path) -> str:
    """
    Split long audio into pieces accepted by Sarvam and combine results.
    """
    if not settings.sarvam_api_key:
        raise TranscriptionError("SARVAM_API_KEY is not configured.")

    path = Path(audio_path)
    if not path.exists():
        raise TranscriptionError(f"Audio file does not exist: {path}")

    try:
        audio = AudioSegment.from_wav(path)
    except (CouldntDecodeError, OSError) as exc:
        raise TranscriptionError(f"Failed to read WAV file '{path}': {exc}") from exc

    piece_length_ms = settings.sarvam_piece_seconds * 1000
    transcripts: list[str] = []

    for index, start in enumerate(range(0, len(audio), piece_length_ms)):
        piece = audio[start:start + piece_length_ms]
        temp_file = path.with_name(f"{path.stem}_piece_{index}.wav")

        piece.export(temp_file, format="wav")

        try:
            logger.info("Processing Sarvam chunk %d", index + 1)
            transcripts.append(send_to_sarvam(temp_file))
        finally:
            temp_file.unlink(missing_ok=True)

    return " ".join(transcripts).strip()


# ==============================================================================
# Routing
# ==============================================================================

def transcribe_chunk(audio_path: str | Path, language: str = "english") -> str:
    """
    Route transcription of a single chunk to the appropriate engine.
    """
    normalized_language = language.strip().lower()

    if normalized_language == "hinglish":
        return transcribe_with_sarvam(audio_path)

    return transcribe_with_whisper(audio_path)


# ==============================================================================
# Public API
# ==============================================================================

def transcribe_audio(chunks: list[str | Path], language: str = "english") -> str:
    """
    Transcribe multiple audio chunks and join them into a single transcript.

    Raises:
        TranscriptionError: If no chunks are provided or any chunk fails.
    """
    if not chunks:
        raise TranscriptionError("No audio chunks were provided for transcription.")

    engine = "Sarvam" if language.strip().lower() == "hinglish" else "Whisper"
    logger.info("Starting transcription of %d chunk(s) using %s", len(chunks), engine)

    transcripts: list[str] = []
    for index, chunk in enumerate(chunks):
        logger.info("Transcribing chunk %d/%d", index + 1, len(chunks))
        transcripts.append(transcribe_chunk(chunk, language))

    logger.info("Transcription completed.")
    return " ".join(transcripts).strip()
