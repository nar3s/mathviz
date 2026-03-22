"""
EquationRevealScene — single equation appearing with Write animation.

Beat params:
  latex: str        — LaTeX string for the equation
  label: str | None — optional label below the equation
"""

from __future__ import annotations

from manim import UP, WHITE

from scenes.base import BaseEngineeringScene


class EquationRevealScene(BaseEngineeringScene):
    latex: str = r"f(x) = x"
    label: str | None = None

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()
        self.show_equation(
            str(self.latex),
            label=str(self.label) if self.label else None,
            position=UP * 0.3,
            animate=True,
        )
        self.pad_to_duration()
