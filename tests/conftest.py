"""
Shared pytest fixtures/config.

`faster_whisper` pulls in a large native `ctranslate2` build. None of
the unit tests actually load a real Whisper model (that would make
them slow, flaky, and non-hermetic), so we stub the module here. This
only affects the test environment - production installs still declare
`faster-whisper` in requirements.txt and use the real package.
"""

from __future__ import annotations

import sys
import types


def _install_faster_whisper_stub() -> None:
    if "faster_whisper" in sys.modules:
        return

    module = types.ModuleType("faster_whisper")

    class _StubWhisperModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "faster_whisper is stubbed out in tests; install the real "
                "package to use Whisper transcription."
            )

    module.WhisperModel = _StubWhisperModel
    sys.modules["faster_whisper"] = module


_install_faster_whisper_stub()
