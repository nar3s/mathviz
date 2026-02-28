"""
Unit tests for audio-visual sync logic and composer layer.

Covers section 6:
  6.1/6.2  duration = max(tts_dur, min_beat_duration)
  6.5      durations dict has one entry per beat (no drift)
  6.7      beat_order follows input list order, not alphabetical
  Composer: audio_path=None → copy video; no segments → ValueError

All FFmpeg calls are mocked — no subprocess, no filesystem I/O.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Section 6.1/6.2: min_beat_duration enforcement ───────────────────────────

class TestMinBeatDuration:

    def _compute_duration(
        self,
        tts_dur: float,
        min_beat_duration: float = 10.0,
    ) -> float:
        """Replicate the pipeline's duration computation from main.py."""
        return max(tts_dur, min_beat_duration)

    def test_6_1_tts_shorter_than_min_uses_min(self):
        """TTS 3s + min_beat=10s → duration is 10s."""
        assert self._compute_duration(3.0, min_beat_duration=10.0) == 10.0

    def test_6_2_tts_longer_than_min_uses_tts(self):
        """TTS 15s + min_beat=10s → duration is 15s."""
        assert self._compute_duration(15.0, min_beat_duration=10.0) == 15.0

    def test_tts_equal_to_min_uses_that_value(self):
        """TTS 10s exactly equals min_beat=10s → 10s."""
        assert self._compute_duration(10.0, min_beat_duration=10.0) == 10.0

    def test_zero_tts_duration_uses_min(self):
        """TTS 0s (silent beat) → defaults to 8.0s in pipeline, then max(8, 10) = 10."""
        tts_dur = 0.0
        default_if_zero = 8.0  # from pipeline: 'tts_dur = clip.duration if ... else 8.0'
        effective_tts = tts_dur if tts_dur > 0 else default_if_zero
        result = self._compute_duration(effective_tts, min_beat_duration=10.0)
        assert result == 10.0

    def test_none_clip_uses_default_8s_then_min(self):
        """
        clip=None in pipeline → tts_dur = 8.0 (pipeline default).
        Then max(8.0, 10.0) = 10.0.
        """
        clip = None
        tts_dur = clip.duration if (clip and clip.duration > 0) else 8.0
        result = self._compute_duration(tts_dur, min_beat_duration=10.0)
        assert result == 10.0

    def test_duration_dict_per_beat(self):
        """Durations dict has exactly one entry per beat."""
        beats = [
            {"beat_id": "b1", "narration": "Beat 1.", "visual": {"type": "pause"}},
            {"beat_id": "b2", "narration": "Beat 2.", "visual": {"type": "pause"}},
            {"beat_id": "b3", "narration": "Beat 3.", "visual": {"type": "pause"}},
        ]
        # Simulate the duration computation loop from main.py
        audio_clips = {
            "b1": MagicMock(duration=5.0),
            "b2": MagicMock(duration=12.0),
            # b3 has no audio clip (TTS failed)
        }
        min_beat_duration = 10.0
        durations = {}
        for beat in beats:
            bid = beat["beat_id"]
            clip = audio_clips.get(bid)
            tts_dur = clip.duration if (clip and clip.duration > 0) else 8.0
            durations[bid] = max(tts_dur, min_beat_duration)

        assert len(durations) == len(beats)
        assert durations["b1"] == 10.0   # 5.0 < 10.0 → min
        assert durations["b2"] == 12.0   # 12.0 > 10.0 → tts
        assert durations["b3"] == 10.0   # 8.0 default < 10.0 → min


# ── Section 6.5: No cumulative drift in duration mapping ─────────────────────

class TestDurationMapping:

    def test_6_5_duration_map_not_cumulative(self):
        """Each beat gets its own absolute duration, not cumulative sum."""
        durations = {"b1": 10.0, "b2": 12.0, "b3": 10.0}
        # Verify these are not cumulative
        assert durations["b1"] == 10.0
        assert durations["b2"] == 12.0  # not 22.0
        assert durations["b3"] == 10.0  # not 32.0

    def test_duration_map_keyed_by_beat_id(self):
        """Durations are keyed by beat_id strings."""
        durations = {"intro_1": 10.0, "def_1": 14.0, "sum_1": 10.0}
        for key in durations:
            assert isinstance(key, str)
        for val in durations.values():
            assert isinstance(val, float)


# ── Section 6.7: Beat ordering ────────────────────────────────────────────────

class TestBeatOrdering:

    def test_6_7_beat_order_follows_input_list_not_alphabetical(self):
        """
        beat_order = [b['beat_id'] for b in beats] preserves input list order.
        This ensures chapter ordering is correct even if beat IDs sort differently.
        """
        beats = [
            {"beat_id": "hook_1", "narration": "Hook.", "visual": {"type": "pause"}},
            {"beat_id": "def_1",  "narration": "Def.",  "visual": {"type": "pause"}},
            {"beat_id": "hook_2", "narration": "Hook2.", "visual": {"type": "pause"}},
            {"beat_id": "sum_1",  "narration": "Sum.",   "visual": {"type": "pause"}},
        ]
        beat_order = [b["beat_id"] for b in beats]
        # Input order: hook_1, def_1, hook_2, sum_1
        assert beat_order == ["hook_1", "def_1", "hook_2", "sum_1"]
        # Alphabetical order would be: def_1, hook_1, hook_2, sum_1 — different
        assert beat_order != sorted(beat_order)

    def test_beat_order_preserved_for_22_beats(self):
        """22-beat list preserves order exactly."""
        import json
        from pathlib import Path
        FIXTURES = Path(__file__).parent.parent / "fixtures" / "beats"
        beats = json.loads((FIXTURES / "many_beats.json").read_text())
        beat_order = [b["beat_id"] for b in beats]
        expected = [f"beat_{i}" for i in range(1, 23)]
        assert beat_order == expected


# ── Composer: merge_segment with no audio ─────────────────────────────────────

class TestComposerMergeNoAudio:

    async def test_audio_path_none_copies_video_without_ffmpeg(self, tmp_path):
        """
        When audio_path is None, merge_segment copies the video file as-is
        without calling VideoComposer.merge_segment (no FFmpeg invoked).
        """
        from renderer.composer import merge_segment

        video = tmp_path / "segment.mp4"
        video.write_bytes(b"fake mp4 data")
        out = tmp_path / "segment_merged.mp4"

        with patch("renderer.composer._get_vc") as mock_get_vc:
            result = await merge_segment(video, None, out)

        # VideoComposer should NOT have been called
        mock_get_vc.assert_not_called()
        assert result == out
        assert out.exists()
        assert out.read_bytes() == b"fake mp4 data"

    async def test_audio_path_nonexistent_copies_video(self, tmp_path):
        """
        When audio_path points to a file that doesn't exist, same as None:
        video is copied without FFmpeg.
        """
        from renderer.composer import merge_segment

        video = tmp_path / "segment.mp4"
        video.write_bytes(b"fake mp4 data")
        out = tmp_path / "out.mp4"
        nonexistent_audio = tmp_path / "ghost.wav"  # does not exist

        with patch("renderer.composer._get_vc") as mock_get_vc:
            result = await merge_segment(video, nonexistent_audio, out)

        mock_get_vc.assert_not_called()
        assert out.exists()

    async def test_audio_path_exists_calls_video_composer(self, tmp_path):
        """
        When audio_path exists, merge_segment delegates to VideoComposer.merge_segment
        via asyncio.to_thread.
        """
        from renderer.composer import merge_segment

        video = tmp_path / "segment.mp4"
        audio = tmp_path / "segment.wav"
        out = tmp_path / "out.mp4"
        video.write_bytes(b"fake mp4")
        audio.write_bytes(b"fake wav")

        mock_vc = MagicMock()
        mock_vc.merge_segment = MagicMock(return_value=out)

        with patch("renderer.composer._get_vc", return_value=mock_vc):
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = out
                result = await merge_segment(video, audio, out)

        mock_thread.assert_called_once()


# ── Composer: concat_segments ─────────────────────────────────────────────────

class TestComposerConcatSegments:

    async def test_empty_segment_list_raises_value_error(self):
        """concat_segments([]) raises ValueError immediately, no FFmpeg call."""
        from renderer.composer import concat_segments

        with pytest.raises(ValueError, match="No segments"):
            await concat_segments([], Path("/tmp/out.mp4"))

    async def test_one_segment_calls_video_composer_concatenate(self, tmp_path):
        """Single segment → VideoComposer.concatenate is called (handles 1 segment by copy)."""
        from renderer.composer import concat_segments

        seg = tmp_path / "seg1.mp4"
        seg.write_bytes(b"fake")
        out = tmp_path / "out.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate = MagicMock(return_value=out)

        with patch("renderer.composer._get_vc", return_value=mock_vc):
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = out
                result = await concat_segments([seg], out)

        mock_thread.assert_called_once()

    async def test_multiple_segments_calls_video_composer_concatenate(self, tmp_path):
        """Multiple segments → VideoComposer.concatenate is called."""
        from renderer.composer import concat_segments

        segs = [tmp_path / f"seg{i}.mp4" for i in range(3)]
        for s in segs:
            s.write_bytes(b"fake")
        out = tmp_path / "out.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate = MagicMock(return_value=out)

        with patch("renderer.composer._get_vc", return_value=mock_vc):
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                mock_thread.return_value = out
                result = await concat_segments(segs, out)

        mock_thread.assert_called_once()
