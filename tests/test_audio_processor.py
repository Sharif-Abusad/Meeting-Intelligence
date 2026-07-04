"""
Tests for core.audio_processor - validation and error paths that
don't require real media files or network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import audio_processor
from app.core.exceptions import AudioProcessingError


def test_process_input_rejects_empty_source():
    with pytest.raises(AudioProcessingError):
        audio_processor.process_input("")


def test_convert_to_wav_rejects_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(AudioProcessingError):
        audio_processor.convert_to_wav(missing)


def test_chunk_audio_rejects_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.wav"
    with pytest.raises(AudioProcessingError):
        audio_processor.chunk_audio(missing)


def test_chunk_audio_rejects_non_positive_chunk_minutes(tmp_path):
    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(b"not really a wav but exists")

    with pytest.raises(AudioProcessingError):
        audio_processor.chunk_audio(fake_wav, chunk_minutes=0)


def test_convert_to_wav_uses_output_dir(monkeypatch, tmp_path):
    source = tmp_path / "input.mp3"
    source.write_bytes(b"fake audio bytes")

    output_dir = tmp_path / "job_dir"

    class _FakeAudio:
        def set_channels(self, n):
            return self

        def set_frame_rate(self, n):
            return self

        def export(self, path, format):
            Path(path).write_bytes(b"fake wav")

    monkeypatch.setattr(
        audio_processor.AudioSegment, "from_file", lambda p: _FakeAudio()
    )

    result = audio_processor.convert_to_wav(source, output_dir=output_dir)

    assert result.parent == output_dir
    assert result.exists()
