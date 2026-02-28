"""
EquationTransformScene — one equation morphing into another.

Beat params:
  from_latex: str — starting equation LaTeX
  to_latex:   str — target equation LaTeX
"""

from __future__ import annotations

from manim import ORIGIN, WHITE, TransformMatchingTex, Write

from scenes.base import BaseEngineeringScene


class EquationTransformScene(BaseEngineeringScene):
    from_latex: str = r"f(x) = x"
    to_latex:   str = r"f(x) = x^2"

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        eq1 = self.safe_tex(str(self.from_latex), color=WHITE)
        eq1.move_to(ORIGIN)
        self.play(Write(eq1), run_time=1.0)
        self.wait(0.4)

        eq2 = self.safe_tex(str(self.to_latex), color=WHITE)
        eq2.move_to(ORIGIN)
        self.play(TransformMatchingTex(eq1, eq2), run_time=1.5)

        self.pad_to_duration()
