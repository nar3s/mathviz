"""
render_from_plan.py — Run the full video pipeline from a saved plan JSON.

Skips LLM calls entirely. Useful for iterating on rendering/audio
without burning API credits.

Usage:
    python scripts/render_from_plan.py tests/saved_responses/eigenvalues_full_plan_claude.json
    python scripts/render_from_plan.py tests/saved_responses/eigenvalues_full_plan_claude.json --quality low
    python scripts/render_from_plan.py tests/saved_responses/eigenvalues_full_plan_claude.json --beats 3
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# ── project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("render_from_plan")

from config.settings import settings
from generator.validator import validate_beats
from narration.audio_cache import AudioCache
from narration.sarvam_client import SarvamTTS
from renderer import composer, render_engine, scene_builder
from tts.sarvam import generate_all_audio


async def run(plan_path: Path, quality: str, max_beats: int | None, job_id: str) -> None:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    beats: list[dict] = plan["beats"]

    if max_beats:
        beats = beats[:max_beats]
        log.info("Limiting to first %d beats", max_beats)

    log.info("Plan: '%s' — %d beats", plan.get("title", "?"), len(beats))

    errors = validate_beats(beats)
    if errors:
        log.warning("Validation warnings:\n%s", "\n".join(errors[:10]))

    settings.ensure_dirs()

    # ── TTS ───────────────────────────────────────────────────────────────────
    log.info("Step 1/4: TTS for %d beats…", len(beats))
    if not settings.sarvam_api_key:
        raise ValueError("SARVAM_API_KEY not set in .env")

    tts       = SarvamTTS(api_key=settings.sarvam_api_key, voice="shubh", model=settings.sarvam_model)
    cache     = AudioCache(settings.audio_cache_dir)
    audio_dir = settings.audio_dir / job_id

    audio_clips = await generate_all_audio(
        beats=beats, voice="shubh", language="en",
        tts=tts, cache=cache, audio_dir=audio_dir,
    )

    durations:   dict[str, float] = {}
    audio_paths: dict[str, Path]  = {}
    for beat in beats:
        bid      = beat["beat_id"]
        clip     = audio_clips.get(bid)
        tts_dur  = clip.duration if (clip and clip.duration > 0) else 8.0
        durations[bid]   = max(tts_dur, settings.min_beat_duration)
        wav = audio_dir / f"{bid}.wav"
        if wav.exists():
            audio_paths[bid] = wav

    log.info("Audio done. Beat durations (s): %s",
             {k: round(v, 1) for k, v in durations.items()})

    # ── Scene files ───────────────────────────────────────────────────────────
    log.info("Step 2/4: Building scene files…")
    style     = {"theme": "dark", "accent_color": settings.default_accent_color}
    scene_dir = settings.raw_dir / "scene_files" / job_id

    scene_entries = scene_builder.build_all_scene_files(
        beats=beats, style=style, durations=durations,
        audio_paths=audio_paths, scene_dir=scene_dir,
    )
    log.info("%d scene files written to %s", len(scene_entries), scene_dir)

    # ── Render ────────────────────────────────────────────────────────────────
    log.info("Step 3/4: Rendering %d beats (quality=%s)…", len(scene_entries), quality)
    media_dir    = settings.raw_dir / "media" / job_id
    render_tasks = [
        (bid, fp, cn, media_dir / bid)
        for bid, fp, cn in scene_entries
    ]

    rendered_map = await render_engine.render_all_parallel(
        tasks=render_tasks, quality=quality,
        max_workers=settings.max_render_workers,
    )
    log.info("Rendered %d/%d beats", len(rendered_map), len(beats))

    if not rendered_map:
        raise RuntimeError("All beats failed to render.")

    # ── Merge + concat ────────────────────────────────────────────────────────
    log.info("Step 4/4: Merging and concatenating…")
    merged_dir = settings.raw_dir / "merged" / job_id
    merged_dir.mkdir(parents=True, exist_ok=True)

    beat_order  = [b["beat_id"] for b in beats]
    merge_tasks_coros = []
    for bid in beat_order:
        vp = rendered_map.get(bid)
        if vp is None:
            log.warning("Skipping missing beat: %s", bid)
            continue
        merge_tasks_coros.append(
            composer.merge_segment(vp, audio_paths.get(bid), merged_dir / f"{bid}_merged.mp4")
        )

    merged_results = await asyncio.gather(*merge_tasks_coros, return_exceptions=True)
    final_segments = [r for r in merged_results if not isinstance(r, Exception)]
    for err in merged_results:
        if isinstance(err, Exception):
            log.error("Merge error: %s", err)

    if not final_segments:
        raise RuntimeError("No beats merged successfully.")

    final_path = settings.final_dir / f"{job_id}.mp4"
    await composer.concat_segments(final_segments, final_path)

    log.info("Done! %d/%d beats → %s", len(final_segments), len(beats), final_path)
    return final_path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Render a video from a saved plan JSON.")
    parser.add_argument("plan", type=Path, help="Path to plan JSON file")
    parser.add_argument("--quality", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--beats", type=int, default=None, help="Limit to first N beats")
    parser.add_argument("--job-id", default=None, help="Job ID prefix (default: auto)")
    args = parser.parse_args()

    if not args.plan.exists():
        print(f"ERROR: plan file not found: {args.plan}")
        sys.exit(1)

    job_id = args.job_id or f"plan_{int(time.time())}"
    log.info("Job ID: %s", job_id)

    t0 = time.monotonic()
    asyncio.run(run(args.plan, args.quality, args.beats, job_id))
    log.info("Total time: %.1fs", time.monotonic() - t0)


if __name__ == "__main__":
    main()
