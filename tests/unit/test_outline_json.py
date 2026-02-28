"""
Unit tests for outline JSON parsing and validation.

Covers sections 1.1 (JSON robustness) and 1.2 (outline schema validation).
All LLM calls are mocked — no network, no API key.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from generator.planner import _strip_fences, generate_outline
from generator.validator import validate_outline

FIXTURES = Path(__file__).parent.parent / "fixtures" / "outline"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_llm(response_text: str) -> MagicMock:
    """Return a mock LLMClient whose complete() always returns response_text."""
    mock = MagicMock()
    mock.complete = AsyncMock(return_value=response_text)
    return mock


def _mock_llm_sequence(*responses: str) -> MagicMock:
    """Return a mock LLMClient that cycles through responses in order."""
    mock = MagicMock()
    mock.complete = AsyncMock(side_effect=list(responses))
    return mock


def _valid_outline_json() -> str:
    return json.dumps(json.loads((FIXTURES / "valid_simple.json").read_text()))


# ── Section 1.1: JSON parsing robustness ─────────────────────────────────────

class TestOutlineJsonRobustness:

    async def test_1_1_1_truncated_json_retries_and_raises(self):
        """Truncated JSON on every attempt → raises ValueError after all retries."""
        truncated = '{"title": "Test", "chapters": [{"id": "intro", "title": "Intro", "n_beats": 2'
        # All 3 retries return truncated JSON
        llm = _mock_llm_sequence(truncated, truncated, truncated)
        with pytest.raises(ValueError):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_1_1_1_truncated_json_succeeds_on_retry(self):
        """Truncated JSON on first attempt, valid on second → succeeds."""
        truncated = '{"title": "Test", "chapters": ['
        valid = _valid_outline_json()
        llm = _mock_llm_sequence(truncated, valid)
        result = await generate_outline("topic", "en", 5, client=llm)
        assert "chapters" in result

    async def test_1_1_2_markdown_fenced_json_parsed_successfully(self):
        """Markdown-fenced JSON response is stripped and parsed correctly."""
        fenced = f"```json\n{_valid_outline_json()}\n```"
        llm = _mock_llm(fenced)
        result = await generate_outline("topic", "en", 5, client=llm)
        assert result["title"] == "Simple Arithmetic"
        assert len(result["chapters"]) == 3

    async def test_1_1_2_bare_fence_stripped(self):
        """Bare ``` fence (no 'json' label) is also stripped."""
        fenced = f"```\n{_valid_outline_json()}\n```"
        llm = _mock_llm(fenced)
        result = await generate_outline("topic", "en", 5, client=llm)
        assert "chapters" in result

    async def test_1_1_3_trailing_comma_causes_retry(self):
        """JSON with a trailing comma causes json.JSONDecodeError; all retries exhaust → ValueError."""
        bad_json = '{"title": "X", "chapters": [{"id": "a", "title": "A", "n_beats": 1,}]}'
        llm = _mock_llm_sequence(bad_json, bad_json, bad_json)
        with pytest.raises(ValueError):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_1_1_3_trailing_comma_retry_then_valid(self):
        """Trailing comma on first attempt, valid JSON on second → succeeds."""
        bad_json = '{"title": "X", "chapters": [{"id": "a", "title": "A", "n_beats": 1,}]}'
        valid = _valid_outline_json()
        llm = _mock_llm_sequence(bad_json, valid)
        result = await generate_outline("topic", "en", 5, client=llm)
        assert "chapters" in result

    async def test_1_1_4_preamble_text_before_json_fails(self):
        """
        Text preamble before JSON (e.g., "Here's the outline: {...}") currently
        fails because _strip_fences only handles ``` fences, not arbitrary preamble.
        This documents the known behavior: ValueError is raised.
        """
        preamble_response = 'Here\'s the outline:\n' + _valid_outline_json()
        llm = _mock_llm_sequence(preamble_response, preamble_response, preamble_response)
        with pytest.raises(ValueError):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_1_1_5_empty_string_response_raises(self):
        """Empty string response raises ValueError."""
        llm = _mock_llm_sequence("", "", "")
        with pytest.raises(ValueError):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_1_1_6_wrong_shape_raises(self):
        """Valid JSON but wrong schema (no 'chapters') → ValueError from validate_outline."""
        wrong = (FIXTURES / "wrong_schema.json").read_text()
        llm = _mock_llm_sequence(wrong, wrong, wrong)
        with pytest.raises(ValueError):
            await generate_outline("topic", "en", 5, client=llm)

    async def test_strip_fences_standalone(self):
        """_strip_fences is a pure function — test it directly."""
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_fences(raw) == '{"key": "value"}'

    async def test_strip_fences_no_fence_unchanged(self):
        raw = '{"key": "value"}'
        assert _strip_fences(raw) == raw

    async def test_strip_fences_whitespace_trimmed(self):
        raw = '  {"key": "value"}  '
        assert _strip_fences(raw) == '{"key": "value"}'


# ── Section 1.2: Outline schema validation ───────────────────────────────────

class TestOutlineSchemaValidation:

    def test_valid_simple_outline_no_errors(self):
        """valid_simple.json should produce zero validation errors."""
        outline = json.loads((FIXTURES / "valid_simple.json").read_text())
        errors = validate_outline(outline)
        assert errors == []

    def test_valid_complex_outline_no_errors(self):
        """valid_complex.json should produce zero validation errors."""
        outline = json.loads((FIXTURES / "valid_complex.json").read_text())
        errors = validate_outline(outline)
        assert errors == []

    def test_1_2_1_missing_chapters_key(self):
        """Outline with no 'chapters' key fails validation."""
        outline = {"title": "Test"}
        errors = validate_outline(outline)
        assert any("chapters" in e.lower() for e in errors)

    def test_1_2_1_missing_chapters_returns_early(self):
        """validate_outline returns early when chapters is missing."""
        outline = {"title": "Test"}
        errors = validate_outline(outline)
        # Should have at least one error about chapters
        assert len(errors) >= 1

    def test_1_2_2_n_beats_string_fails(self):
        """n_beats as string '3' fails validation — must be int."""
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "title": "Chapter 1", "n_beats": "3"}],
        }
        errors = validate_outline(outline)
        assert any("n_beats" in e for e in errors)

    def test_1_2_3_n_beats_zero_fails(self):
        """n_beats=0 fails validation — must be >= 1."""
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "title": "Chapter 1", "n_beats": 0}],
        }
        errors = validate_outline(outline)
        assert any("n_beats" in e for e in errors)

    def test_1_2_4_chapter_missing_id_fails(self):
        """Chapter without 'id' field fails validation."""
        outline = {
            "title": "Test",
            "chapters": [{"title": "No ID Chapter", "n_beats": 2}],
        }
        errors = validate_outline(outline)
        assert any("id" in e.lower() for e in errors)

    def test_1_2_5_duplicate_chapter_ids_fails(self):
        """Duplicate chapter IDs fail validation."""
        outline = {
            "title": "Test",
            "chapters": [
                {"id": "ch1", "title": "Chapter 1", "n_beats": 2},
                {"id": "ch1", "title": "Chapter 1 Again", "n_beats": 1},
            ],
        }
        errors = validate_outline(outline)
        assert any("duplicate" in e.lower() for e in errors)

    def test_1_2_6_n_beats_negative_fails(self):
        """Negative n_beats fails validation."""
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "title": "Chapter 1", "n_beats": -1}],
        }
        errors = validate_outline(outline)
        assert any("n_beats" in e for e in errors)

    def test_1_2_7_n_beats_100_passes_validate_outline(self):
        """
        validate_outline has no cap on n_beats — n_beats=100 is technically valid
        per the validator. The planner's settings.max_beats_per_chapter=5 caps it
        at planning time, not validation time.
        """
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "title": "Chapter 1", "n_beats": 100}],
        }
        errors = validate_outline(outline)
        # No validation error from validate_outline itself
        assert not any("n_beats" in e for e in errors)

    def test_missing_title_fails(self):
        """Outline without 'title' fails validation."""
        outline = {
            "chapters": [{"id": "ch1", "title": "Chapter 1", "n_beats": 2}],
        }
        errors = validate_outline(outline)
        assert any("title" in e.lower() for e in errors)

    def test_chapters_not_a_list_fails(self):
        """chapters as a dict fails validation."""
        outline = {
            "title": "Test",
            "chapters": {"id": "ch1", "title": "Chapter 1"},
        }
        errors = validate_outline(outline)
        assert any("list" in e.lower() for e in errors)

    def test_chapter_missing_title_fails(self):
        """Chapter without a title fails validation."""
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "n_beats": 2}],
        }
        errors = validate_outline(outline)
        assert any("title" in e.lower() for e in errors)

    def test_chapter_missing_n_beats_fails(self):
        """Chapter without n_beats fails validation."""
        outline = {
            "title": "Test",
            "chapters": [{"id": "ch1", "title": "Chapter 1"}],
        }
        errors = validate_outline(outline)
        assert any("n_beats" in e for e in errors)

    def test_multiple_chapters_multiple_errors_collected(self):
        """validate_outline collects all errors from all chapters."""
        outline = {
            "title": "Test",
            "chapters": [
                {"id": "ch1", "title": "Chapter 1", "n_beats": 0},
                {"id": "ch1", "title": "Chapter 1 Dup", "n_beats": 2},  # duplicate id
            ],
        }
        errors = validate_outline(outline)
        assert len(errors) >= 2

    async def test_generate_outline_raises_on_validation_failure(self):
        """generate_outline raises ValueError when validate_outline fails."""
        bad_outline = {"title": "Test"}  # missing chapters
        llm = _mock_llm_sequence(
            json.dumps(bad_outline),
            json.dumps(bad_outline),
            json.dumps(bad_outline),
        )
        with pytest.raises(ValueError, match="chapters"):
            await generate_outline("topic", "en", 5, client=llm)
