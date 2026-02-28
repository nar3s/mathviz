"""
Unit tests for generator/validator.py

All tests are deterministic — no LLM calls, no network, no filesystem I/O.
"""

import pytest

from generator.validator import (
    ALLOWED_COMMANDS,
    ALLOWED_BEAT_TYPES,
    check_braces,
    check_commands,
    validate_beat,
    validate_beats,
    validate_outline,
)


# ── check_braces ─────────────────────────────────────────────────────────────

class TestCheckBraces:

    def test_empty_string_is_balanced(self):
        assert check_braces("") is True

    def test_matched_single_pair(self):
        assert check_braces(r"\frac{a}{b}") is True

    def test_unmatched_open_brace(self):
        assert check_braces(r"\frac{a}{b") is False

    def test_unmatched_close_brace(self):
        assert check_braces(r"\frac{a}b}") is False

    def test_nested_balanced(self):
        assert check_braces(r"\sqrt{\frac{a}{b}}") is True

    def test_nested_unbalanced(self):
        assert check_braces(r"\sqrt{\frac{a}{b}") is False

    def test_simple_equation_no_braces(self):
        assert check_braces(r"x = y + z") is True

    def test_matrix_balanced(self):
        latex = r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"
        assert check_braces(latex) is True

    def test_extra_closing_returns_false(self):
        assert check_braces("a}b") is False

    def test_only_open_braces(self):
        assert check_braces("{{{") is False

    def test_only_close_braces(self):
        assert check_braces("}}}") is False

    def test_interleaved_ok(self):
        assert check_braces("{a{b}c}") is True


# ── check_commands ────────────────────────────────────────────────────────────

class TestCheckCommands:

    def test_all_allowed_returns_empty(self):
        assert check_commands(r"\frac{a}{b}") == []

    def test_unknown_command_detected(self):
        result = check_commands(r"\unknowncmd{x}")
        assert r"\unknowncmd" in result

    def test_multiple_unknowns(self):
        result = check_commands(r"\badcmd{x} + \anotherbad{y}")
        assert r"\badcmd" in result
        assert r"\anotherbad" in result

    def test_known_greek_letters_pass(self):
        assert check_commands(r"\lambda + \alpha + \sigma") == []

    def test_known_calculus_operators_pass(self):
        assert check_commands(r"\int_{0}^{1} \frac{dx}{dt}") == []

    def test_known_linear_algebra_pass(self):
        assert check_commands(r"\vec{v} + \hat{n} + \det") == []

    def test_empty_string_returns_empty(self):
        assert check_commands("") == []

    def test_no_backslash_commands(self):
        assert check_commands("x + y = z") == []


# ── validate_beat ─────────────────────────────────────────────────────────────

class TestValidateBeat:

    def _valid_beat(self, **overrides) -> dict:
        beat = {
            "beat_id": "ch1_1",
            "narration": "This is a sentence.",
            "visual": {"type": "equation_reveal", "latex": r"f(x) = x^2"},
        }
        beat.update(overrides)
        return beat

    def test_valid_beat_has_no_errors(self):
        assert validate_beat(self._valid_beat()) == []

    def test_missing_beat_id(self):
        beat = self._valid_beat()
        del beat["beat_id"]
        errors = validate_beat(beat)
        assert any("beat_id" in e for e in errors)

    def test_empty_narration(self):
        errors = validate_beat(self._valid_beat(narration="   "))
        assert any("narration" in e for e in errors)

    def test_missing_visual(self):
        beat = self._valid_beat()
        del beat["visual"]
        errors = validate_beat(beat)
        assert any("visual" in e for e in errors)

    def test_unknown_beat_type(self):
        beat = self._valid_beat()
        beat["visual"]["type"] = "flying_pigs"
        errors = validate_beat(beat)
        assert any("flying_pigs" in e for e in errors)

    def test_missing_required_latex_field(self):
        beat = {
            "beat_id": "ch1_2",
            "narration": "Here is an equation.",
            "visual": {"type": "equation_reveal"},  # missing "latex"
        }
        errors = validate_beat(beat)
        assert any("latex" in e for e in errors)

    def test_unbalanced_braces_in_latex(self):
        beat = self._valid_beat()
        beat["visual"]["latex"] = r"\frac{a}{b"  # missing closing }
        errors = validate_beat(beat)
        assert any("brace" in e.lower() for e in errors)

    def test_all_beat_types_accepted(self):
        for beat_type in ALLOWED_BEAT_TYPES:
            # Just check no "unknown type" error
            beat = {"beat_id": "x_1", "narration": "test", "visual": {"type": beat_type}}
            errs = validate_beat(beat)
            assert not any("unknown" in e for e in errs), f"Type '{beat_type}' rejected: {errs}"

    def test_pause_needs_no_visual_fields(self):
        beat = {"beat_id": "p1", "narration": "Pause.", "visual": {"type": "pause"}}
        errors = validate_beat(beat)
        assert errors == []

    def test_title_card_requires_title(self):
        beat = {
            "beat_id": "t1",
            "narration": "Intro.",
            "visual": {"type": "title_card"},  # missing "title"
        }
        errors = validate_beat(beat)
        assert any("title" in e for e in errors)

    def test_highlight_requires_target_and_color(self):
        beat = {
            "beat_id": "h1",
            "narration": "Highlight lambda.",
            "visual": {"type": "highlight", "target": r"\lambda"},  # missing "color"
        }
        errors = validate_beat(beat)
        assert any("color" in e for e in errors)


# ── validate_beats ────────────────────────────────────────────────────────────

class TestValidateBeats:

    def _beat(self, bid: str) -> dict:
        return {
            "beat_id": bid,
            "narration": f"Narration for {bid}.",
            "visual": {"type": "text_card", "text": bid},
        }

    def test_empty_list_has_no_errors(self):
        assert validate_beats([]) == []

    def test_all_valid_beats_no_errors(self):
        beats = [self._beat("ch1_1"), self._beat("ch1_2"), self._beat("ch1_3")]
        assert validate_beats(beats) == []

    def test_duplicate_beat_id_detected(self):
        beats = [self._beat("ch1_1"), self._beat("ch1_1")]
        errors = validate_beats(beats)
        assert any("Duplicate" in e for e in errors)

    def test_errors_collected_across_all_beats(self):
        beats = [
            {"beat_id": "a", "narration": "", "visual": {"type": "pause"}},
            {"beat_id": "b", "narration": "ok", "visual": {"type": "unknown_type"}},
        ]
        errors = validate_beats(beats)
        assert len(errors) >= 2


# ── validate_outline ──────────────────────────────────────────────────────────

class TestValidateOutline:

    def _valid_outline(self) -> dict:
        return {
            "title": "Eigenvalues",
            "total_duration_mins": 5,
            "chapters": [
                {"id": "intro",  "title": "Introduction",  "concepts": ["motivation"], "n_beats": 2},
                {"id": "theory", "title": "Core Theory",   "concepts": ["Av=lv"],     "n_beats": 3},
            ],
        }

    def test_valid_outline_has_no_errors(self):
        assert validate_outline(self._valid_outline()) == []

    def test_missing_title(self):
        o = self._valid_outline()
        del o["title"]
        errors = validate_outline(o)
        assert any("title" in e for e in errors)

    def test_missing_chapters(self):
        errors = validate_outline({"title": "Test"})
        assert any("chapters" in e for e in errors)

    def test_empty_chapters_list(self):
        errors = validate_outline({"title": "Test", "chapters": []})
        assert any("chapters" in e for e in errors)

    def test_chapter_missing_id(self):
        o = self._valid_outline()
        del o["chapters"][0]["id"]
        errors = validate_outline(o)
        assert any("id" in e for e in errors)

    def test_chapter_missing_title(self):
        o = self._valid_outline()
        del o["chapters"][0]["title"]
        errors = validate_outline(o)
        assert any("title" in e for e in errors)

    def test_chapter_missing_n_beats(self):
        o = self._valid_outline()
        del o["chapters"][0]["n_beats"]
        errors = validate_outline(o)
        assert any("n_beats" in e for e in errors)

    def test_duplicate_chapter_ids(self):
        o = self._valid_outline()
        o["chapters"][1]["id"] = "intro"  # duplicate
        errors = validate_outline(o)
        assert any("Duplicate" in e for e in errors)

    def test_invalid_n_beats_zero(self):
        o = self._valid_outline()
        o["chapters"][0]["n_beats"] = 0
        errors = validate_outline(o)
        assert any("n_beats" in e for e in errors)

    def test_saved_eigenvalues_outline_valid(self):
        """Integration check: the saved fixture passes validation."""
        import json
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "saved_responses" / "outlines" / "eigenvalues_outline.json"
        if fixture.exists():
            outline = json.loads(fixture.read_text())
            assert validate_outline(outline) == []

    def test_saved_eigenvalues_beats_valid(self):
        """Integration check: the saved beats fixture passes validation."""
        import json
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "saved_responses" / "chapters" / "eigenvalues_ch2_beats.json"
        if fixture.exists():
            beats = json.loads(fixture.read_text())
            assert validate_beats(beats) == []
