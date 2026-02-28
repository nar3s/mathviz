"""
Root conftest — sys.path setup + shared WAV helpers and fixtures.
"""

import io
import struct
import sys
import wave
from pathlib import Path

import pytest

# ── Add project root to sys.path so `from renderer.x import ...` works ─────
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── WAV byte helpers (plain functions, not fixtures) ────────────────────────

def make_wav_bytes(
    duration_s: float = 1.0,
    sample_rate: int = 22050,
    amplitude: int = 0,
) -> bytes:
    """
    Create minimal valid WAV bytes.

    amplitude=0  → pure silence
    amplitude>0  → square wave at that PCM amplitude (max 32767)
    """
    num_frames = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # 16-bit
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


def make_wav_with_padding(
    silence_before_ms: int = 200,
    content_ms: int = 1000,
    silence_after_ms: int = 200,
    sample_rate: int = 22050,
    amplitude: int = 8000,
) -> bytes:
    """
    WAV with silence at start/end and a non-silent square-wave in the middle.

    Used for _trim_silence tests; the non-silent section must be above pydub's
    default silence threshold (-45 dB).  amplitude=8000 ≈ -12 dB for 16-bit.
    """
    before_frames = int(sample_rate * silence_before_ms / 1000)
    content_frames = int(sample_rate * content_ms / 1000)
    after_frames   = int(sample_rate * silence_after_ms / 1000)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # silence prefix
        wf.writeframes(b"\x00\x00" * before_frames)
        # non-silent square wave
        data = b""
        for i in range(content_frames):
            val = amplitude if (i % 100) < 50 else -amplitude
            data += struct.pack("<h", val)
        wf.writeframes(data)
        # silence suffix
        wf.writeframes(b"\x00\x00" * after_frames)
    return buf.getvalue()


# ── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_style() -> dict:
    return {"theme": "dark", "accent_color": "#58C4DD", "font": "sans-serif"}


@pytest.fixture
def sample_segment() -> dict:
    """Legacy fixture — keep for backward-compat with any remaining old tests."""
    return {
        "id": "intro",
        "type": "title_card",
        "title": "Introduction",
        "subtitle": "Getting started",
        "narration": "Welcome to the lesson.",
    }


@pytest.fixture
def sample_beat() -> dict:
    """Minimal valid beat dict for builder / scene tests."""
    return {
        "beat_id": "intro_1",
        "narration": "Welcome to the lesson.",
        "visual": {
            "type": "title_card",
            "title": "Introduction",
            "subtitle": "Getting started",
        },
    }


@pytest.fixture
def sample_plan() -> dict:
    """Beat-level scene plan returned by the two-phase planner."""
    return {
        "title": "Eigenvalues and Eigenvectors",
        "beats": [
            {
                "beat_id": "intro_1",
                "narration": "Welcome to the eigenvalues lesson.",
                "visual": {
                    "type": "title_card",
                    "title": "Eigenvalues",
                    "subtitle": "Linear Algebra",
                },
            },
            {
                "beat_id": "def_1",
                "narration": "The eigenvalue equation is A v equals lambda v.",
                "visual": {
                    "type": "equation_reveal",
                    "latex": r"A\vec{v} = \lambda\vec{v}",
                    "label": "Eigenvalue equation",
                },
            },
            {
                "beat_id": "sum_1",
                "narration": "In summary, eigenvalues tell us about scaling.",
                "visual": {
                    "type": "summary_card",
                    "key_points": [r"Eigenvalues scale eigenvectors.", r"\det(A - \lambda I) = 0"],
                },
            },
        ],
    }


@pytest.fixture
def sample_audio_clip():
    from narration.sarvam_client import AudioClip
    return AudioClip(
        audio_bytes=make_wav_bytes(duration_s=3.0),
        duration=3.0,
        sample_rate=22050,
        text="Hello.",
    )
