"""
Unit tests for generator/planner.py (two-phase architecture)

LLM client is fully mocked — no network calls, no real API key needed.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from generator.planner import (
    _strip_fences,
    generate_outline,
    generate_scene_plan,
)

# ── Sample data ───────────────────────────────────────────────────────────────

VALID_OUTLINE = {
    "title": "Eigenvalues and Eigenvectors",
    "total_duration_mins": 5,
    "chapters": [
        {
            "id": "hook",
            "title": "The Mystery Vector",
            "concepts": ["motivation"],
            "n_beats": 2,
        },
        {
            "id": "definition",
            "title": "The Definition",
            "concepts": ["Av = lambda v"],
            "n_beats": 3,
        },
    ],
}

VALID_BEATS_CH1 = [
    {
        "beat_id": "hook_1",
        "narration": "Watch what happens to different vectors.",
        "visual": {"type": "text_card", "text": "Motivation"},
    },
    {
        "beat_id": "hook_2",
        "narration": "Most change direction, but special ones only stretch.",
        "visual": {"type": "pause"},
    },
]

VALID_BEATS_CH2 = [
    {
        "beat_id": "definition_1",
        "narration": "A v equals lambda v defines an eigenvector.",
        "visual": {"type": "equation_reveal", "latex": r"A\vec{v} = \lambda\vec{v}"},
    },
    {
        "beat_id": "definition_2",
        "narration": "Lambda is the eigenvalue.",
        "visual": {"type": "highlight", "target": r"\lambda", "color": "YELLOW"},
    },
    {
        "beat_id": "definition_3",
        "narration": "Rearranging gives the characteristic equation.",
        "visual": {
            "type": "equation_transform",
            "from_latex": r"A\vec{v} = \lambda\vec{v}",
            "to_latex": r"\det(A - \lambda I) = 0",
        },
    },
]


def _mock_llm(response_json) -> MagicMock:
    """Return a mock LLMClient whose complete() returns response_json as JSON text."""
    mock = MagicMock()
    mock.complete = AsyncMock(return_value=json.dumps(response_json))
    return mock


def _mock_llm_multi(*responses) -> MagicMock:
    """Return a mock LLMClient that cycles through multiple responses in order."""
    mock = MagicMock()
    mock.complete = AsyncMock(side_effect=[json.dumps(r) for r in responses])
    return mock


# ── _strip_fences ─────────────────────────────────────────────────────────────

class TestStripFences:

    def test_no_fences_unchanged(self):
        s = '{"title": "Test"}'
        assert _strip_fences(s) == s

    def test_json_fence_stripped(self):
        s = '```json\n{"title": "Test"}\n```'
        assert _strip_fences(s) == '{"title": "Test"}'

    def test_bare_fence_stripped(self):
        s = '```\n{"title": "Test"}\n```'
        assert _strip_fences(s) == '{"title": "Test"}'

    def test_whitespace_stripped(self):
        s = '  {"title": "Test"}  '
        assert _strip_fences(s) == '{"title": "Test"}'

    def test_empty_string(self):
        assert _strip_fences("") == ""


# ── generate_outline ──────────────────────────────────────────────────────────

class TestGenerateOutline:

    async def test_returns_parsed_outline_dict(self):
        llm = _mock_llm(VALID_OUTLINE)
        result = await generate_outline("Eigenvalues", "en", 5, client=llm)

        assert result["title"] == "Eigenvalues and Eigenvectors"
        assert len(result["chapters"]) == 2

    async def test_invalid_json_raises_value_error(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value="not json {{{")

        with pytest.raises(ValueError, match="Outline failed after"):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_outline_missing_chapters_raises(self):
        llm = _mock_llm({"title": "Test"})  # no chapters

        with pytest.raises(ValueError, match="chapters"):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_outline_missing_title_raises(self):
        llm = _mock_llm({"chapters": [{"id": "x", "title": "X", "n_beats": 1}]})

        with pytest.raises(ValueError, match="title"):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_strips_markdown_fences_from_response(self):
        fenced = f"```json\n{json.dumps(VALID_OUTLINE)}\n```"
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=fenced)

        result = await generate_outline("topic", "en", 5, client=llm)

        assert result["title"] == VALID_OUTLINE["title"]

    async def test_topic_in_prompt(self):
        llm = _mock_llm(VALID_OUTLINE)
        await generate_outline("Fourier transforms", "en", 5, client=llm)

        call_args = llm.complete.call_args
        assert "Fourier transforms" in str(call_args)

    async def test_duration_in_prompt(self):
        llm = _mock_llm(VALID_OUTLINE)
        await generate_outline("topic", "en", 8, client=llm)

        call_args = llm.complete.call_args
        assert "8" in str(call_args)

    async def test_hindi_language_adds_language_note(self):
        llm = _mock_llm(VALID_OUTLINE)
        await generate_outline("topic", "hi", 5, client=llm)

        call_args = llm.complete.call_args
        assert "Hindi" in str(call_args)

    async def test_english_no_language_note(self):
        llm = _mock_llm(VALID_OUTLINE)
        await generate_outline("topic", "en", 5, client=llm)

        call_args = llm.complete.call_args
        assert "IMPORTANT" not in str(call_args)

    async def test_missing_api_key_raises_value_error(self):
        with patch("generator.planner.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.llm_provider = "claude"
            mock_settings.llm_model = "claude-opus-4-6"
            mock_settings.outline_output_tokens = 600
            mock_settings.max_chapter_output_tokens = 800
            mock_settings.max_beats_per_chapter = 5
            with pytest.raises(ValueError, match="LLM_API_KEY"):
                await generate_outline("topic", "en", 5)


# ── generate_scene_plan ───────────────────────────────────────────────────────

class TestGenerateScenePlan:

    async def test_returns_title_and_beats(self):
        # Outline call → ch1 call → ch2 call
        llm = _mock_llm_multi(VALID_OUTLINE, VALID_BEATS_CH1, VALID_BEATS_CH2)

        with patch("generator.planner.get_llm_client", return_value=llm):
            result = await generate_scene_plan("Eigenvalues", "en", 5)

        assert result["title"] == "Eigenvalues and Eigenvectors"
        assert "beats" in result
        assert isinstance(result["beats"], list)

    async def test_beats_are_flat_list(self):
        llm = _mock_llm_multi(VALID_OUTLINE, VALID_BEATS_CH1, VALID_BEATS_CH2)

        with patch("generator.planner.get_llm_client", return_value=llm):
            result = await generate_scene_plan("Eigenvalues", "en", 5)

        # ch1 has 2 beats + ch2 has 3 beats = 5 total
        assert len(result["beats"]) == 5

    async def test_all_beats_have_required_fields(self):
        llm = _mock_llm_multi(VALID_OUTLINE, VALID_BEATS_CH1, VALID_BEATS_CH2)

        with patch("generator.planner.get_llm_client", return_value=llm):
            result = await generate_scene_plan("Eigenvalues", "en", 5)

        for beat in result["beats"]:
            assert "beat_id" in beat
            assert "narration" in beat
            assert "visual" in beat

    async def test_chapter_failure_falls_back_to_text_card(self):
        """If a chapter call fails all retries, it returns a fallback beat."""
        # Outline OK, then all chapter calls fail
        llm = MagicMock()
        side_effects = [json.dumps(VALID_OUTLINE)]
        side_effects += ["INVALID JSON {{{"] * (_MAX_RETRIES := 3) * 2  # 2 chapters × 3 retries
        llm.complete = AsyncMock(side_effect=side_effects)

        with patch("generator.planner.get_llm_client", return_value=llm):
            result = await generate_scene_plan("topic", "en", 5)

        # Should have fallback beats (one per chapter)
        assert len(result["beats"]) >= 1
        # Each fallback beat is a text_card
        for beat in result["beats"]:
            assert beat["visual"]["type"] == "text_card"

    async def test_topic_passed_to_outline_prompt(self):
        llm = _mock_llm_multi(VALID_OUTLINE, VALID_BEATS_CH1, VALID_BEATS_CH2)

        with patch("generator.planner.get_llm_client", return_value=llm):
            await generate_scene_plan("Fourier transforms", "en", 5)

        # First call is the outline call
        first_call = llm.complete.call_args_list[0]
        assert "Fourier transforms" in str(first_call)

    async def test_missing_api_key_raises(self):
        with patch("generator.planner.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.llm_provider = "claude"
            mock_settings.llm_model = "claude-opus-4-6"
            mock_settings.outline_output_tokens = 600
            mock_settings.max_chapter_output_tokens = 800
            mock_settings.max_beats_per_chapter = 5
            with pytest.raises(ValueError, match="LLM_API_KEY"):
                await generate_scene_plan("topic")
