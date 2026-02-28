"""
Sarvam AI TTS — async beat-level audio generation.

Functions:
  generate_audio_async   — generate audio for a single narration string
  generate_all_audio     — generate audio for all beats concurrently
  _trim_silence          — trim leading/trailing silence from an AudioClip
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from narration.audio_cache import AudioCache
from narration.sarvam_client import AudioClip, SarvamTTS

log = logging.getLogger(__name__)


# ── Silence trimming ──────────────────────────────────────────────────────────

def _trim_silence(clip: AudioClip) -> AudioClip:
    """
    Trim leading and trailing silence from an AudioClip using pydub.

    Falls back gracefully if pydub is not installed or clip is empty.
    Returns the original clip unchanged if no non-silent sections are found.
    """
    if not clip.audio_bytes:
        return clip

    try:
        import io as _io

        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
    except ImportError:
        return clip

    try:
        # audio_bytes may be a complete WAV file (with RIFF header) or raw PCM.
        # Always try WAV first; fall back to raw PCM interpretation.
        raw = clip.audio_bytes
        if raw[:4] == b"RIFF":
            seg = AudioSegment.from_file(_io.BytesIO(raw), format="wav")
        else:
            seg = AudioSegment(
                data=raw,
                sample_width=2,
                frame_rate=clip.sample_rate or 22050,
                channels=1,
            )

        ranges = detect_nonsilent(seg, min_silence_len=100, silence_thresh=-40)
        if not ranges:
            return clip

        start_ms = max(0, ranges[0][0] - 50)
        end_ms = min(len(seg), ranges[-1][1] + 50)
        trimmed = seg[start_ms:end_ms]

        # Export trimmed segment back to WAV bytes
        buf = _io.BytesIO()
        trimmed.export(buf, format="wav")
        new_bytes = buf.getvalue()

        new_dur = len(trimmed) / 1000.0
        return AudioClip(
            audio_bytes=new_bytes,
            duration=new_dur,
            sample_rate=clip.sample_rate,
            text=clip.text,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Silence trimming failed: %s", exc)
        return clip


# ── Single beat audio ─────────────────────────────────────────────────────────

async def generate_audio_async(
    narration: str,
    voice: str,
    language: str,
    tts: SarvamTTS,
    cache: AudioCache,
) -> AudioClip:
    """
    Generate (or retrieve from cache) TTS audio for a single narration string.

    Returns an empty AudioClip (audio_bytes=b"", duration=5.0) for blank narration.
    """
    text = narration.strip()
    if not text:
        return AudioClip(audio_bytes=b"", duration=5.0, text="")

    cached = cache.get(text=text, voice=voice, language=language)
    if cached is not None:
        log.debug("Cache hit for: %.40s", text)
        return cached

    loop = asyncio.get_event_loop()
    raw_clip = await loop.run_in_executor(None, tts.generate, text, language)
    trimmed = _trim_silence(raw_clip)
    cache.put(text=text, voice=voice, language=language, clip=trimmed)
    return trimmed


# ── All beats ─────────────────────────────────────────────────────────────────

async def generate_all_audio(
    beats: list[dict],
    voice: str,
    language: str,
    tts: SarvamTTS,
    cache: AudioCache,
    audio_dir: Path,
) -> dict[str, AudioClip]:
    """
    Generate audio for all beats concurrently.

    Args:
        beats:     List of beat dicts, each with 'beat_id' and 'narration'.
        voice:     Sarvam AI voice ID.
        language:  Narration language code (e.g. "en", "hi").
        tts:       SarvamTTS client instance.
        cache:     AudioCache for hash-based caching.
        audio_dir: Directory where .wav files will be written.

    Returns:
        Dict mapping beat_id → AudioClip (only for beats that succeeded).
    """
    audio_dir = Path(audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)

    async def _generate_one(beat: dict) -> tuple[str, AudioClip | None]:
        bid = beat.get("beat_id", "")
        narration = beat.get("narration", "")
        try:
            clip = await generate_audio_async(narration, voice, language, tts, cache)
            if clip.audio_bytes:
                (audio_dir / f"{bid}.wav").write_bytes(_clip_to_wav(clip))
            return bid, clip
        except Exception as exc:  # noqa: BLE001
            log.error("TTS failed for beat '%s': %s", bid, exc)
            return bid, None

    results = await asyncio.gather(*[_generate_one(b) for b in beats])
    return {bid: clip for bid, clip in results if clip is not None}


# ── WAV serialisation helper ──────────────────────────────────────────────────

def _clip_to_wav(clip: AudioClip) -> bytes:
    """
    Return WAV bytes for the clip's audio.

    If audio_bytes is already a WAV file (starts with RIFF), return it directly.
    Otherwise wrap raw PCM in a WAV container.
    """
    import io
    import wave

    raw = clip.audio_bytes
    if raw[:4] == b"RIFF":
        return raw  # already a complete WAV file

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(clip.sample_rate or 22050)
        wf.writeframes(raw)
    return buf.getvalue()
