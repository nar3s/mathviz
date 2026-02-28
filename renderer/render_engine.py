"""
Render Engine — runs Manim scene files via subprocess, in parallel.

Each segment is an independent `manim render` subprocess so Manim's
global state never bleeds between segments or crashes the API server.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Quality flag mapping: user-friendly → Manim CLI flag
QUALITY_FLAGS = {
    "low":    "l",   # 480p15
    "medium": "m",   # 720p30
    "high":   "h",   # 1080p60
}


def _find_rendered_mp4(media_dir: Path, class_name: str) -> Path | None:
    """
    Locate the final .mp4 Manim produced inside its nested media directory.

    Manim writes to: <media_dir>/videos/<stem>/<quality>/<ClassName>.mp4
    Partial files live under partial_movie_files/ — we explicitly exclude them
    so a crashed render never returns a fragment as a valid output.
    """
    mp4_files = [
        f for f in media_dir.rglob("*.mp4")
        if "partial_movie_files" not in f.parts
        and not f.stem.endswith("_temp")
    ]
    if not mp4_files:
        return None

    # Prefer exact class name match
    for f in mp4_files:
        if f.stem == class_name:
            return f

    # Fallback: most recently modified non-partial file
    return max(mp4_files, key=lambda p: p.stat().st_mtime)


def render_segment_subprocess(
    scene_file: Path,
    class_name: str,
    media_dir: Path,
    quality: str = "medium",
) -> Path:
    """
    Render one Manim scene via subprocess and return the output .mp4 path.

    This runs synchronously — call it via asyncio.to_thread() for parallelism.

    Raises:
        RuntimeError: If manim exits non-zero or no .mp4 is produced.
    """
    quality_flag = QUALITY_FLAGS.get(quality, "m")
    media_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "manim", "render",
        str(scene_file),
        class_name,
        f"-q{quality_flag}",
        "--media_dir", str(media_dir),
        "--disable_caching",
    ]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    log.info("Rendering %s (%s quality)…", class_name, quality)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(scene_file.parent.parent),  # project root
        timeout=300,  # 5 min hard limit per beat
    )

    if result.returncode != 0:
        # Surface the Manim error clearly
        raise RuntimeError(
            f"Manim render failed for '{class_name}':\n"
            f"STDOUT: {result.stdout[-2000:]}\n"
            f"STDERR: {result.stderr[-2000:]}"
        )

    output = _find_rendered_mp4(media_dir, class_name)
    if output is None:
        raise FileNotFoundError(
            f"Manim reported success but no .mp4 found in {media_dir}"
        )

    log.info("Rendered: %s → %s", class_name, output)
    return output


async def render_all_parallel(
    tasks: list[tuple[str, Path, str, Path]],
    quality: str = "medium",
    max_workers: int = 4,
) -> dict[str, Path]:
    """
    Render all segments in parallel (bounded by max_workers).

    Args:
        tasks:       List of (segment_id, scene_file, class_name, media_dir).
        quality:     "low" | "medium" | "high".
        max_workers: Max concurrent Manim subprocesses.

    Returns:
        Dict mapping segment_id → rendered .mp4 path.
        Segments that fail are omitted and a warning is logged.
    """
    semaphore = asyncio.Semaphore(max_workers)

    async def _render_one(seg_id: str, scene_file: Path, class_name: str, media_dir: Path):
        async with semaphore:
            return seg_id, await asyncio.to_thread(
                render_segment_subprocess,
                scene_file, class_name, media_dir, quality,
            )

    coros = [_render_one(*t) for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    rendered: dict[str, Path] = {}
    errors: dict[str, str] = {}
    for item in results:
        if isinstance(item, Exception):
            log.error("Render failed: %s", item)
            # Extract segment id from the exception message if possible
            msg = str(item)
            for seg_id, _, class_name, _ in tasks:
                if class_name in msg:
                    errors[seg_id] = msg[:500]
                    break
            else:
                errors[f"unknown_{len(errors)}"] = msg[:500]
            continue
        seg_id, mp4_path = item
        rendered[seg_id] = mp4_path

    return rendered, errors
