"""
MathViz Engine — FastAPI backend.

POST /generate        Submit a topic → returns job_id immediately
GET  /status/{job_id} Poll job progress
GET  /output/{file}   Download the rendered video

Pipeline (runs in background):
  1. LLM → outline (Phase 1) + chapter beats (Phase 2, parallel)
  2. Beat validation (deterministic, zero LLM cost)
  3. TTS for all beats concurrently (asyncio.gather)
  4. Scene .py files generated for each beat
  5. Manim renders all beats in parallel (subprocess + asyncio.to_thread)
  6. FFmpeg merges audio+video per beat
  7. FFmpeg concatenates all beats into final .mp4 (-c copy, no re-encode)
  8. Job status updated with video_url
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

# ── Windows UTF-8 fix ────────────────────────────────────────────────────────
import os as _os
import sys as _sys

_os.environ.setdefault("PYTHONIOENCODING", "utf-8")
_os.environ.setdefault("PYTHONUTF8", "1")
_sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config.settings import settings
from generator.planner import generate_scene_plan
from storage.r2 import upload_json, upload_video
from generator.validator import validate_beats
from narration.audio_cache import AudioCache
from narration.sarvam_client import SarvamTTS
from renderer import composer, render_engine, scene_builder
from tts.sarvam import generate_all_audio

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mathviz.api")

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MathViz Engine",
    description="Generate animated math explainer videos from a topic description.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store ───────────────────────────────────────────────────────
_jobs: dict[str, dict] = {}
_jobs_lock = asyncio.Lock()


async def _update_job(job_id: str, updates: dict) -> None:
    async with _jobs_lock:
        _jobs[job_id].update(updates)


# ── Request / Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic:        str = Field(..., description="Plain-text topic description", min_length=3)
    language:     str = Field("en",     description="Narration language: 'en' or 'hi'")
    duration_mins: int = Field(5,       description="Target video length in minutes (3–10)")
    quality:      str = Field("medium", description="Render quality: 'low' | 'medium' | 'high'")
    voice:        str = Field("shubh",  description="Sarvam AI voice ID")


class GenerateResponse(BaseModel):
    job_id:  str
    status:  str
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Submit a topic for video generation. Returns job_id immediately."""
    settings.ensure_dirs()

    job_id = uuid.uuid4().hex[:10]
    async with _jobs_lock:
        _jobs[job_id] = {
            "job_id":               job_id,
            "status":               "queued",
            "topic":                request.topic,
            "created_at":           time.time(),
            "render_time_seconds":  None,
            "video_url":            None,
            "total_beats":          None,
            "error":                None,
        }

    background_tasks.add_task(_run_pipeline, job_id, request)

    return GenerateResponse(
        job_id=job_id,
        status="queued",
        message=f"Job queued. Poll /status/{job_id} for progress.",
    )


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Poll job progress and retrieve the video URL when complete."""
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        # In-memory store is wiped on container restart.
        # If the video file exists on the persistent volume, reconstruct status.
        final_path = settings.final_dir / f"{job_id}.mp4"
        if final_path.exists():
            return {
                "job_id":    job_id,
                "status":    "completed",
                "video_url": f"/output/{job_id}.mp4",
            }
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@app.get("/output/{filename}")
async def get_output(filename: str):
    """Download a rendered video file."""
    safe_name = Path(filename).name
    path = settings.final_dir / safe_name
    if not path.exists() or path.suffix != ".mp4":
        raise HTTPException(status_code=404, detail="Video not found.")
    return FileResponse(str(path), media_type="video/mp4", filename=safe_name)


@app.get("/jobs")
async def list_jobs():
    """List all jobs (most recent first)."""
    async with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/health")
async def health():
    return {
        "status":   "ok",
        "provider": settings.llm_provider,
        "model":    settings.llm_model,
        "version":  "2.0.0",
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, request: GenerateRequest) -> None:
    """
    Full beat-level video generation pipeline — runs as a FastAPI background task.

    Steps:
      1. LLM two-phase planning → flat list of beats
      2. Beat validation (LaTeX brace check, schema)
      3. TTS → audio for all beats (concurrent)
      4. Scene builder → .py files per beat
      5. Manim → render .mp4 per beat (parallel subprocesses)
      6. FFmpeg → merge audio+video per beat
      7. FFmpeg → concat all beats into final .mp4
    """
    t_start = time.monotonic()

    try:
        # ── Step 1: Two-phase LLM planning ────────────────────────────────
        log.info("[%s] Step 1: Planning '%s' via %s/%s",
                 job_id, request.topic[:60], settings.llm_provider, settings.llm_model)
        await _update_job(job_id, {"status": "planning"})

        plan  = await generate_scene_plan(request.topic, request.language, request.duration_mins)
        beats = plan["beats"]

        log.info("[%s] Plan: '%s', %d beats", job_id, plan["title"], len(beats))

        # Persist LLM plan to R2 (best-effort, non-blocking)
        if settings.r2_enabled:
            try:
                await asyncio.to_thread(
                    upload_json,
                    plan,
                    settings.r2_bucket_name,
                    settings.r2_account_id,
                    settings.r2_access_key_id,
                    settings.r2_secret_access_key,
                    f"plans/{job_id}.json",
                )
            except Exception as exc:
                log.warning("[%s] R2 plan upload failed (non-fatal): %s", job_id, exc)

        # ── Step 2: Beat validation ────────────────────────────────────────
        errors = validate_beats(beats)
        if errors:
            log.warning("[%s] Validation warnings:\n%s", job_id, "\n".join(errors[:10]))

        await _update_job(job_id, {
            "status":      "generating_audio",
            "total_beats": len(beats),
            "title":       plan["title"],
        })

        # ── Step 3: TTS — all beats concurrently ──────────────────────────
        log.info("[%s] Step 3: TTS for %d beats", job_id, len(beats))

        if not settings.sarvam_api_key:
            raise ValueError("SARVAM_API_KEY not set — cannot generate audio.")

        tts   = SarvamTTS(api_key=settings.sarvam_api_key, voice=request.voice, model=settings.sarvam_model)
        cache = AudioCache(settings.audio_cache_dir)
        audio_dir = settings.audio_dir / job_id

        audio_clips = await generate_all_audio(
            beats=beats,
            voice=request.voice,
            language=request.language,
            tts=tts,
            cache=cache,
            audio_dir=audio_dir,
        )

        # Duration map: TTS duration → Manim scene length
        durations:   dict[str, float] = {}
        audio_paths: dict[str, Path]  = {}
        for beat in beats:
            bid  = beat["beat_id"]
            clip = audio_clips.get(bid)
            tts_dur = clip.duration if (clip and clip.duration > 0) else 8.0
            # Enforce minimum so viewers have time to absorb each visual
            durations[bid] = max(tts_dur, settings.min_beat_duration)
            wav = audio_dir / f"{bid}.wav"
            if wav.exists():
                audio_paths[bid] = wav

        log.info("[%s] Audio done. Durations (s): %s",
                 job_id, {k: round(v, 1) for k, v in durations.items()})

        # ── Step 4: Build scene .py files ─────────────────────────────────
        await _update_job(job_id, {"status": "building_scenes"})

        style = {
            "theme":        "dark",
            "accent_color": settings.default_accent_color,
        }

        scene_dir    = settings.raw_dir / "scene_files" / job_id
        scene_entries = scene_builder.build_all_scene_files(
            beats       = beats,
            style       = style,
            durations   = durations,
            audio_paths = audio_paths,
            scene_dir   = scene_dir,
        )
        log.info("[%s] Scene files: %d", job_id, len(scene_entries))

        # ── Step 5: Render all beats in parallel ──────────────────────────
        await _update_job(job_id, {"status": "rendering"})
        log.info("[%s] Step 5: Rendering %d beats (quality=%s)", job_id, len(scene_entries), request.quality)

        media_dir    = settings.raw_dir / "media" / job_id
        render_tasks = [
            (bid, file_path, class_name, media_dir / bid)
            for bid, file_path, class_name in scene_entries
        ]

        rendered_map, render_errors = await render_engine.render_all_parallel(
            tasks       = render_tasks,
            quality     = request.quality,
            max_workers = settings.max_render_workers,
        )

        render_failures = len(beats) - len(rendered_map)
        if render_failures:
            log.warning("[%s] %d/%d beats failed to render", job_id, render_failures, len(beats))
            for beat_id, err in render_errors.items():
                log.error("[%s] Render error [%s]: %s", job_id, beat_id, err[:300])
        if not rendered_map:
            raise RuntimeError(
                f"All {len(beats)} beats failed to render. "
                f"First error: {next(iter(render_errors.values()), 'unknown')[:300]}"
            )

        await _update_job(job_id, {"render_errors": render_errors})

        log.info("[%s] Rendered %d/%d beats", job_id, len(rendered_map), len(beats))

        # ── Step 6: Merge audio + video per beat ──────────────────────────
        await _update_job(job_id, {"status": "composing"})

        merged_dir = settings.raw_dir / "merged" / job_id
        merged_dir.mkdir(parents=True, exist_ok=True)

        beat_order   = [b["beat_id"] for b in beats]
        merge_tasks  = []

        for bid in beat_order:
            video_path = rendered_map.get(bid)
            if video_path is None:
                log.warning("[%s] Skipping missing beat: %s", job_id, bid)
                continue
            out = merged_dir / f"{bid}_merged.mp4"
            merge_tasks.append(
                composer.merge_segment(video_path, audio_paths.get(bid), out)
            )

        merged_results = await asyncio.gather(*merge_tasks, return_exceptions=True)

        final_segments: list[Path] = [
            r for r in merged_results if not isinstance(r, Exception)
        ]
        merge_failures = [str(r) for r in merged_results if isinstance(r, Exception)]
        for f in merge_failures:
            log.error("[%s] Merge failed: %s", job_id, f)

        if not final_segments:
            raise RuntimeError("No beats merged successfully.")

        # ── Step 7: Concatenate into final video ──────────────────────────
        log.info("[%s] Step 7: Concatenating %d beats", job_id, len(final_segments))

        final_path = settings.final_dir / f"{job_id}.mp4"
        await composer.concat_segments(final_segments, final_path)

        render_time = round(time.monotonic() - t_start, 1)
        log.info("[%s] Done in %.1fs → %s", job_id, render_time, final_path)

        # ── Step 8: Upload to R2 (if configured) ──────────────────
        video_url = f"/output/{final_path.name}"
        if settings.r2_enabled:
            try:
                await _update_job(job_id, {"status": "uploading"})
                video_url = await asyncio.to_thread(
                    upload_video,
                    final_path,
                    settings.r2_bucket_name,
                    settings.r2_account_id,
                    settings.r2_access_key_id,
                    settings.r2_secret_access_key,
                    settings.r2_public_url,
                )
                log.info("[%s] Uploaded to R2: %s", job_id, video_url)
            except Exception as exc:
                log.warning("[%s] R2 upload failed (falling back to local URL): %s", job_id, exc)

        beats_dropped = len(beats) - len(final_segments)
        await _update_job(job_id, {
            "status":              "completed",
            "video_url":           video_url,
            "render_time_seconds": render_time,
            "beats_rendered":      len(final_segments),
            "beats_dropped":       beats_dropped,
            "drop_reasons":        merge_failures if merge_failures else None,
        })

    except Exception as exc:
        log.exception("[%s] Pipeline failed: %s", job_id, exc)
        await _update_job(job_id, {
            "status":            "failed",
            "error":             str(exc),
            "render_time_seconds": round(time.monotonic() - t_start, 1),
        })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level="info",
    )
