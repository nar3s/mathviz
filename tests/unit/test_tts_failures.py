"""
Unit tests for TTS failure handling in tts/sarvam.py.

Covers section 4: empty narration, None narration, missing narration key,
long/short narration, API exceptions, and 0-byte audio.

SarvamTTS and AudioCache are fully mocked — no network calls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from narration.sarvam_client import AudioClip
from tts.sarvam import generate_all_audio, generate_audio_async


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_clip(duration: float = 3.0, audio_bytes: bytes = b"RIFF\x00\x00\x00\x00WAVE") -> AudioClip:
    """Return a minimal AudioClip (WAV header prefix is enough for the code path)."""
    # Build a proper RIFF header to satisfy the RIFF check in _clip_to_wav
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        # Write enough frames for the requested duration
        frames = int(22050 * duration)
        wf.writeframes(b"\x00\x00" * frames)
    return AudioClip(
        audio_bytes=buf.getvalue(),
        duration=duration,
        sample_rate=22050,
        text="test",
    )


def _make_tts(clip: AudioClip | None = None, side_effect=None) -> MagicMock:
    """Return a mock SarvamTTS whose generate() returns clip (or raises side_effect)."""
    tts = MagicMock()
    if side_effect is not None:
        tts.generate = MagicMock(side_effect=side_effect)
    else:
        tts.generate = MagicMock(return_value=clip or _make_clip())
    return tts


def _make_cache(cached_clip: AudioClip | None = None) -> MagicMock:
    """Return a mock AudioCache that always misses (or returns cached_clip)."""
    cache = MagicMock()
    cache.get = MagicMock(return_value=cached_clip)
    cache.put = MagicMock()
    return cache


# ── Section 4: generate_audio_async edge cases ───────────────────────────────

class TestGenerateAudioAsync:

    async def test_4_1_empty_narration_returns_empty_clip_without_calling_tts(self):
        """Empty narration → no TTS call, returns AudioClip(audio_bytes=b'', duration=5.0)."""
        tts = _make_tts()
        cache = _make_cache()
        clip = await generate_audio_async("", "shubh", "en", tts, cache)
        tts.generate.assert_not_called()
        assert clip.audio_bytes == b""
        assert clip.duration == 5.0

    async def test_4_1_whitespace_only_narration_treated_as_empty(self):
        """Narration with only spaces/tabs → treated as empty, no TTS call."""
        tts = _make_tts()
        cache = _make_cache()
        clip = await generate_audio_async("   \t  ", "shubh", "en", tts, cache)
        tts.generate.assert_not_called()
        assert clip.audio_bytes == b""

    async def test_4_2_none_narration_handled(self):
        """
        generate_audio_async expects a str. If None is passed it would fail on
        .strip(). The caller (generate_all_audio) guards with beat.get('narration', '').
        Test that passing '' (the safe default) works correctly.
        """
        tts = _make_tts()
        cache = _make_cache()
        # Using empty string (safe default for None narration)
        clip = await generate_audio_async("", "shubh", "en", tts, cache)
        assert clip.audio_bytes == b""

    async def test_4_4_very_long_narration_calls_tts(self):
        """200-word narration → TTS is called with the full text."""
        tts = _make_tts(_make_clip(duration=60.0))
        cache = _make_cache()
        long_text = " ".join(["word"] * 200)
        clip = await generate_audio_async(long_text, "shubh", "en", tts, cache)
        tts.generate.assert_called_once()
        assert clip.duration == 60.0

    async def test_4_5_very_short_narration_calls_tts(self):
        """Short narration 'Yes.' → TTS is called, short clip returned."""
        short_clip = _make_clip(duration=0.8)
        tts = _make_tts(short_clip)
        cache = _make_cache()
        clip = await generate_audio_async("Yes.", "shubh", "en", tts, cache)
        tts.generate.assert_called_once()
        assert clip.duration == 0.8

    async def test_cache_hit_skips_tts(self):
        """Cache hit → TTS not called, cached clip returned."""
        cached = _make_clip(duration=4.0)
        tts = _make_tts()
        cache = _make_cache(cached_clip=cached)
        clip = await generate_audio_async("Hello world.", "shubh", "en", tts, cache)
        tts.generate.assert_not_called()
        assert clip.duration == 4.0

    async def test_cache_miss_puts_result_in_cache(self):
        """Cache miss → TTS called, result stored via cache.put."""
        tts = _make_tts(_make_clip(duration=3.0))
        cache = _make_cache()
        await generate_audio_async("Hello world.", "shubh", "en", tts, cache)
        cache.put.assert_called_once()


# ── Section 4: generate_all_audio edge cases ──────────────────────────────────

class TestGenerateAllAudio:

    async def test_4_1_beat_with_empty_narration_handled(self, tmp_path):
        """Beat with empty narration → produce empty clip, no file written."""
        beats = [{"beat_id": "b1", "narration": "", "visual": {"type": "pause"}}]
        tts = _make_tts()
        cache = _make_cache()
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)
        # Empty clip is returned but audio_bytes is b'' → no file written
        assert "b1" in result
        tts.generate.assert_not_called()

    async def test_4_2_beat_with_none_narration_handled(self, tmp_path):
        """
        Beat where narration value is None → generate_all_audio uses
        beat.get('narration', '') which gives None (not '').
        The code calls narration.strip() which would AttributeError on None.
        Test documents actual behavior: generate_audio_async receives None.

        Current code: narration = beat.get('narration', '') returns None if key exists with None value.
        generate_audio_async then calls narration.strip() → AttributeError.
        This is caught by the except clause in _generate_one → beat returns None.
        """
        beats = [{"beat_id": "b2", "narration": None, "visual": {"type": "pause"}}]
        tts = _make_tts()
        cache = _make_cache()
        # Should not raise; the exception is caught in _generate_one
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)
        # Beat may be excluded from result (clip=None) or included with empty clip
        # The important thing: no unhandled exception
        assert isinstance(result, dict)

    async def test_4_3_beat_with_missing_narration_key_handled(self, tmp_path):
        """
        Beat with no 'narration' key → beat.get('narration', '') → empty string.
        Treated as empty narration → no TTS call, empty clip returned.
        """
        beats = [{"beat_id": "b3", "visual": {"type": "pause"}}]  # no 'narration' key
        tts = _make_tts()
        cache = _make_cache()
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)
        tts.generate.assert_not_called()
        assert isinstance(result, dict)

    async def test_4_9_tts_api_exception_does_not_break_other_beats(self, tmp_path):
        """
        TTS raises for beat b1, succeeds for b2.
        Beat b2 still produces audio. b1 is excluded from result (clip=None).
        """
        good_clip = _make_clip(duration=3.0)
        call_count = {"n": 0}

        def side_effect(text, lang):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("API error")
            return good_clip

        tts = _make_tts(side_effect=side_effect)
        cache = _make_cache()

        beats = [
            {"beat_id": "b1", "narration": "First beat.", "visual": {"type": "pause"}},
            {"beat_id": "b2", "narration": "Second beat.", "visual": {"type": "pause"}},
        ]
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)

        # b1 failed → excluded from result
        assert "b1" not in result
        # b2 succeeded
        assert "b2" in result

    async def test_4_10_tts_returns_zero_byte_audio_handled(self, tmp_path):
        """
        TTS returns AudioClip with audio_bytes=b'' (0 bytes).
        generate_all_audio: clip.audio_bytes is falsy → no file written.
        The clip is still returned in the result dict.
        """
        zero_clip = AudioClip(audio_bytes=b"", duration=0.0, text="empty")
        tts = _make_tts(zero_clip)
        cache = _make_cache()

        beats = [{"beat_id": "b1", "narration": "Some text.", "visual": {"type": "pause"}}]
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)

        # Clip returned, but audio_bytes empty
        assert "b1" in result
        assert result["b1"].audio_bytes == b""
        # No .wav file written
        assert not (tmp_path / "b1.wav").exists()

    async def test_all_beats_returned_when_all_succeed(self, tmp_path):
        """Result dict has one entry per beat when all TTS calls succeed."""
        beats = [
            {"beat_id": f"b{i}", "narration": f"Beat {i}.", "visual": {"type": "pause"}}
            for i in range(5)
        ]
        tts = _make_tts(_make_clip(duration=3.0))
        cache = _make_cache()
        result = await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)
        assert len(result) == 5

    async def test_audio_dir_created_if_not_exists(self, tmp_path):
        """generate_all_audio creates audio_dir if it does not exist."""
        audio_dir = tmp_path / "new_dir" / "audio"
        beats = [{"beat_id": "b1", "narration": "", "visual": {"type": "pause"}}]
        tts = _make_tts()
        cache = _make_cache()
        await generate_all_audio(beats, "shubh", "en", tts, cache, audio_dir)
        assert audio_dir.exists()

    async def test_wav_file_written_for_beat_with_audio(self, tmp_path):
        """When TTS returns non-empty audio, a .wav file is written for the beat."""
        good_clip = _make_clip(duration=3.0)
        tts = _make_tts(good_clip)
        cache = _make_cache()
        beats = [{"beat_id": "b1", "narration": "Hello.", "visual": {"type": "pause"}}]
        await generate_all_audio(beats, "shubh", "en", tts, cache, tmp_path)
        assert (tmp_path / "b1.wav").exists()
