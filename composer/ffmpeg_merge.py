"""
FFmpeg Merge — Video composition using FFmpeg.

Handles per-segment video+audio merging, concatenation with crossfade,
subtitle embedding, and final encoding.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class VideoComposer:
    """
    Final assembly using FFmpeg.

    Pipeline:
    1. For each segment: merge segment.mp4 + segment_audio.wav
    2. Concatenate all segments with optional crossfade
    3. Add optional intro/outro bumper
    4. Add optional subtitles (.srt)
    5. Encode final output (1080p, h264, AAC)
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self) -> None:
        """Check that FFmpeg is available."""
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg and ensure it's in PATH. "
                "Download from: https://ffmpeg.org/download.html"
            )

    def merge_segment(
        self,
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Merge a video segment with its audio track.

        If the audio is longer than the video, the video is padded by
        freezing the last frame (using tpad filter). If video is longer
        than audio, it is trimmed to audio duration.
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)

        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_merged.mp4"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get durations to decide padding strategy
        video_dur = self._get_duration(video_path)
        audio_dur = self._get_duration(audio_path)

        if audio_dur > video_dur + 0.5:
            # Audio is longer: pad video by freezing last frame
            pad_duration = audio_dur - video_dur + 0.5
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-vf", f"tpad=stop_mode=clone:stop_duration={pad_duration:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                str(output_path),
            ]
        else:
            # Video is equal or longer: merge and trim to audio duration.
            # Re-encode video (ultrafast) so all segments share the same codec,
            # FPS, and timebase — required for glitch-free -c copy concat.
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-r", "30",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-t", f"{audio_dur:.2f}",
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

        return output_path

    def concatenate(
        self,
        segment_paths: list[str | Path],
        output_path: str | Path,
        crossfade: float = 0.5,
    ) -> Path:
        """
        Concatenate multiple video segments.

        Uses ffmpeg concat demuxer for no-crossfade, or xfade filter for crossfade.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(segment_paths) == 0:
            raise ValueError("No segments to concatenate")

        if len(segment_paths) == 1:
            # Just copy the single file
            import shutil
            shutil.copy2(str(segment_paths[0]), str(output_path))
            return output_path

        if crossfade <= 0:
            return self._concat_demuxer(segment_paths, output_path)
        else:
            return self._concat_xfade(segment_paths, output_path, crossfade)

    def _concat_demuxer(
        self,
        segment_paths: list[str | Path],
        output_path: Path,
    ) -> Path:
        """Concatenate using concat demuxer (no crossfade)."""
        # Create concat file listing
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for path in segment_paths:
                # Escape single quotes in path
                escaped = str(Path(path).resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
            concat_file = f.name

        try:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-reset_timestamps", "1",   # fixes PTS discontinuities between segments
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
        finally:
            Path(concat_file).unlink(missing_ok=True)

        return output_path

    def _concat_xfade(
        self,
        segment_paths: list[str | Path],
        output_path: Path,
        crossfade: float,
    ) -> Path:
        """Concatenate using xfade filter for crossfade transitions."""
        if len(segment_paths) == 2:
            # Simple two-input xfade
            duration = self._get_duration(segment_paths[0])
            offset = max(0, duration - crossfade)

            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(segment_paths[0]),
                "-i", str(segment_paths[1]),
                "-filter_complex",
                f"xfade=transition=fade:duration={crossfade}:offset={offset}",
                "-c:a", "aac",
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg xfade failed: {result.stderr}")
            return output_path

        # For 3+ segments, chain xfade filters or fall back to demuxer
        return self._concat_demuxer(segment_paths, output_path)

    def add_subtitles(
        self,
        video_path: str | Path,
        srt_path: str | Path,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Burn subtitles into video.

        ffmpeg -i video.mp4 -vf subtitles=subs.srt output.mp4
        """
        video_path = Path(video_path)
        srt_path = Path(srt_path)

        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}_subtitled.mp4"
        output_path = Path(output_path)

        # Escape path for subtitle filter
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_escaped}'",
            "-c:a", "copy",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg subtitles failed: {result.stderr}")

        return output_path

    def encode_final(
        self,
        input_path: str | Path,
        output_path: str | Path,
        resolution: str = "1920x1080",
        fps: int = 30,
    ) -> Path:
        """Final encode with quality settings."""
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = resolution.split("x")

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {result.stderr}")

        return output_path

    def _get_duration(self, video_path: str | Path) -> float:
        """Get the duration of a video file using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 5.0  # fallback
