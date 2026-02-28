"""
BaseEngineeringScene — Foundation for all MathViz beat scenes.

Provides consistent styling, theme setup, title cards, equation display,
axes helpers, transitions, safe-zone fit helpers, and audio sync.
"""

from __future__ import annotations

from pathlib import Path

from manim import (
    BLACK,
    BLUE,
    BLUE_B,
    BLUE_C,
    BLUE_D,
    BLUE_E,
    DOWN,
    GOLD,
    GOLD_C,
    GREEN,
    GREEN_B,
    GREEN_C,
    GREY,
    LEFT,
    LIGHT_BROWN,
    MAROON,
    ORANGE,
    PINK,
    PURPLE,
    PURPLE_B,
    PURPLE_C,
    RED,
    RED_B,
    RED_C,
    RIGHT,
    TEAL,
    TEAL_B,
    TEAL_C,
    UP,
    WHITE,
    YELLOW,
    YELLOW_C,
    Axes,
    Create,
    FadeIn,
    FadeOut,
    MathTex,
    Mobject,
    Rectangle,
    Scene,
    Text,
    Tex,
    VGroup,
    Write,
    config as manim_config,
)
import numpy as np

# ── Centralized color resolver ────────────────────────────────────────────────
# Maps any color name the LLM might produce to a valid Manim color.
# Case-insensitive. Hex strings (#RRGGBB) are passed through unchanged.
_GLOBAL_COLOR_MAP: dict[str, object] = {
    # Core palette
    "BLUE":    BLUE,
    "BLUE_B":  BLUE_B,
    "BLUE_C":  BLUE_C,
    "BLUE_D":  BLUE_D,
    "BLUE_E":  BLUE_E,
    "GREEN":   GREEN,
    "GREEN_B": GREEN_B,
    "GREEN_C": GREEN_C,
    "RED":     RED,
    "RED_B":   RED_B,
    "RED_C":   RED_C,
    "YELLOW":  YELLOW,
    "YELLOW_C": YELLOW_C,
    "WHITE":   WHITE,
    "BLACK":   BLACK,
    "ORANGE":  ORANGE,
    "TEAL":    TEAL,
    "TEAL_B":  TEAL_B,
    "TEAL_C":  TEAL_C,
    "PURPLE":  PURPLE,
    "PURPLE_B": PURPLE_B,
    "PURPLE_C": PURPLE_C,
    "GOLD":    GOLD,
    "GOLD_C":  GOLD_C,
    "PINK":    PINK,
    "MAROON":  MAROON,
    "GREY":    GREY,
    "GRAY":    GREY,
    "LIGHT_BROWN": LIGHT_BROWN,
    # Common aliases the LLM often produces
    "CYAN":    TEAL_C,      # Manim has no CYAN; TEAL_C is the closest
    "AQUA":    TEAL_B,
    "MAGENTA": PINK,
    "VIOLET":  PURPLE_C,
    "INDIGO":  PURPLE,
    "LIME":    GREEN_B,
    "NAVY":    BLUE_E,
    "CORAL":   RED_B,
    "BROWN":   LIGHT_BROWN,
    "SILVER":  GREY,
    "GOLD_YELLOW": GOLD_C,
}


# ── Text normalizer ───────────────────────────────────────────────────────────
# Replace ASCII approximations the LLM commonly outputs with proper Unicode
# so Manim's Text() renders them correctly.
_TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    ("=/",  "≠"),   # not-equal (LLM sometimes writes =/ instead of ≠)
    ("!=",  "≠"),
    ("/=",  "≠"),
    ("~=",  "≈"),
    (">=",  "≥"),
    ("<=",  "≤"),
    ("->",  "→"),
    ("<-",  "←"),
    ("=>",  "⇒"),
    ("<=>", "⟺"),
    ("...", "…"),
]


def normalize_text(text: str) -> str:
    """Replace common ASCII approximations with proper Unicode characters."""
    for ascii_form, unicode_char in _TEXT_REPLACEMENTS:
        text = text.replace(ascii_form, unicode_char)
    return text


def resolve_color(name: str | object, fallback=YELLOW) -> object:
    """
    Resolve a color name to a Manim color object.

    Accepts:
    - Manim color name (case-insensitive): "cyan", "YELLOW", "BLUE_C"
    - Hex string: "#FFD700"
    - Already-resolved Manim color object (passed through)

    Unknown names fall back to `fallback` (default: YELLOW).
    """
    if not isinstance(name, str):
        return name  # already a Manim color / array
    upper = name.strip().upper()
    if upper in _GLOBAL_COLOR_MAP:
        return _GLOBAL_COLOR_MAP[upper]
    if upper.startswith("#") and len(upper) in (7, 9):
        return name  # valid hex — pass through
    return fallback


class BaseEngineeringScene(Scene):
    """
    Base scene for all MathViz beat visualizations.

    Provides:
    - Consistent styling (colors, fonts, background)
    - Title card animation
    - Equation display helpers
    - Axes setup
    - Transitions
    - Auto-fit: prevents mobjects from going off-screen
    - Audio integration via add_sound()
    - Duration padding so every beat matches its TTS audio exactly
    """

    theme: str = "dark"
    accent_color: str = "#58C4DD"   # BLUE_C
    equation_font_size: int = 36
    title_font_size: int = 48
    subtitle_font_size: int = 28
    total_duration: float = 10.0
    audio_file: str | None = None

    MARGIN_X = 0.85
    MARGIN_Y = 0.88

    def setup_theme(self) -> None:
        if self.theme == "dark":
            self.camera.background_color = "#1e1e2e"
        else:
            self.camera.background_color = "#fafafa"

    def add_audio(self) -> float:
        """Add audio track if available. Returns total_duration for pacing."""
        if self.audio_file and Path(self.audio_file).exists():
            self.add_sound(str(self.audio_file))
        return self.total_duration

    # ── Safe-zone fit ────────────────────────────────────────────────

    def fit(self, mob: Mobject, margin_x: float | None = None, margin_y: float | None = None) -> Mobject:
        """Scale mob down if it exceeds the safe zone. Never scales up."""
        mx = margin_x or self.MARGIN_X
        my = margin_y or self.MARGIN_Y
        max_w = manim_config.frame_width * mx
        max_h = manim_config.frame_height * my
        if mob.width > max_w:
            mob.scale(max_w / mob.width)
        if mob.height > max_h:
            mob.scale(max_h / mob.height)
        return mob

    def safe_tex(self, latex: str, font_size: int = 36, **kwargs) -> MathTex:
        tex = MathTex(latex, font_size=font_size, **kwargs)
        self.fit(tex)
        return tex

    def safe_text(self, text: str, font_size: int = 28, **kwargs) -> Text:
        t = Text(normalize_text(text), font_size=font_size, **kwargs)
        self.fit(t)
        return t

    # ── Title card ───────────────────────────────────────────────────

    def show_title(self, title: str, subtitle: str | None = None, duration: float = 3.0) -> VGroup:
        title_text = self.safe_text(title, font_size=self.title_font_size, color=WHITE, weight="BOLD")
        group = VGroup(title_text)
        if subtitle:
            sub = self.safe_text(subtitle, font_size=self.subtitle_font_size, color=self.accent_color)
            sub.next_to(title_text, DOWN, buff=0.4)
            group.add(sub)
        self.fit(group)
        group.move_to([0, 0, 0])
        self.play(FadeIn(group, shift=UP * 0.5), run_time=1.0)
        self.wait(max(0.3, duration - 2.0))
        self.play(FadeOut(group, shift=UP * 0.5), run_time=1.0)
        return group

    # ── Equation display ─────────────────────────────────────────────

    def show_equation(self, latex: str, label: str | None = None, position=UP * 0.5,
                      animate: bool = True, font_size: int | None = None) -> VGroup:
        fs = font_size or self.equation_font_size
        equation = self.safe_tex(latex, font_size=fs, color=WHITE)
        group = VGroup(equation)
        if label:
            label_text = self.safe_text(label, font_size=fs - 8, color=self.accent_color, slant="ITALIC")
            label_text.next_to(equation, DOWN, buff=0.3)
            group.add(label_text)
        self.fit(group)
        group.move_to(position)
        if animate:
            self.play(Write(equation), run_time=1.5)
            if label:
                self.play(FadeIn(label_text), run_time=0.5)
        else:
            self.add(group)
        return group

    def highlight_equation_part(self, equation: MathTex, indices: list[int], color=YELLOW) -> None:
        for idx in indices:
            if idx < len(equation):
                self.play(equation[idx].animate.set_color(color), run_time=0.5)

    # ── Axes ─────────────────────────────────────────────────────────

    def create_axes(self, x_range=(-5, 5, 1), y_range=(-5, 5, 1),
                    x_length: float = 8, y_length: float = 6, **kwargs) -> Axes:
        return Axes(
            x_range=list(x_range), y_range=list(y_range),
            x_length=x_length, y_length=y_length,
            axis_config={"color": WHITE, "include_numbers": True, "font_size": 20},
            **kwargs,
        )

    def create_labeled_axes(self, x_range=(-5, 5, 1), y_range=(-5, 5, 1),
                            x_label: str = "x", y_label: str = "y", **kwargs):
        axes = self.create_axes(x_range, y_range, **kwargs)
        labels = VGroup(axes.get_x_axis_label(x_label), axes.get_y_axis_label(y_label))
        return axes, labels

    # ── Transitions ──────────────────────────────────────────────────

    def transition_to_next(self, style: str = "fade") -> None:
        if style == "fade" and self.mobjects:
            self.play(*[FadeOut(mob) for mob in self.mobjects], run_time=0.8)
        else:
            self.clear()

    # ── Audio sync ───────────────────────────────────────────────────

    def pad_to_duration(self) -> None:
        """Add trailing wait so beat duration exactly matches TTS audio length."""
        try:
            remaining = self.total_duration - self.renderer.time
            if remaining > 0.05:
                self.wait(remaining)
        except Exception:
            pass
