"""
Unit tests for LaTeX validation edge cases.

Covers section 3: brace matching, command whitelisting, and
validate_beat behavior on various LaTeX content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from generator.validator import check_braces, check_commands, validate_beat

FIXTURES = Path(__file__).parent.parent / "fixtures" / "beats"


# ── check_braces ──────────────────────────────────────────────────────────────

class TestCheckBraces:

    def test_empty_string_balanced(self):
        """Empty string has balanced braces (depth stays 0)."""
        assert check_braces("") is True

    def test_simple_balanced(self):
        assert check_braces(r"\frac{a}{b}") is True

    def test_nested_balanced(self):
        assert check_braces(r"\frac{\partial f}{\partial x}") is True

    def test_unmatched_open_brace(self):
        assert check_braces(r"\frac{a}{b") is False

    def test_unmatched_close_brace(self):
        assert check_braces(r"\frac{a}b}") is False

    def test_close_before_open(self):
        assert check_braces("}x{") is False

    def test_3_4_unmatched_brace_from_fixture(self):
        """bad_latex.json l2: '\\frac{a}{b' → unmatched open brace."""
        beats = json.loads((FIXTURES / "bad_latex.json").read_text())
        l2 = next(b for b in beats if b["beat_id"] == "l2")
        latex = l2["visual"]["latex"]
        # Should have unbalanced braces
        assert check_braces(latex) is False

    def test_3_1_empty_frac_args_balanced(self):
        """\\frac{}{} has balanced braces even though args are empty."""
        assert check_braces(r"\frac{}{}") is True

    def test_plain_text_no_braces(self):
        assert check_braces("x equals lambda v") is True

    def test_dollar_signs_ignored(self):
        """Dollar signs are not brace characters — no effect on depth."""
        assert check_braces("For all $x > 0$") is True

    def test_very_long_equation_balanced(self):
        """Long equation from fixture should be balanced."""
        beats = json.loads((FIXTURES / "bad_latex.json").read_text())
        l5 = next(b for b in beats if b["beat_id"] == "l5")
        latex = l5["visual"]["latex"]
        assert check_braces(latex) is True

    def test_deeply_nested_balanced(self):
        latex = r"\frac{\frac{\frac{a}{b}}{c}}{d}"
        assert check_braces(latex) is True

    def test_deeply_nested_unbalanced(self):
        latex = r"\frac{\frac{\frac{a}{b}{c}}{d}"
        assert check_braces(latex) is False


# ── check_commands ─────────────────────────────────────────────────────────────

class TestCheckCommands:

    def test_no_commands_returns_empty(self):
        assert check_commands("x + y = z") == []

    def test_allowed_command_returns_empty(self):
        assert check_commands(r"\frac{a}{b}") == []

    def test_multiple_allowed_commands_returns_empty(self):
        assert check_commands(r"\frac{\partial f}{\partial x}") == []

    def test_unknown_command_returned(self):
        result = check_commands(r"\usepackage{tikz}")
        assert r"\usepackage" in result

    def test_3_9_usepackage_detected(self):
        """\\usepackage is not in the allowed set → returned as unknown."""
        result = check_commands(r"\usepackage{tikz} x^2")
        assert r"\usepackage" in result

    def test_3_5_unicode_lambda_no_commands(self):
        """Unicode λ has no backslash → check_commands returns empty."""
        result = check_commands("λ + μ = ν")
        assert result == []

    def test_3_10_dollar_signs_no_commands(self):
        """Dollar signs don't register as LaTeX commands."""
        result = check_commands("For all $x > 0$")
        assert result == []

    def test_allowed_greek_letters_empty(self):
        result = check_commands(r"\alpha + \beta = \gamma")
        assert result == []

    def test_allowed_calc_commands_empty(self):
        result = check_commands(r"\int_{-\infty}^{\infty} f(x) dx")
        assert result == []

    def test_multiple_unknown_commands_all_returned(self):
        result = check_commands(r"\usepackage{tikz} \newcommand{\foo}{bar}")
        assert r"\usepackage" in result
        assert r"\newcommand" in result

    def test_single_backslash_escaped_chars_not_matched(self):
        """
        In a Python raw string, \\n is two chars: backslash + n.
        check_commands uses re.findall(r'\\[a-zA-Z]+') so \\n does NOT match
        (it's parsed as literal \n in regular string).
        Test with raw string to be explicit.
        """
        # \lambda is an allowed command
        result = check_commands(r"\lambda")
        assert result == []

    def test_3_2_single_backslash_frac_is_allowed(self):
        """
        In Python source r"\frac{a}{b}" is the string \frac{a}{b} (one backslash).
        check_commands looks for \frac which IS in the allowed set.
        """
        result = check_commands(r"\frac{a}{b}")
        assert result == []


# ── validate_beat LaTeX checks ────────────────────────────────────────────────

class TestValidateBeatLatex:

    def test_3_3_over_escaped_braces_balanced(self):
        """
        \\\\frac{a}{b} in Python source is \\frac{a}{b} at runtime.
        The braces {a} and {b} are balanced → check_braces returns True.
        check_commands finds \\frac which is allowed.
        """
        beat = {
            "beat_id": "oe",
            "narration": "Over-escaped.",
            "visual": {"type": "equation_reveal", "latex": r"\\frac{a}{b}"},
        }
        errors = validate_beat(beat)
        # No brace errors; \\frac not in allowed set but \\\\frac at runtime
        # is just two backslashes + frac — the regex won't find it as a valid command
        # either way. The key point: no BRACE error.
        assert not any("brace" in e.lower() for e in errors)

    def test_3_4_unmatched_brace_reported_by_validate_beat(self):
        """Unmatched brace in latex → validate_beat reports brace error."""
        beat = {
            "beat_id": "ub",
            "narration": "Unmatched.",
            "visual": {"type": "equation_reveal", "latex": r"\frac{a}{b"},
        }
        errors = validate_beat(beat)
        assert any("brace" in e.lower() or "unbalanced" in e.lower() for e in errors)

    def test_3_6_very_long_equation_no_length_limit(self):
        """
        validate_beat has no length limit on latex strings.
        The long equation from fixture should pass brace/command checks.
        """
        beats = json.loads((FIXTURES / "bad_latex.json").read_text())
        l5 = next(b for b in beats if b["beat_id"] == "l5")
        errors = validate_beat(l5)
        # Only brace/command errors — no "too long" error
        assert not any("length" in e.lower() or "too long" in e.lower() for e in errors)

    def test_3_7_latex_in_narration_not_checked(self):
        """
        validate_beat only checks the 'visual' fields, not narration.
        LaTeX-like content in narration does not trigger any error.
        """
        beat = {
            "beat_id": "nar",
            "narration": r"The formula \frac{a}{b} shows the ratio.",
            "visual": {"type": "text_card", "text": "Wave equation."},
        }
        errors = validate_beat(beat)
        assert errors == []

    def test_3_8_empty_latex_string_passes_brace_check(self):
        """
        Empty latex string passes check_braces (empty → depth stays 0 → True).
        validate_beat does not check for non-empty latex — it only checks braces
        when the field is non-empty (the 'if val and not check_braces...' guard).
        So empty latex produces NO brace error from validate_beat.
        """
        beat = {"beat_id": "el", "narration": "Empty.", "visual": {"type": "equation_reveal", "latex": ""}}
        errors = validate_beat(beat)
        # Required field 'latex' IS present (just empty) → no missing field error
        # Empty string skips the brace check → no brace error
        assert not any("brace" in e.lower() for e in errors)
        assert not any("missing" in e.lower() and "latex" in e.lower() for e in errors)

    def test_3_9_usepackage_in_latex_detected_by_check_commands(self):
        """
        check_commands detects \\usepackage as unknown.
        Note: validate_beat calls check_braces but does NOT call check_commands
        directly — it only checks braces. Commands are checked separately.
        """
        latex = r"\usepackage{tikz} x^2"
        unknown = check_commands(latex)
        assert r"\usepackage" in unknown
        # But validate_beat only does brace check for latex fields:
        beat = {
            "beat_id": "up",
            "narration": "Pkg.",
            "visual": {"type": "equation_reveal", "latex": latex},
        }
        errors = validate_beat(beat)
        # Braces are balanced → no brace error from validate_beat
        assert not any("brace" in e.lower() for e in errors)

    def test_3_10_dollar_signs_in_latex_balanced_braces(self):
        """$x > 0$ has no curly braces → check_braces returns True."""
        latex = "For all $x > 0$"
        assert check_braces(latex) is True
        beat = {
            "beat_id": "ds",
            "narration": "Dollar.",
            "visual": {"type": "equation_reveal", "latex": latex},
        }
        errors = validate_beat(beat)
        assert not any("brace" in e.lower() for e in errors)

    def test_from_latex_brace_check_on_equation_transform(self):
        """Unmatched brace in from_latex → brace error in validate_beat."""
        beat = {
            "beat_id": "bt",
            "narration": "Transform.",
            "visual": {
                "type": "equation_transform",
                "from_latex": r"\frac{a}{b",  # unbalanced
                "to_latex": r"2x",
            },
        }
        errors = validate_beat(beat)
        assert any("brace" in e.lower() or "unbalanced" in e.lower() for e in errors)

    def test_statement_latex_brace_check_on_theorem_card(self):
        """Unmatched brace in statement_latex → brace error."""
        beat = {
            "beat_id": "thm",
            "narration": "Theorem.",
            "visual": {
                "type": "theorem_card",
                "theorem_name": "Test",
                "statement_latex": r"a^2 + b^2 = c^{2",  # unbalanced
            },
        }
        errors = validate_beat(beat)
        assert any("brace" in e.lower() or "unbalanced" in e.lower() for e in errors)

    def test_valid_all_types_no_brace_errors(self):
        """None of the beats in valid_all_types.json should have brace errors."""
        beats = json.loads((FIXTURES / "valid_all_types.json").read_text())
        for beat in beats:
            errors = validate_beat(beat)
            brace_errors = [e for e in errors if "brace" in e.lower() or "unbalanced" in e.lower()]
            assert brace_errors == [], f"Unexpected brace error for {beat['beat_id']}: {brace_errors}"
