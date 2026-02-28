"""
SummaryCardScene — key-points bullet list with fade-in animation.

Beat params:
  key_points: list[str] — bullet point strings (3–6 recommended)
"""

from __future__ import annotations

from manim import DOWN, LEFT, ORIGIN, RIGHT, WHITE, FadeIn, VGroup

from scenes.base import BaseEngineeringScene


class SummaryCardScene(BaseEngineeringScene):
    key_points: list = ["Key point 1", "Key point 2"]

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        heading = self.safe_text(
            "Summary",
            font_size=40,
            color=self.accent_color,
            weight="BOLD",
        )

        bullets = [
            self.safe_text(f"\u2022 {pt}", font_size=26, color=WHITE)
            for pt in self.key_points
        ]

        all_items = VGroup(heading, *bullets)
        all_items.arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        self.fit(all_items)
        all_items.move_to(ORIGIN)

        self.play(FadeIn(heading, shift=RIGHT * 0.2), run_time=0.6)
        for bullet in bullets:
            self.play(FadeIn(bullet, shift=RIGHT * 0.3), run_time=0.4)

        self.pad_to_duration()
