"""
TheoremCardScene — boxed theorem or definition display.

Beat params:
  theorem_name:    str — name/title of the theorem (e.g. "Spectral Theorem")
  statement_latex: str — LaTeX for the mathematical statement
"""

from __future__ import annotations

from manim import ORIGIN, WHITE, Create, SurroundingRectangle, VGroup, Write

from scenes.base import BaseEngineeringScene


class TheoremCardScene(BaseEngineeringScene):
    theorem_name:    str = "Theorem"
    statement_latex: str = r"f(x) = x"

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        title = self.safe_text(
            str(self.theorem_name),
            font_size=36,
            color=self.accent_color,
            weight="BOLD",
        )
        statement = self.safe_tex(
            str(self.statement_latex),
            font_size=32,
            color=WHITE,
        )

        from manim import DOWN
        content = VGroup(title, statement)
        content.arrange(DOWN, buff=0.5)

        box = SurroundingRectangle(content, color=self.accent_color, buff=0.4, corner_radius=0.1)
        group = VGroup(content, box)
        self.fit(group)
        group.move_to(ORIGIN)

        self.play(Write(title), run_time=1.5)
        self.play(Create(box), Write(statement), run_time=2.5)

        self.pad_to_duration()
