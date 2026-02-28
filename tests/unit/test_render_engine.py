"""
Unit tests for renderer/render_engine.py

All subprocess calls are mocked — no Manim installation required.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from renderer.render_engine import (
    QUALITY_FLAGS,
    _find_rendered_mp4,
    render_all_parallel,
    render_segment_subprocess,
)


# ── Quality flag mapping ─────────────────────────────────────────────────────

class TestQualityFlags:

    def test_low_maps_to_l(self):
        assert QUALITY_FLAGS["low"] == "l"

    def test_medium_maps_to_m(self):
        assert QUALITY_FLAGS["medium"] == "m"

    def test_high_maps_to_h(self):
        assert QUALITY_FLAGS["high"] == "h"

    def test_all_three_qualities_defined(self):
        assert set(QUALITY_FLAGS.keys()) == {"low", "medium", "high"}

    def test_unknown_quality_get_defaults_to_m(self):
        # The production code uses QUALITY_FLAGS.get(quality, "m")
        assert QUALITY_FLAGS.get("ultra", "m") == "m"
        assert QUALITY_FLAGS.get("", "m") == "m"


# ── _find_rendered_mp4 ───────────────────────────────────────────────────────

class TestFindRenderedMp4:

    def test_returns_none_when_no_files(self, tmp_path):
        result = _find_rendered_mp4(tmp_path, "MyScene")
        assert result is None

    def test_finds_exact_class_name_match(self, tmp_path):
        nested = tmp_path / "videos" / "scene" / "720p30"
        nested.mkdir(parents=True)
        target = nested / "MyScene.mp4"
        target.write_bytes(b"fake")

        result = _find_rendered_mp4(tmp_path, "MyScene")
        assert result == target

    def test_falls_back_to_newest_when_no_name_match(self, tmp_path):
        nested = tmp_path / "videos"
        nested.mkdir()

        old = nested / "OldScene.mp4"
        old.write_bytes(b"old")
        time.sleep(0.02)   # ensure distinct mtime
        new = nested / "NewScene.mp4"
        new.write_bytes(b"new")

        result = _find_rendered_mp4(tmp_path, "Missing")
        assert result == new

    def test_prefers_exact_match_over_newest_file(self, tmp_path):
        nested = tmp_path / "videos"
        nested.mkdir()

        # exact-match file created first (older mtime)
        target = nested / "ExactMatch.mp4"
        target.write_bytes(b"target")
        time.sleep(0.02)

        # newer file that does NOT match the class name
        other = nested / "OtherScene.mp4"
        other.write_bytes(b"other")

        result = _find_rendered_mp4(tmp_path, "ExactMatch")
        assert result == target

    def test_searches_recursively(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        target = deep / "DeepScene.mp4"
        target.write_bytes(b"fake")

        result = _find_rendered_mp4(tmp_path, "DeepScene")
        assert result == target


# ── render_segment_subprocess ────────────────────────────────────────────────

class TestRenderSegmentSubprocess:

    def _make_fake_mp4(self, media_dir: Path, class_name: str) -> Path:
        """Create a fake rendered mp4 where Manim would put it."""
        mp4_dir = media_dir / "videos" / "scene" / "720p30"
        mp4_dir.mkdir(parents=True, exist_ok=True)
        mp4 = mp4_dir / f"{class_name}.mp4"
        mp4.write_bytes(b"fake_video_data")
        return mp4

    def _ok_result(self):
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    def _fail_result(self, stderr="error details"):
        r = MagicMock()
        r.returncode = 1
        r.stdout = ""
        r.stderr = stderr
        return r

    def test_returns_mp4_path_on_success(self, tmp_path):
        class_name = "MathVizScene_intro"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()):
            result = render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
                quality="medium",
            )

        assert result.name == f"{class_name}.mp4"

    def test_nonzero_exit_raises_runtime_error(self, tmp_path):
        with patch("renderer.render_engine.subprocess.run", return_value=self._fail_result()):
            with pytest.raises(RuntimeError, match="Manim render failed"):
                render_segment_subprocess(
                    scene_file=tmp_path / "scene.py",
                    class_name="MyScene",
                    media_dir=tmp_path,
                    quality="medium",
                )

    def test_missing_mp4_raises_file_not_found(self, tmp_path):
        # Subprocess succeeds but leaves no .mp4 behind
        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()):
            with pytest.raises(FileNotFoundError, match="no .mp4 found"):
                render_segment_subprocess(
                    scene_file=tmp_path / "scene.py",
                    class_name="MyScene",
                    media_dir=tmp_path,   # empty — no .mp4 here
                    quality="medium",
                )

    def test_uses_sys_executable(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable

    def test_quality_high_flag_in_command(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
                quality="high",
            )

        cmd = mock_run.call_args[0][0]
        assert "-qh" in cmd

    def test_quality_low_flag_in_command(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
                quality="low",
            )

        cmd = mock_run.call_args[0][0]
        assert "-ql" in cmd

    def test_unknown_quality_uses_medium_flag(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
                quality="nonexistent",
            )

        cmd = mock_run.call_args[0][0]
        assert "-qm" in cmd

    def test_utf8_env_vars_set(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
            )

        env = mock_run.call_args[1]["env"]
        assert env.get("PYTHONIOENCODING") == "utf-8"
        assert env.get("PYTHONUTF8") == "1"

    def test_disable_caching_flag_present(self, tmp_path):
        class_name = "MyScene"
        self._make_fake_mp4(tmp_path, class_name)

        with patch("renderer.render_engine.subprocess.run", return_value=self._ok_result()) as mock_run:
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=tmp_path,
            )

        cmd = mock_run.call_args[0][0]
        assert "--disable_caching" in cmd

    def test_media_dir_created_if_missing(self, tmp_path):
        media_dir = tmp_path / "does_not_exist" / "media"
        class_name = "MyScene"

        def side_effect(*args, **kwargs):
            # Simulate Manim creating the mp4 after the media dir is made
            mp4_dir = media_dir / "videos" / "scene" / "720p30"
            mp4_dir.mkdir(parents=True, exist_ok=True)
            (mp4_dir / f"{class_name}.mp4").write_bytes(b"fake")
            r = MagicMock()
            r.returncode = 0
            r.stdout = r.stderr = ""
            return r

        with patch("renderer.render_engine.subprocess.run", side_effect=side_effect):
            render_segment_subprocess(
                scene_file=tmp_path / "scene.py",
                class_name=class_name,
                media_dir=media_dir,
            )

        assert media_dir.exists()


# ── render_all_parallel ──────────────────────────────────────────────────────

class TestRenderAllParallel:

    async def test_successful_renders_returned(self, tmp_path):
        tasks = [
            ("seg1", tmp_path / "s1.py", "Scene1", tmp_path / "m1"),
            ("seg2", tmp_path / "s2.py", "Scene2", tmp_path / "m2"),
        ]
        expected = {
            "seg1": tmp_path / "Scene1.mp4",
            "seg2": tmp_path / "Scene2.mp4",
        }

        async def fake_to_thread(fn, scene_file, class_name, media_dir, quality):
            return expected[f"seg{class_name[-1]}"]

        with patch("renderer.render_engine.asyncio.to_thread", side_effect=fake_to_thread):
            result, errors = await render_all_parallel(tasks, quality="medium", max_workers=4)

        assert result == expected
        assert errors == {}

    async def test_failed_segment_excluded_others_succeed(self, tmp_path):
        tasks = [
            ("seg1", tmp_path / "s1.py", "Scene1", tmp_path / "m1"),
            ("seg2", tmp_path / "s2.py", "Scene2", tmp_path / "m2"),
            ("seg3", tmp_path / "s3.py", "Scene3", tmp_path / "m3"),
        ]

        async def fake_to_thread(fn, scene_file, class_name, media_dir, quality):
            if class_name == "Scene2":
                raise RuntimeError("Manim failed")
            return tmp_path / f"{class_name}.mp4"

        with patch("renderer.render_engine.asyncio.to_thread", side_effect=fake_to_thread):
            result, errors = await render_all_parallel(tasks, quality="medium", max_workers=4)

        assert "seg1" in result
        assert "seg2" not in result     # failed — must be absent
        assert "seg3" in result
        assert len(errors) == 1

    async def test_semaphore_limits_concurrency(self, tmp_path):
        max_workers = 2
        active = [0]
        max_concurrent = [0]

        async def fake_to_thread(fn, scene_file, class_name, media_dir, quality):
            active[0] += 1
            max_concurrent[0] = max(max_concurrent[0], active[0])
            await asyncio.sleep(0.05)   # hold the slot briefly
            active[0] -= 1
            return tmp_path / f"{class_name}.mp4"

        tasks = [
            (f"seg{i}", tmp_path / f"s{i}.py", f"Scene{i}", tmp_path / f"m{i}")
            for i in range(6)
        ]

        with patch("renderer.render_engine.asyncio.to_thread", side_effect=fake_to_thread):
            await render_all_parallel(tasks, quality="medium", max_workers=max_workers)

        assert max_concurrent[0] <= max_workers

    async def test_empty_task_list_returns_empty_dict(self):
        result, errors = await render_all_parallel([], quality="medium", max_workers=4)
        assert result == {}
        assert errors == {}

    async def test_all_fail_returns_empty_dict(self, tmp_path):
        tasks = [
            ("seg1", tmp_path / "s1.py", "Scene1", tmp_path / "m1"),
        ]

        async def always_fail(fn, *args, **kwargs):
            raise RuntimeError("always fails")

        with patch("renderer.render_engine.asyncio.to_thread", side_effect=always_fail):
            result, errors = await render_all_parallel(tasks, quality="medium", max_workers=4)

        assert result == {}
        assert len(errors) == 1
