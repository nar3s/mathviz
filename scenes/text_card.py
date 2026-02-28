"""
TextCardScene — plain text display (fallback for any beat type).

Beat params:
  text: str — text to display
"""

from __future__ import annotations

from manim import ORIGIN, UP, WHITE, FadeIn

from scenes.base import BaseEngineeringScene


class TextCardScene(BaseEngineeringScene):
    text: str = "Text"

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        t = self.safe_text(str(self.text), font_size=32, color=WHITE)
        t.move_to(ORIGIN)

        self.play(FadeIn(t, shift=UP * 0.3), run_time=0.8)

        self.pad_to_duration()
