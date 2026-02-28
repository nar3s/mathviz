"""
Unit tests for normalize_text and resolve_color in scenes/base.py.

normalize_text replaces ASCII approximations with proper Unicode.
resolve_color maps color name strings to Manim color objects.

No Manim rendering occurs — pure Python logic tests.
"""

from __future__ import annotations

import pytest

from scenes.base import normalize_text, resolve_color


# ── normalize_text ────────────────────────────────────────────────────────────

class TestNormalizeText:

    def test_not_equal_slash_replaced(self):
        """=/ → ≠"""
        assert normalize_text("a =/ b") == "a ≠ b"

    def test_not_equal_bang_replaced(self):
        """!= → ≠"""
        assert normalize_text("a != b") == "a ≠ b"

    def test_arrow_right_replaced(self):
        """-> → →"""
        assert normalize_text("a -> b") == "a → b"

    def test_double_arrow_replaced(self):
        """=> → ⇒"""
        assert normalize_text("a => b") == "a ⇒ b"

    def test_greater_equal_replaced(self):
        """>= → ≥"""
        assert normalize_text("x >= 0") == "x ≥ 0"

    def test_less_equal_replaced(self):
        """<= → ≤"""
        assert normalize_text("x <= 1") == "x ≤ 1"

    def test_tilde_equal_replaced(self):
        """~= → ≈"""
        assert normalize_text("a ~= b") == "a ≈ b"

    def test_ellipsis_replaced(self):
        """... → …"""
        assert normalize_text("and so on...") == "and so on…"

    def test_plain_text_unchanged(self):
        text = "The eigenvalue equation"
        assert normalize_text(text) == text

    def test_already_unicode_unchanged(self):
        """Unicode characters already present are left as-is."""
        text = "λ + μ → ν"
        result = normalize_text(text)
        assert "λ" in result
        assert "μ" in result
        assert "→" in result

    def test_multiple_replacements_in_one_string(self):
        """Multiple replacements applied to a single string."""
        text = "a != b and x >= 0 so a -> b"
        result = normalize_text(text)
        assert "≠" in result
        assert "≥" in result
        assert "→" in result

    def test_empty_string_returns_empty(self):
        assert normalize_text("") == ""

    def test_no_replacement_needed(self):
        """String with none of the trigger patterns stays unchanged."""
        text = "Hello world: 1 + 1 = 2"
        assert normalize_text(text) == text

    def test_slash_equal_not_equal_replaced(self):
        """/= → ≠"""
        assert normalize_text("a /= b") == "a ≠ b"

    def test_left_arrow_replaced(self):
        """<- → ←"""
        assert normalize_text("a <- b") == "a ← b"

    def test_double_arrow_bidirectional_partial_replacement(self):
        """
        <=> is NOT handled atomically. The replacement list processes <= before <=>,
        so '<=' in '<=> ' is replaced first, producing '≤>' rather than '⟺'.
        This documents actual behavior: <=> → ≤>
        """
        result = normalize_text("<=>")
        # <= is applied before <=> in the list, so we get ≤> not ⟺
        assert result == "≤>"

    def test_replacement_order_less_equal_before_bidir(self):
        """
        Because the replacement list applies '<=' before '<=>', the string '<='
        inside '<=>' is replaced first. Document the actual processing order.
        """
        result = normalize_text("<=>")
        # <= replaces to ≤, leaving ≤>
        assert "≤" in result

    def test_repeated_pattern_all_replaced(self):
        """All instances of the pattern in the string are replaced."""
        result = normalize_text("a != b and c != d")
        assert result == "a ≠ b and c ≠ d"


# ── resolve_color ─────────────────────────────────────────────────────────────

class TestResolveColor:

    def test_known_color_name_resolved(self):
        """Uppercase 'BLUE' resolves to the Manim BLUE color object."""
        from manim import BLUE
        result = resolve_color("BLUE")
        assert result is BLUE

    def test_lowercase_color_name_resolved(self):
        """Case-insensitive: 'blue' also resolves."""
        from manim import BLUE
        result = resolve_color("blue")
        assert result is BLUE

    def test_yellow_resolved(self):
        from manim import YELLOW
        assert resolve_color("YELLOW") is YELLOW

    def test_hex_string_passed_through(self):
        """#RRGGBB hex string is returned as-is."""
        result = resolve_color("#FF0000")
        assert result == "#FF0000"

    def test_hex_with_alpha_passed_through(self):
        """#RRGGBBAA hex string (9 chars) is passed through."""
        result = resolve_color("#FF0000FF")
        assert result == "#FF0000FF"

    def test_unknown_name_returns_fallback(self):
        """Unknown color name returns the fallback (default YELLOW)."""
        from manim import YELLOW
        result = resolve_color("NOTACOLOR")
        assert result is YELLOW

    def test_unknown_name_with_custom_fallback(self):
        """Unknown color name with custom fallback returns that fallback."""
        from manim import BLUE
        result = resolve_color("NOTACOLOR", fallback=BLUE)
        assert result is BLUE

    def test_non_string_passed_through(self):
        """Non-string value (already a Manim color object) is passed through."""
        from manim import GREEN
        assert resolve_color(GREEN) is GREEN

    def test_alias_cyan_resolves(self):
        """'CYAN' is an alias → should not return the fallback."""
        from manim import YELLOW
        result = resolve_color("CYAN")
        assert result is not YELLOW  # should resolve to something valid

    def test_alias_magenta_resolves(self):
        from manim import YELLOW
        result = resolve_color("MAGENTA")
        assert result is not YELLOW

    def test_white_resolved(self):
        from manim import WHITE
        assert resolve_color("WHITE") is WHITE

    def test_empty_string_falls_back(self):
        """Empty string → not in map, not a valid hex → returns fallback."""
        from manim import YELLOW
        result = resolve_color("")
        assert result is YELLOW

    def test_short_hex_falls_back(self):
        """Short hex '#FFF' is not exactly 7 or 9 chars → falls back."""
        from manim import YELLOW
        result = resolve_color("#FFF")
        assert result is YELLOW
