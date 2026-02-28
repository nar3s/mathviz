"""
Unit tests for renderer/composer.py

VideoComposer (and therefore FFmpeg) is fully mocked in every test so the
suite runs without FFmpeg installed.  The module-level singleton `_vc` is
patched at the `renderer.composer._vc` level after import.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# renderer.composer creates _vc = VideoComposer() at import time.
# If FFmpeg is not installed VideoComposer.__init__ may raise; guard here.
try:
    from renderer.composer import concat_segments, merge_segment
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="renderer.composer could not be imported (FFmpeg missing?)",
)


def _fake_video(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 128)
    return path


def _fake_audio(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 64)
    return path


# ── merge_segment ────────────────────────────────────────────────────────────

class TestMergeSegment:

    async def test_audio_none_copies_video_as_is(self, tmp_path):
        video  = _fake_video(tmp_path / "video.mp4")
        output = tmp_path / "out.mp4"

        result = await merge_segment(video, audio_path=None, output_path=output)

        assert output.exists()
        assert output.read_bytes() == video.read_bytes()
        assert result == output

    async def test_missing_audio_file_copies_video_as_is(self, tmp_path):
        video  = _fake_video(tmp_path / "video.mp4")
        ghost  = tmp_path / "does_not_exist.wav"   # intentionally absent
        output = tmp_path / "out.mp4"

        result = await merge_segment(video, audio_path=ghost, output_path=output)

        assert output.exists()
        assert output.read_bytes() == video.read_bytes()
        assert result == output

    async def test_present_audio_delegates_to_video_composer(self, tmp_path):
        video  = _fake_video(tmp_path / "video.mp4")
        audio  = _fake_audio(tmp_path / "audio.wav")
        output = tmp_path / "merged.mp4"

        mock_vc = MagicMock()
        mock_vc.merge_segment.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            result = await merge_segment(video, audio_path=audio, output_path=output)

        mock_vc.merge_segment.assert_called_once_with(video, audio, output)

    async def test_no_audio_skips_video_composer_call(self, tmp_path):
        video  = _fake_video(tmp_path / "video.mp4")
        output = tmp_path / "out.mp4"

        mock_vc = MagicMock()

        with patch("renderer.composer._vc", mock_vc):
            await merge_segment(video, audio_path=None, output_path=output)

        mock_vc.merge_segment.assert_not_called()

    async def test_output_parent_dir_created_when_no_audio(self, tmp_path):
        video  = _fake_video(tmp_path / "video.mp4")
        output = tmp_path / "nested" / "deep" / "out.mp4"

        await merge_segment(video, audio_path=None, output_path=output)

        assert output.parent.exists()
        assert output.exists()


# ── concat_segments ──────────────────────────────────────────────────────────

class TestConcatSegments:

    async def test_empty_list_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="No segments"):
            await concat_segments([], output_path=tmp_path / "out.mp4")

    async def test_calls_video_composer_concatenate(self, tmp_path):
        paths  = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            result = await concat_segments(paths, output_path=output)

        mock_vc.concatenate.assert_called_once_with(
            [str(p) for p in paths],
            str(output),
            0,   # crossfade=0 → FFmpeg -c copy
        )

    async def test_crossfade_argument_is_zero(self, tmp_path):
        """crossfade=0 is what triggers the -c copy (no re-encode) path."""
        paths  = [tmp_path / "a.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            await concat_segments(paths, output_path=output)

        _, positional_args, _ = mock_vc.concatenate.mock_calls[0]
        crossfade = positional_args[2]
        assert crossfade == 0

    async def test_segment_paths_converted_to_strings(self, tmp_path):
        paths  = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            await concat_segments(paths, output_path=output)

        call_paths = mock_vc.concatenate.call_args[0][0]
        assert all(isinstance(p, str) for p in call_paths)

    async def test_output_path_converted_to_string(self, tmp_path):
        paths  = [tmp_path / "a.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            await concat_segments(paths, output_path=output)

        call_output = mock_vc.concatenate.call_args[0][1]
        assert isinstance(call_output, str)
        assert call_output == str(output)

    async def test_returns_result_of_concatenate(self, tmp_path):
        paths  = [tmp_path / "a.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            result = await concat_segments(paths, output_path=output)

        assert result == output

    async def test_single_segment_list_accepted(self, tmp_path):
        paths  = [tmp_path / "only.mp4"]
        output = tmp_path / "final.mp4"

        mock_vc = MagicMock()
        mock_vc.concatenate.return_value = output

        with patch("renderer.composer._vc", mock_vc):
            result = await concat_segments(paths, output_path=output)

        mock_vc.concatenate.assert_called_once()
