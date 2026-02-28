"""
Unit tests for tts/sarvam.py

SarvamTTS SDK and AudioCache are fully mocked — no API calls, no network.
pydub-dependent tests are skipped automatically when pydub is not installed.
"""

import asyncio
import io
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from narration.sarvam_client import AudioClip
from tts.sarvam import _trim_silence, generate_all_audio, generate_audio_async


# ── Local WAV helpers ────────────────────────────────────────────────────────

def _make_wav(duration_s: float = 1.0, sample_rate: int = 22050, amplitude: int = 0) -> bytes:
    num_frames = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        if amplitude == 0:
            wf.writeframes(b"\x00\x00" * num_frames)
        else:
            data = b""
            for i in range(num_frames):
                val = amplitude if (i % 100) < 50 else -amplitude
                data += struct.pack("<h", val)
            wf.writeframes(data)
    return buf.getvalue()


def _make_padded_wav(
    before_ms: int = 200,
    content_ms: int = 1000,
    after_ms: int = 200,
    amplitude: int = 8000,
    sample_rate: int = 22050,
) -> bytes:
    """WAV: silence | square-wave content | silence."""
    before_frames  = int(sample_rate * before_ms  / 1000)
    content_frames = int(sample_rate * content_ms / 1000)
    after_frames   = int(sample_rate * after_ms   / 1000)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * before_frames)
        data = b""
        for i in range(content_frames):
            val = amplitude if (i % 100) < 50 else -amplitude
            data += struct.pack("<h", val)
        wf.writeframes(data)
        wf.writeframes(b"\x00\x00" * after_frames)
    return buf.getvalue()


def _make_clip(duration_s: float = 3.0, amplitude: int = 0, text: str = "Hello.") -> AudioClip:
    return AudioClip(
        audio_bytes=_make_wav(duration_s, amplitude=amplitude),
        duration=duration_s,
        sample_rate=22050,
        text=text,
    )


# ── _trim_silence ────────────────────────────────────────────────────────────

class TestTrimSilence:

    def test_empty_audio_bytes_returns_original_unchanged(self):
        clip = AudioClip(audio_bytes=b"", duration=5.0, text="")
        result = _trim_silence(clip)
        assert result is clip

    def test_silence_padding_trimmed_reduces_duration(self):
        pytest.importorskip("pydub", reason="pydub not installed")
        padded = _make_padded_wav(before_ms=300, content_ms=1000, after_ms=300)
        total_dur = 1.6  # 300 + 1000 + 300 ms
        clip = AudioClip(audio_bytes=padded, duration=total_dur, sample_rate=22050, text="t")

        trimmed = _trim_silence(clip)

        # Silence removed → duration should shrink
        assert trimmed.duration < total_dur
        # Core content still present
        assert trimmed.duration > 0.5

    def test_all_silent_clip_returns_original(self):
        pytest.importorskip("pydub", reason="pydub not installed")
        silent = _make_wav(duration_s=1.0, amplitude=0)
        clip = AudioClip(audio_bytes=silent, duration=1.0, sample_rate=22050, text="t")

        result = _trim_silence(clip)

        # No non-silent ranges → fall-through → original returned
        assert result.audio_bytes == clip.audio_bytes

    def test_pydub_import_error_returns_original(self):
        """When pydub is unavailable the function falls back gracefully."""
        clip = _make_clip(3.0)
        with patch.dict("sys.modules", {"pydub": None, "pydub.silence": None}):
            result = _trim_silence(clip)
        assert result is clip

    def test_trimmed_result_has_nonempty_audio_bytes(self):
        pytest.importorskip("pydub", reason="pydub not installed")
        padded = _make_padded_wav()
        clip = AudioClip(audio_bytes=padded, duration=1.4, sample_rate=22050, text="t")

        trimmed = _trim_silence(clip)

        assert len(trimmed.audio_bytes) > 0

    def test_clean_audio_not_over_trimmed(self):
        pytest.importorskip("pydub", reason="pydub not installed")
        pure = _make_wav(duration_s=1.0, amplitude=8000)
        clip = AudioClip(audio_bytes=pure, duration=1.0, sample_rate=22050, text="t")

        trimmed = _trim_silence(clip)

        assert trimmed.duration > 0


# ── generate_audio_async ─────────────────────────────────────────────────────

class TestGenerateAudioAsync:

    def _tts(self, text: str = "Hello.", duration: float = 3.0) -> MagicMock:
        tts = MagicMock()
        tts.generate.return_value = _make_clip(duration, text=text)
        return tts

    def _cache(self, cached: AudioClip | None = None) -> MagicMock:
        c = MagicMock()
        c.get.return_value = cached
        return c

    async def test_cache_hit_returns_cached_clip_without_tts_call(self):
        cached = _make_clip(2.0, text="cached")
        tts   = self._tts()
        cache = self._cache(cached)

        result = await generate_audio_async("Hello.", "shubh", "en", tts, cache)

        assert result is cached
        tts.generate.assert_not_called()

    async def test_cache_miss_calls_tts_generate(self):
        tts   = self._tts()
        cache = self._cache(None)

        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            await generate_audio_async("Hello.", "shubh", "en", tts, cache)

        tts.generate.assert_called_once_with("Hello.", "en")

    async def test_cache_miss_stores_result_in_cache(self):
        tts   = self._tts()
        cache = self._cache(None)

        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            await generate_audio_async("Hello.", "shubh", "en", tts, cache)

        cache.put.assert_called_once()
        _, kwargs = cache.put.call_args
        assert kwargs["voice"] == "shubh"
        assert kwargs["language"] == "en"

    async def test_empty_text_returns_placeholder_no_tts(self):
        tts   = self._tts()
        cache = self._cache()

        result = await generate_audio_async("   ", "shubh", "en", tts, cache)

        assert result.audio_bytes == b""
        assert result.duration == 5.0
        tts.generate.assert_not_called()
        cache.get.assert_not_called()

    async def test_trim_called_before_caching(self):
        tts   = self._tts()
        cache = self._cache(None)
        trimmed = _make_clip(2.5)

        with patch("tts.sarvam._trim_silence", return_value=trimmed) as mock_trim:
            await generate_audio_async("Hello.", "shubh", "en", tts, cache)

        mock_trim.assert_called_once()
        _, kwargs = cache.put.call_args
        assert kwargs["clip"] is trimmed

    async def test_cache_not_called_after_hit(self):
        """On cache hit, cache.put is never invoked."""
        cached = _make_clip(2.0)
        cache  = self._cache(cached)
        tts    = self._tts()

        await generate_audio_async("Hello.", "shubh", "en", tts, cache)

        cache.put.assert_not_called()


# ── generate_all_audio ───────────────────────────────────────────────────────

class TestGenerateAllAudio:

    def _tts(self) -> MagicMock:
        tts = MagicMock()
        tts.generate.return_value = _make_clip(3.0)
        return tts

    def _cache(self) -> MagicMock:
        c = MagicMock()
        c.get.return_value = None
        return c

    async def test_all_beats_in_result(self, tmp_path):
        beats = [
            {"beat_id": "intro_1",   "narration": "Hello."},
            {"beat_id": "def_1",     "narration": "The equation."},
            {"beat_id": "summary_1", "narration": "That is all."},
        ]
        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            result = await generate_all_audio(
                beats, "shubh", "en", self._tts(), self._cache(), tmp_path
            )

        assert set(result.keys()) == {"intro_1", "def_1", "summary_1"}

    async def test_failed_beat_excluded_others_present(self, tmp_path):
        beats = [
            {"beat_id": "intro_1",   "narration": "Hello."},
            {"beat_id": "bad_1",     "narration": "This will fail."},
            {"beat_id": "summary_1", "narration": "That is all."},
        ]
        tts = MagicMock()
        cache = self._cache()

        def tts_generate(text, lang):
            if "fail" in text:
                raise RuntimeError("TTS API error")
            return _make_clip(3.0, text=text)

        tts.generate.side_effect = tts_generate

        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            result = await generate_all_audio(
                beats, "shubh", "en", tts, cache, tmp_path
            )

        assert "intro_1"   in result
        assert "bad_1"     not in result   # failed
        assert "summary_1" in result

    async def test_audio_wav_files_written_to_disk(self, tmp_path):
        beats = [
            {"beat_id": "intro_1", "narration": "Hello."},
            {"beat_id": "def_1",   "narration": "The equation."},
        ]
        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            await generate_all_audio(
                beats, "shubh", "en", self._tts(), self._cache(), tmp_path
            )

        assert (tmp_path / "intro_1.wav").exists()
        assert (tmp_path / "def_1.wav").exists()

    async def test_audio_dir_created_when_missing(self, tmp_path):
        audio_dir = tmp_path / "brand_new_dir"
        beats = [{"beat_id": "intro_1", "narration": "Hello."}]

        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            await generate_all_audio(
                beats, "shubh", "en", self._tts(), self._cache(), audio_dir
            )

        assert audio_dir.exists()

    async def test_empty_narration_beat_not_saved_to_disk(self, tmp_path):
        """
        Beats with empty narration produce an empty AudioClip
        (audio_bytes == b'') so no .wav file is written.
        """
        beats = [{"beat_id": "silent_1", "narration": ""}]

        result = await generate_all_audio(
            beats, "shubh", "en", self._tts(), self._cache(), tmp_path
        )

        assert not (tmp_path / "silent_1.wav").exists()

    async def test_returns_dict_keyed_by_beat_id(self, tmp_path):
        beats = [{"beat_id": "x_1", "narration": "Hello."}]
        with patch("tts.sarvam._trim_silence", side_effect=lambda c: c):
            result = await generate_all_audio(
                beats, "shubh", "en", self._tts(), self._cache(), tmp_path
            )

        assert "x_1" in result
        assert isinstance(result["x_1"], AudioClip)
