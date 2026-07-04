"""
Audio Processing Service.

Provides utilities for:

- Downloading audio from YouTube
- Converting media files to WAV
- Splitting audio into chunks
- Preparing audio for transcription
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import yt_dlp
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from app.core.config import settings
from app.core.exceptions import AudioProcessingError

logger = logging.getLogger(__name__)


# ==============================================================================
# YouTube Download
# ==============================================================================

def download_youtube_audio(url: str, job_dir: Path) -> Path:
    """
    Download the audio from a YouTube video and convert it to WAV.

    Args:
        url: A YouTube video URL.
        job_dir: Directory this job's files should be written to.

    Returns:
        Path to the downloaded WAV file.

    Raises:
        AudioProcessingError: If the download or extraction fails.
    """
    logger.info("Downloading audio from YouTube: %s", url)

    output_template = str(job_dir / "%(title)s.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "noprogress": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as exc:
        raise AudioProcessingError(f"Failed to download audio from '{url}': {exc}") from exc

    wav_file = downloaded_file.with_suffix(".wav")

    if not wav_file.exists():
        raise AudioProcessingError(
            f"Expected downloaded WAV file was not found: {wav_file}"
        )

    logger.info("Download completed: %s", wav_file)
    return wav_file


# ==============================================================================
# Audio Conversion
# ==============================================================================

def convert_to_wav(input_file: str | Path, output_dir: Path | None = None) -> Path:
    """
    Convert an audio/video file into a mono 16 kHz WAV file.

    Args:
        input_file: Path to the source audio/video file.
        output_dir: Directory to write the converted file to. Defaults
            to the source file's own directory.

    Raises:
        AudioProcessingError: If the source file is missing or unreadable.
    """
    source = Path(input_file)

    if not source.exists():
        raise AudioProcessingError(f"Input file does not exist: {source}")

    logger.info("Converting media to WAV: %s", source)

    target_dir = output_dir or source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    output_file = target_dir / f"{source.stem}_converted.wav"

    try:
        audio = AudioSegment.from_file(source)
        (
            audio
            .set_channels(settings.channels)
            .set_frame_rate(settings.sample_rate)
            .export(output_file, format="wav")
        )
    except (CouldntDecodeError, OSError) as exc:
        raise AudioProcessingError(f"Failed to convert '{source}' to WAV: {exc}") from exc

    logger.info("Conversion completed: %s", output_file)
    return output_file


# ==============================================================================
# Audio Chunking
# ==============================================================================

def chunk_audio(
    wav_file: str | Path,
    chunk_minutes: int = settings.default_chunk_minutes,
) -> list[Path]:
    """
    Split a WAV file into smaller chunks for transcription.

    Raises:
        AudioProcessingError: If the file is missing/unreadable or
            `chunk_minutes` is not positive.
    """
    source = Path(wav_file)

    if not source.exists():
        raise AudioProcessingError(f"WAV file does not exist: {source}")

    if chunk_minutes <= 0:
        raise AudioProcessingError("chunk_minutes must be a positive integer.")

    logger.info("Splitting audio into %d-minute chunks: %s", chunk_minutes, source)

    try:
        audio = AudioSegment.from_wav(source)
    except (CouldntDecodeError, OSError) as exc:
        raise AudioProcessingError(f"Failed to read WAV file '{source}': {exc}") from exc

    chunk_length_ms = chunk_minutes * 60 * 1000
    chunk_paths: list[Path] = []

    for index, start in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start:start + chunk_length_ms]
        chunk_path = source.with_name(f"{source.stem}_chunk_{index}.wav")
        chunk.export(chunk_path, format="wav")
        chunk_paths.append(chunk_path)

    if not chunk_paths:
        raise AudioProcessingError(f"No audio chunks were produced from '{source}'.")

    logger.info("Generated %d audio chunk(s).", len(chunk_paths))
    return chunk_paths


# ==============================================================================
# Pipeline
# ==============================================================================

def process_input(source: str, chunk_minutes: int | None = None) -> tuple[str, list[Path]]:
    """
    Prepare an input source (local file or YouTube URL) for transcription.

    Returns:
        A tuple of (job_id, list of WAV chunk paths). The job_id can be
        used to namespace downstream artifacts (vector store collection,
        output files, etc).

    Raises:
        AudioProcessingError: If any stage of preparation fails.
    """
    if not source or not source.strip():
        raise AudioProcessingError("No input source was provided.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = settings.download_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Preparing input source (job_id=%s): %s", job_id, source)

    if source.startswith(("http://", "https://")):
        wav_file = download_youtube_audio(source, job_dir)
    else:
        wav_file = convert_to_wav(source, output_dir=job_dir)

    chunks = chunk_audio(wav_file, chunk_minutes or settings.default_chunk_minutes)

    logger.info("Audio processing completed (job_id=%s).", job_id)
    return job_id, chunks
