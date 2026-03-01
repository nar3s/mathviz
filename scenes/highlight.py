"""
HighlightScene — display a LaTeX expression with a highlight color.

Beat params:
  target: str — LaTeX string to show highlighted
  color:  str — Manim color name or hex string (e.g. "YELLOW", "#FFD700")
"""

from __future__ import annotations

from manim import (
    ORIGIN,
    WHITE,
    FadeIn,
    MathTex,
    SurroundingRectangle,
    Create,
    Write,
)

from scenes.base import BaseEngineeringScene, resolve_color


class HighlightScene(BaseEngineeringScene):
    target: str = r"x"
    color:  str = "YELLOW"

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        resolved = resolve_color(str(self.color))

        eq = self.safe_tex(str(self.target), font_size=self.equation_font_size, color=WHITE)
        eq.move_to(ORIGIN)

        # Highlight box in the target color
        box = SurroundingRectangle(eq, color=resolved, buff=0.15, corner_radius=0.1)

        self.play(Write(eq), run_time=1.8)
        self.play(Create(box), eq.animate.set_color(resolved), run_time=1.5)

        self.pad_to_duration()
