"""
MathViz Engine — Configuration & Settings.

Loads settings from environment variables / .env file with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# Project root directory (one level up from config/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from .env or environment variables."""

    # ── LLM Provider (provider-agnostic) ──────────────────────────
    llm_provider: str = Field(
        default="claude",
        description="LLM provider: 'claude' (Anthropic) or 'openai' (OpenAI)",
    )
    llm_model: str = Field(
        default="claude-opus-4-6",
        description="Model ID for the selected provider (e.g. claude-opus-4-6, gpt-4o)",
    )
    llm_api_key: str = Field(
        default="",
        description="API key for the selected LLM provider",
    )

    # ── Sarvam AI TTS ──────────────────────────────────────────────
    sarvam_api_key: str = Field(
        default="",
        description="Sarvam AI API key for text-to-speech",
    )
    sarvam_model: str = Field(
        default="bulbul:v3",
        description="Sarvam AI TTS model",
    )

    # ── Defaults ───────────────────────────────────────────────────
    default_voice: str = Field(default="shubh", description="Default TTS voice ID")
    default_language: str = Field(default="en", description="Default narration language")
    default_theme: str = Field(default="dark", description="Default visual theme")
    default_accent_color: str = Field(default="#58C4DD", description="Default accent color (Manim BLUE_C)")
    default_font: str = Field(default="sans-serif", description="Default font family")

    # ── Output Directories ─────────────────────────────────────────
    output_dir: Path = Field(default=PROJECT_ROOT / "output", description="Base output directory")

    # ── Rendering ──────────────────────────────────────────────────
    render_resolution: str = Field(default="1920x1080", description="Video resolution")
    render_fps: int = Field(default=30, description="Video frame rate")
    crossfade_duration: float = Field(default=0.5, description="Crossfade between segments (seconds)")

    # ── Manim ──────────────────────────────────────────────────────
    manim_quality: str = Field(
        default="production_quality",
        description="Manim quality flag: low_quality | medium_quality | high_quality | production_quality",
    )

    # ── Beat timing ───────────────────────────────────────────────
    min_beat_duration: float = Field(
        default=10.0,
        description="Minimum scene duration per beat in seconds (gives viewer time to absorb)",
    )

    # ── Two-phase planning ────────────────────────────────────────
    max_beats_per_chapter: int = Field(
        default=5,
        description="Max beats per chapter call (keeps output tokens bounded)",
    )
    max_chapter_output_tokens: int = Field(
        default=1500,
        description="Max output tokens for each chapter beats call",
    )
    outline_output_tokens: int = Field(
        default=600,
        description="Max output tokens for the Phase-1 outline call",
    )

    # ── Cloudflare R2 Storage (optional) ──────────────────────────
    r2_account_id: str = Field(default="", description="Cloudflare account ID")
    r2_access_key_id: str = Field(default="", description="R2 API token access key ID")
    r2_secret_access_key: str = Field(default="", description="R2 API token secret access key")
    r2_bucket_name: str = Field(default="", description="R2 bucket name")
    r2_public_url: str = Field(default="", description="Public base URL for the R2 bucket (e.g. https://pub-xxx.r2.dev)")

    @property
    def r2_enabled(self) -> bool:
        return bool(self.r2_account_id and self.r2_access_key_id and
                    self.r2_secret_access_key and self.r2_bucket_name and self.r2_public_url)

    # ── FastAPI / Rendering ────────────────────────────────────────
    max_render_workers: int = Field(
        default=4,
        description="Max parallel Manim render workers per job",
    )
    api_host: str = Field(default="0.0.0.0", description="FastAPI host")
    api_port: int = Field(default=8000, description="FastAPI port")

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ── Derived Paths ──────────────────────────────────────────────
    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw"

    @property
    def audio_dir(self) -> Path:
        return self.output_dir / "audio"

    @property
    def final_dir(self) -> Path:
        return self.output_dir / "final"

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "cache"

    @property
    def audio_cache_dir(self) -> Path:
        return self.cache_dir / "audio"

    @property
    def video_cache_dir(self) -> Path:
        return self.cache_dir / "video"

    def ensure_dirs(self) -> None:
        """Create all output directories if they don't exist."""
        for d in [
            self.raw_dir,
            self.audio_dir,
            self.final_dir,
            self.audio_cache_dir,
            self.video_cache_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton instance
settings = Settings()
