"""
Composer — FFmpeg wrapper for merging audio+video and concatenating segments.

Thin async-friendly layer over the existing composer/ffmpeg_merge.py VideoComposer.
All heavy FFmpeg work runs in asyncio.to_thread() so it doesn't block the API.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from composer.ffmpeg_merge import VideoComposer

log = logging.getLogger(__name__)

_vc: VideoComposer | None = None  # lazy singleton — created on first use


def _get_vc() -> VideoComposer:
    global _vc
    if _vc is None:
        _vc = VideoComposer()
    return _vc


async def merge_segment(
    video_path: Path,
    audio_path: Path | None,
    output_path: Path,
) -> Path:
    """
    Merge a rendered video with its TTS audio track.

    If audio_path is None or doesn't exist, the video is copied as-is
    (silent video, no merge step needed).
    """
    if audio_path is None or not audio_path.exists():
        import shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(video_path), str(output_path))
        return output_path

    return await asyncio.to_thread(
        _get_vc().merge_segment,
        video_path,
        audio_path,
        output_path,
    )


async def concat_segments(
    segment_paths: list[Path],
    output_path: Path,
) -> Path:
    """
    Concatenate all merged segment videos into one final .mp4.

    Uses FFmpeg concat demuxer (-c copy) — no re-encoding, so it's fast.
    All segments must share the same codec, resolution, and fps.
    """
    if not segment_paths:
        raise ValueError("No segments to concatenate")

    log.info("Concatenating %d segments → %s", len(segment_paths), output_path)
    return await asyncio.to_thread(
        _get_vc().concatenate,
        [str(p) for p in segment_paths],
        str(output_path),
        0,   # crossfade=0 → concat demuxer, no re-encode
    )
