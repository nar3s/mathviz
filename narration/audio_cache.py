"""
Audio Cache — SHA256 hash-based caching for generated TTS audio.

Avoids redundant API calls when narration text hasn't changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from narration.sarvam_client import AudioClip


class AudioCache:
    """
    Hash-based audio cache.

    Cache key: sha256(narration_text + voice + language)
    Stores .wav files and a manifest.json mapping hashes to metadata.
    """

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.cache_dir / "manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        """Load the cache manifest from disk."""
        if self.manifest_path.exists():
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_manifest(self) -> None:
        """Save the cache manifest to disk."""
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    @staticmethod
    def _compute_key(text: str, voice: str, language: str) -> str:
        """Compute cache key from text + voice + language."""
        content = f"{text}|{voice}|{language}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(
        self,
        text: str,
        voice: str = "meera",
        language: str = "en",
    ) -> AudioClip | None:
        """
        Retrieve a cached audio clip if it exists.

        Returns None if not cached.
        """
        key = self._compute_key(text, voice, language)

        if key not in self.manifest:
            return None

        entry = self.manifest[key]
        audio_path = self.cache_dir / entry["filename"]

        if not audio_path.exists():
            # Cache entry exists but file is missing — remove stale entry
            del self.manifest[key]
            self._save_manifest()
            return None

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        return AudioClip(
            audio_bytes=audio_bytes,
            duration=entry.get("duration", 0.0),
            sample_rate=entry.get("sample_rate", 22050),
            text=text,
        )

    def put(
        self,
        text: str,
        voice: str,
        language: str,
        clip: AudioClip,
    ) -> Path:
        """
        Store an audio clip in the cache.

        Returns the path to the cached file.
        """
        key = self._compute_key(text, voice, language)
        filename = f"{key}.wav"
        audio_path = self.cache_dir / filename

        # Write audio bytes
        with open(audio_path, "wb") as f:
            f.write(clip.audio_bytes)

        # Update manifest
        self.manifest[key] = {
            "filename": filename,
            "duration": clip.duration,
            "sample_rate": clip.sample_rate,
            "text_preview": text[:100],
            "voice": voice,
            "language": language,
        }
        self._save_manifest()

        return audio_path

    def has(self, text: str, voice: str = "meera", language: str = "en") -> bool:
        """Check if text is in the cache."""
        key = self._compute_key(text, voice, language)
        if key in self.manifest:
            audio_path = self.cache_dir / self.manifest[key]["filename"]
            return audio_path.exists()
        return False

    def invalidate(self, text: str, voice: str = "meera", language: str = "en") -> None:
        """Remove a specific entry from the cache."""
        key = self._compute_key(text, voice, language)
        if key in self.manifest:
            audio_path = self.cache_dir / self.manifest[key]["filename"]
            if audio_path.exists():
                audio_path.unlink()
            del self.manifest[key]
            self._save_manifest()

    def clear(self) -> None:
        """Clear the entire cache."""
        for key, entry in self.manifest.items():
            audio_path = self.cache_dir / entry["filename"]
            if audio_path.exists():
                audio_path.unlink()
        self.manifest.clear()
        self._save_manifest()

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self.manifest)
