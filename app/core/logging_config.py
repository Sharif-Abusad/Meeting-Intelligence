"""
Central logging configuration.

Call `configure_logging()` once, at process startup (CLI entry point
or app server), rather than each module setting up its own handlers.
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings

_CONFIGURED = False


def configure_logging(level: str | None = None) -> None:
    global _CONFIGURED

    if _CONFIGURED:
        return

    logging.basicConfig(
        level=level or settings.log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    # Third-party libraries are noisy at INFO/DEBUG; keep them quiet
    # unless the app itself is running in DEBUG mode.
    if (level or settings.log_level).upper() != "DEBUG":
        for noisy_logger in ("httpx", "urllib3", "yt_dlp", "chromadb"):
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    _CONFIGURED = True
