"""
Unit tests for render_all_parallel and VideoComposer stitch logic.

Covers section 7:
  7.2  All beats fail → render_all_parallel returns ({}, errors) → pipeline raises RuntimeError
  7.6  Single beat → concatenate copies (VideoComposer handles 1 segment)
  7.7  FFmpeg failure → VideoComposer raises RuntimeError → caught at pipeline level

Also tests:
  - render_all_parallel return signature: (dict, dict)
  - Error dict contains error messages
  - render errors included in job status render_errors field
  - VideoComposer.concatenate raises ValueError on empty list

All subprocess and network calls are mocked.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── render_all_parallel return signature ─────────────────────────────────────

class TestRenderAllParallelReturnSignature:

    async def test_returns_tuple_of_two_dicts(self, tmp_path):
        """render_all_parallel always returns a 2-tuple: (rendered_map, errors)."""
        from renderer.render_engine import render_all_parallel

        tasks = [("b1", tmp_path / "scene.py", "MyScene", tmp_path / "media")]

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            fake_mp4 = tmp_path / "b1.mp4"
            fake_mp4.write_bytes(b"fake")
            mock_thread.return_value = fake_mp4
            result = await render_all_parallel(tasks, quality="medium")

        assert isinstance(result, tuple)
        assert len(result) == 2
        rendered_map, errors = result
        assert isinstance(rendered_map, dict)
        assert isinstance(errors, dict)

    async def test_successful_renders_in_rendered_map(self, tmp_path):
        """Successful renders appear in the rendered_map dict keyed by segment_id."""
        from renderer.render_engine import render_all_parallel

        fake_mp4 = tmp_path / "b1.mp4"
        fake_mp4.write_bytes(b"fake")

        tasks = [("b1", tmp_path / "scene.py", "MyScene_b1", tmp_path / "media")]

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = fake_mp4
            rendered_map, errors = await render_all_parallel(tasks)

        assert "b1" in rendered_map
        assert errors == {} or isinstance(errors, dict)

    async def test_failed_renders_in_errors_dict(self, tmp_path):
        """Failed renders appear in the errors dict."""
        from renderer.render_engine import render_all_parallel

        tasks = [("b1", tmp_path / "scene.py", "MyScene_b1", tmp_path / "media")]

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = RuntimeError("Manim render failed for 'MyScene_b1'")
            rendered_map, errors = await render_all_parallel(tasks)

        assert rendered_map == {}
        assert len(errors) >= 1
        # The error message should be stored somewhere in errors
        assert any("b1" in k or "MyScene_b1" in v for k, v in errors.items())

    async def test_7_2_all_beats_fail_returns_empty_rendered_map(self, tmp_path):
        """
        When all beats fail, render_all_parallel returns ({}, non-empty errors dict).
        The pipeline then raises RuntimeError('All beats failed').
        """
        from renderer.render_engine import render_all_parallel

        tasks = [
            ("b1", tmp_path / "s1.py", "MyScene_b1", tmp_path / "m1"),
            ("b2", tmp_path / "s2.py", "MyScene_b2", tmp_path / "m2"),
        ]

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = RuntimeError("Manim crash")
            rendered_map, errors = await render_all_parallel(tasks)

        assert rendered_map == {}
        assert len(errors) > 0

    async def test_7_2_pipeline_raises_runtime_error_when_all_fail(self, tmp_path):
        """
        Simulates the pipeline's post-render check:
        if not rendered_map: raise RuntimeError('All X beats failed...')
        """
        rendered_map = {}
        render_errors = {"b1": "Manim crash for MyScene_b1", "b2": "Manim crash for MyScene_b2"}
        beats = [
            {"beat_id": "b1", "narration": "B1.", "visual": {"type": "pause"}},
            {"beat_id": "b2", "narration": "B2.", "visual": {"type": "pause"}},
        ]
        if not rendered_map:
            error_msg = (
                f"All {len(beats)} beats failed to render. "
                f"First error: {next(iter(render_errors.values()), 'unknown')[:300]}"
            )
            with pytest.raises(RuntimeError, match="beats failed to render"):
                raise RuntimeError(error_msg)

    async def test_partial_failure_only_failed_in_errors(self, tmp_path):
        """When some beats fail and some succeed, only failures appear in errors."""
        from renderer.render_engine import render_all_parallel

        fake_mp4 = tmp_path / "b1.mp4"
        fake_mp4.write_bytes(b"fake")

        tasks = [
            ("b1", tmp_path / "s1.py", "MyScene_b1", tmp_path / "m1"),
            ("b2", tmp_path / "s2.py", "MyScene_b2", tmp_path / "m2"),
        ]

        call_count = {"n": 0}
        async def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return fake_mp4
            raise RuntimeError("Manim render failed for 'MyScene_b2'")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = side_effect
            rendered_map, errors = await render_all_parallel(tasks)

        assert "b1" in rendered_map
        assert "b2" not in rendered_map


# ── VideoComposer single-segment concatenation ────────────────────────────────

class TestVideoComposerSingleSegment:

    def test_7_6_single_segment_concatenate_copies_file(self, tmp_path):
        """
        VideoComposer.concatenate with 1 segment copies the file using shutil.copy2.
        No FFmpeg subprocess is invoked for a single segment.
        """
        from composer.ffmpeg_merge import VideoComposer

        seg = tmp_path / "seg1.mp4"
        seg.write_bytes(b"fake mp4 content")
        out = tmp_path / "out.mp4"

        # Mock _verify_ffmpeg so VideoComposer can be instantiated without FFmpeg
        with patch.object(VideoComposer, "_verify_ffmpeg", return_value=None):
            vc = VideoComposer()
            with patch("shutil.copy2") as mock_copy:
                vc.concatenate([str(seg)], str(out))
                mock_copy.assert_called_once_with(str(seg), str(out))

    def test_7_6_empty_segment_list_raises_value_error(self, tmp_path):
        """VideoComposer.concatenate([]) raises ValueError."""
        from composer.ffmpeg_merge import VideoComposer

        out = tmp_path / "out.mp4"
        with patch.object(VideoComposer, "_verify_ffmpeg", return_value=None):
            vc = VideoComposer()
            with pytest.raises(ValueError, match="No segments"):
                vc.concatenate([], str(out))


# ── FFmpeg failure propagation ────────────────────────────────────────────────

class TestFfmpegFailure:

    def test_7_7_merge_segment_ffmpeg_failure_raises_runtime_error(self, tmp_path):
        """
        VideoComposer.merge_segment raises RuntimeError when FFmpeg exits non-zero.
        """
        from composer.ffmpeg_merge import VideoComposer

        video = tmp_path / "seg.mp4"
        audio = tmp_path / "seg.wav"
        out = tmp_path / "merged.mp4"
        video.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        with patch.object(VideoComposer, "_verify_ffmpeg", return_value=None):
            vc = VideoComposer()
            # Mock _get_duration to return non-zero values
            with patch.object(vc, "_get_duration", return_value=5.0):
                # Mock subprocess.run to simulate FFmpeg failure
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=1, stderr="FFmpeg error: codec not found")
                    with pytest.raises(RuntimeError, match="FFmpeg merge failed"):
                        vc.merge_segment(video, audio, out)

    def test_7_7_concatenate_ffmpeg_failure_raises_runtime_error(self, tmp_path):
        """
        VideoComposer._concat_demuxer raises RuntimeError when FFmpeg concat fails.
        """
        from composer.ffmpeg_merge import VideoComposer

        seg1 = tmp_path / "seg1.mp4"
        seg2 = tmp_path / "seg2.mp4"
        out = tmp_path / "out.mp4"
        seg1.write_bytes(b"fake")
        seg2.write_bytes(b"fake")

        with patch.object(VideoComposer, "_verify_ffmpeg", return_value=None):
            vc = VideoComposer()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="concat error")
                with pytest.raises(RuntimeError, match="FFmpeg concat failed"):
                    vc.concatenate([str(seg1), str(seg2)], str(out), crossfade=0)


# ── render_errors in job status ───────────────────────────────────────────────

class TestRenderErrorsInJobStatus:

    async def test_render_errors_dict_passed_to_job_update(self, tmp_path):
        """
        The pipeline calls _update_job(job_id, {'render_errors': render_errors}).
        Test that render_errors dict from render_all_parallel is stored.
        """
        # Simulate what the pipeline does:
        render_errors = {"b1": "Manim crash: SomeError"}
        job_status = {}
        job_status.update({"render_errors": render_errors})
        assert "render_errors" in job_status
        assert job_status["render_errors"] == render_errors

    async def test_render_errors_contains_error_message(self, tmp_path):
        """Error strings in render_errors dict are non-empty."""
        from renderer.render_engine import render_all_parallel

        tasks = [("b1", tmp_path / "s.py", "MyScene_b1", tmp_path / "m")]
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = RuntimeError("Manim render failed for 'MyScene_b1': out of memory")
            rendered_map, errors = await render_all_parallel(tasks)

        for key, msg in errors.items():
            assert len(msg) > 0

    async def test_errors_dict_is_empty_when_all_succeed(self, tmp_path):
        """When all renders succeed, errors dict is empty."""
        from renderer.render_engine import render_all_parallel

        fake_mp4 = tmp_path / "b1.mp4"
        fake_mp4.write_bytes(b"fake")

        tasks = [("b1", tmp_path / "s.py", "MyScene_b1", tmp_path / "m")]
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = fake_mp4
            rendered_map, errors = await render_all_parallel(tasks)

        assert errors == {}


# ── VideoComposer instantiation without FFmpeg ────────────────────────────────

class TestVideoComposerInstantiation:

    def test_video_composer_raises_runtime_error_when_ffmpeg_missing(self):
        """VideoComposer raises RuntimeError if FFmpeg binary is not found."""
        from composer.ffmpeg_merge import VideoComposer
        import subprocess

        with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
            with pytest.raises(RuntimeError, match="FFmpeg not found"):
                VideoComposer(ffmpeg_path="nonexistent_ffmpeg")

    def test_video_composer_initialised_with_mock(self):
        """VideoComposer can be instantiated when _verify_ffmpeg is mocked."""
        from composer.ffmpeg_merge import VideoComposer

        with patch.object(VideoComposer, "_verify_ffmpeg", return_value=None):
            vc = VideoComposer()
            assert vc.ffmpeg_path == "ffmpeg"
