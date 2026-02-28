"""
StepRevealScene — show one derivation step with a step number label.

Beat params:
  latex:       str — LaTeX for this step's equation
  step_number: int — step index (shown as "Step N" label)
"""

from __future__ import annotations

from manim import DOWN, ORIGIN, UP, WHITE, FadeIn, Write

from scenes.base import BaseEngineeringScene


class StepRevealScene(BaseEngineeringScene):
    latex:       str = r"x = 0"
    step_number: int = 1

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        step_label = self.safe_text(
            f"Step {self.step_number}",
            font_size=24,
            color=self.accent_color,
        )
        step_label.to_edge(UP, buff=0.5)

        eq = self.safe_tex(str(self.latex), font_size=self.equation_font_size, color=WHITE)
        eq.move_to(ORIGIN)

        self.play(FadeIn(step_label), run_time=0.4)
        self.play(Write(eq), run_time=1.5)

        self.pad_to_duration()
