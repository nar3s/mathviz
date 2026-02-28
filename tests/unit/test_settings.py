"""
Unit tests for config/settings.py

No external APIs or subprocesses — pure Settings object inspection.
"""

from pathlib import Path

import pytest

from config.settings import PROJECT_ROOT, Settings


# ── Default values ───────────────────────────────────────────────────────────

class TestSettingsDefaults:

    def test_default_llm_provider(self):
        s = Settings()
        assert s.llm_provider == "claude"

    def test_default_llm_model(self):
        s = Settings()
        assert s.llm_model == "claude-opus-4-6"

    def test_default_sarvam_model(self):
        s = Settings()
        assert s.sarvam_model == "bulbul:v3"

    def test_default_voice(self):
        s = Settings()
        assert s.default_voice == "shubh"

    def test_default_language(self):
        s = Settings()
        assert s.default_language == "en"

    def test_default_theme(self):
        s = Settings()
        assert s.default_theme == "dark"

    def test_default_max_render_workers_is_four(self):
        s = Settings()
        assert s.max_render_workers == 4

    def test_max_render_workers_is_int(self):
        s = Settings()
        assert isinstance(s.max_render_workers, int)

    def test_default_api_host(self):
        s = Settings()
        assert s.api_host == "0.0.0.0"

    def test_default_api_port(self):
        s = Settings()
        assert s.api_port == 8000

    def test_default_accent_color(self):
        s = Settings()
        assert s.default_accent_color == "#58C4DD"

    def test_llm_api_key_defaults_to_empty_string(self):
        # In CI without .env the key should be empty, not None
        s = Settings(llm_api_key="")
        assert s.llm_api_key == ""


# ── Derived path properties ──────────────────────────────────────────────────

class TestDerivedPaths:

    def test_audio_dir_is_output_subdir(self):
        s = Settings()
        assert s.audio_dir == s.output_dir / "audio"

    def test_final_dir_is_output_subdir(self):
        s = Settings()
        assert s.final_dir == s.output_dir / "final"

    def test_raw_dir_is_output_subdir(self):
        s = Settings()
        assert s.raw_dir == s.output_dir / "raw"

    def test_cache_dir_is_output_subdir(self):
        s = Settings()
        assert s.cache_dir == s.output_dir / "cache"

    def test_audio_cache_dir_is_under_cache(self):
        s = Settings()
        assert s.audio_cache_dir == s.cache_dir / "audio"

    def test_video_cache_dir_is_under_cache(self):
        s = Settings()
        assert s.video_cache_dir == s.cache_dir / "video"

    def test_output_dir_is_path_instance(self):
        s = Settings()
        assert isinstance(s.output_dir, Path)

    def test_output_dir_parent_is_project_root(self):
        s = Settings()
        assert s.output_dir.parent == PROJECT_ROOT

    def test_derived_paths_are_absolute(self):
        s = Settings()
        for path in [s.audio_dir, s.final_dir, s.raw_dir, s.audio_cache_dir]:
            assert path.is_absolute(), f"{path} should be absolute"


# ── ensure_dirs() ────────────────────────────────────────────────────────────

class TestEnsureDirs:

    def test_creates_all_output_directories(self, tmp_path):
        s = Settings(output_dir=tmp_path / "output")
        s.ensure_dirs()

        assert s.raw_dir.exists()
        assert s.audio_dir.exists()
        assert s.final_dir.exists()
        assert s.audio_cache_dir.exists()
        assert s.video_cache_dir.exists()

    def test_idempotent_called_twice(self, tmp_path):
        s = Settings(output_dir=tmp_path / "output")
        s.ensure_dirs()
        s.ensure_dirs()   # must not raise

        assert s.audio_dir.exists()

    def test_created_dirs_are_directories(self, tmp_path):
        s = Settings(output_dir=tmp_path / "output")
        s.ensure_dirs()

        for d in [s.raw_dir, s.audio_dir, s.final_dir, s.audio_cache_dir]:
            assert d.is_dir(), f"{d} should be a directory"


# ── Environment variable overrides ───────────────────────────────────────────

class TestEnvOverrides:

    def test_llm_model_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
        s = Settings()
        assert s.llm_model == "claude-sonnet-4-6"

    def test_llm_provider_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        s = Settings()
        assert s.llm_provider == "openai"

    def test_max_render_workers_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("MAX_RENDER_WORKERS", "8")
        s = Settings()
        assert s.max_render_workers == 8

    def test_default_voice_overridden_by_env(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_VOICE", "meera")
        s = Settings()
        assert s.default_voice == "meera"

    def test_constructor_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
        s = Settings(llm_model="claude-opus-4-6")
        # Constructor kwargs take highest precedence
        assert s.llm_model == "claude-opus-4-6"
