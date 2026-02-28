"""
Sarvam AI TTS Client — Text-to-Speech wrapper using the official sarvamai SDK.

Supports English and Hindi (+ code-mixed), returns audio bytes + duration metadata,
handles chunking for long narrations.
"""

from __future__ import annotations

import base64
import io
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sarvamai import SarvamAI


@dataclass
class AudioClip:
    """Represents a generated audio clip."""
    audio_bytes: bytes
    duration: float  # seconds
    sample_rate: int = 22050
    text: str = ""

    def save(self, path: str | Path) -> Path:
        """Save audio bytes to a WAV file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.audio_bytes)
        return path


@dataclass
class WordTimestamp:
    """Word-level timestamp for precise sync."""
    word: str
    start: float
    end: float


class SarvamTTS:
    """
    Wraps the Sarvam AI text-to-speech API using the official SDK.

    - Supports English and Hindi (+ code-mixed)
    - Returns audio bytes + duration metadata
    - Handles chunking for long narrations
    """

    # Maximum characters per API request
    MAX_CHUNK_LENGTH = 500

    def __init__(
        self,
        api_key: str,
        voice: str = "shubh",
        model: str = "bulbul:v3",
    ):
        self.api_key = api_key
        self.voice = voice
        self.model = model
        self.client = SarvamAI(api_subscription_key=api_key)

    def generate(self, text: str, language: str = "en") -> AudioClip:
        """
        Generate speech audio from text.

        Returns AudioClip with:
          - .audio_bytes: raw WAV audio data
          - .duration: float (seconds)
          - .sample_rate: int
        """
        if not text.strip():
            return AudioClip(audio_bytes=b"", duration=0.0, text=text)

        # Chunk long texts
        chunks = self._chunk_text(text)

        if len(chunks) == 1:
            return self._generate_single(chunks[0], language)

        # Generate and concatenate multiple chunks
        clips = [self._generate_single(chunk, language) for chunk in chunks]
        return self._concatenate_clips(clips, text)

    def _generate_single(self, text: str, language: str = "en") -> AudioClip:
        """Generate audio for a single text chunk."""
        # Map language codes to Sarvam API format
        lang_map = {
            "en": "en-IN",
            "hi": "hi-IN",
            "en-IN": "en-IN",
            "hi-IN": "hi-IN",
        }
        target_lang = lang_map.get(language, "en-IN")

        response = self.client.text_to_speech.convert(
            text=text,
            target_language_code=target_lang,
            speaker=self.voice,
            model=self.model,
            speech_sample_rate=22050,
            enable_preprocessing=True,
        )

        # The SDK returns response with audios as base64 strings
        audio_b64 = response.audios[0]
        audio_bytes = base64.b64decode(audio_b64)

        # Calculate duration from WAV data
        duration = self._get_wav_duration(audio_bytes)

        return AudioClip(
            audio_bytes=audio_bytes,
            duration=duration,
            sample_rate=22050,
            text=text,
        )

    def generate_segments(self, segments: list[dict], language: str = "en") -> list[AudioClip]:
        """
        Batch generate audio for multiple narration segments.

        Args:
            segments: List of dicts with 'id' and 'narration' keys
            language: Language code

        Returns:
            List of AudioClip objects in the same order
        """
        clips = []
        for seg in segments:
            narration = seg.get("narration", "")
            clip = self.generate(narration.strip(), language)
            clips.append(clip)
        return clips

    def get_word_timestamps(self, text: str) -> list[WordTimestamp]:
        """
        Estimate word-level timestamps based on duration / word count.

        If the Sarvam API supports word-level timestamps natively in
        the future, this method should be updated to use that.
        """
        clip = self.generate(text)
        words = text.split()
        if not words:
            return []

        avg_duration = clip.duration / len(words)
        timestamps = []
        current_time = 0.0

        for word in words:
            timestamps.append(WordTimestamp(
                word=word,
                start=current_time,
                end=current_time + avg_duration,
            ))
            current_time += avg_duration

        return timestamps

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks respecting sentence boundaries."""
        if len(text) <= self.MAX_CHUNK_LENGTH:
            return [text]

        chunks = []
        sentences = text.replace("! ", ".|").replace("? ", ".|").replace(". ", ".|").split("|")

        current_chunk = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_chunk) + len(sentence) + 1 <= self.MAX_CHUNK_LENGTH:
                current_chunk = f"{current_chunk} {sentence}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        return chunks if chunks else [text]

    def _concatenate_clips(self, clips: list[AudioClip], original_text: str) -> AudioClip:
        """Concatenate multiple audio clips into one."""
        if not clips:
            return AudioClip(audio_bytes=b"", duration=0.0, text=original_text)

        # Simple concatenation of WAV data
        all_bytes = b""
        total_duration = 0.0

        for clip in clips:
            all_bytes += clip.audio_bytes
            total_duration += clip.duration

        return AudioClip(
            audio_bytes=all_bytes,
            duration=total_duration,
            sample_rate=clips[0].sample_rate,
            text=original_text,
        )

    @staticmethod
    def _get_wav_duration(audio_bytes: bytes) -> float:
        """Calculate duration of WAV audio data."""
        try:
            with io.BytesIO(audio_bytes) as buf:
                with wave.open(buf, "rb") as wav:
                    frames = wav.getnframes()
                    rate = wav.getframerate()
                    return frames / rate if rate > 0 else 0.0
        except Exception:
            # Fallback: estimate from byte length
            # Assume 16-bit mono 22050Hz
            return len(audio_bytes) / (22050 * 2) if audio_bytes else 0.0
