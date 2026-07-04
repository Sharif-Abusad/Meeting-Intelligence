"""
Centralized Application Configuration.

All environment-dependent values (API keys, model names, directories,
tunables) are read here exactly once and exposed via a single
`settings` object. No other module should call `os.getenv` directly -
this keeps configuration auditable and makes testing/overriding easy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # -- Mistral / LLM -------------------------------------------------
    mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    temperature_extraction: float = _env_float("LLM_TEMPERATURE_EXTRACTION", 0.2)
    temperature_summary: float = _env_float("LLM_TEMPERATURE_SUMMARY", 0.2)
    temperature_rag: float = _env_float("LLM_TEMPERATURE_RAG", 0.3)

    # -- Sarvam (Hinglish STT) ------------------------------------------
    sarvam_api_key: str | None = os.getenv("SARVAM_API_KEY")
    sarvam_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")
    sarvam_url: str = os.getenv(
        "SARVAM_URL", "https://api.sarvam.ai/speech-to-text-translate"
    )
    sarvam_piece_seconds: int = _env_int("SARVAM_PIECE_SECONDS", 25)
    sarvam_max_retries: int = _env_int("SARVAM_MAX_RETRIES", 3)

    # -- Whisper (English STT) ------------------------------------------
    whisper_model_name: str = os.getenv("WHISPER_MODEL", "small")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # -- Audio processing -------------------------------------------------
    download_dir: Path = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
    sample_rate: int = _env_int("AUDIO_SAMPLE_RATE", 16_000)
    channels: int = _env_int("AUDIO_CHANNELS", 1)
    default_chunk_minutes: int = _env_int("AUDIO_CHUNK_MINUTES", 10)

    # -- Vector store / RAG ------------------------------------------------
    chroma_root_dir: Path = Path(os.getenv("CHROMA_ROOT_DIR", "vector_db"))
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    vector_chunk_size: int = _env_int("VECTOR_CHUNK_SIZE", 500)
    vector_chunk_overlap: int = _env_int("VECTOR_CHUNK_OVERLAP", 50)
    retriever_top_k: int = _env_int("RETRIEVER_TOP_K", 4)

    # -- Summarization -------------------------------------------------
    summary_chunk_size: int = _env_int("SUMMARY_CHUNK_SIZE", 3000)
    summary_chunk_overlap: int = _env_int("SUMMARY_CHUNK_OVERLAP", 100)

    # -- Networking -------------------------------------------------
    request_timeout_seconds: int = _env_int("REQUEST_TIMEOUT_SECONDS", 120)

    # -- Logging -------------------------------------------------
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()


def ensure_directories() -> None:
    """Create all directories the application writes to, if missing."""
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_root_dir.mkdir(parents=True, exist_ok=True)


def validate_settings(require_mistral: bool = True, require_sarvam: bool = False) -> None:
    """
    Fail fast with a clear error instead of surfacing a cryptic
    downstream exception when a required credential is missing.
    """
    missing: list[str] = []

    if require_mistral and not settings.mistral_api_key:
        missing.append("MISTRAL_API_KEY")

    if require_sarvam and not settings.sarvam_api_key:
        missing.append("SARVAM_API_KEY")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in your .env file or environment before starting."
        )
