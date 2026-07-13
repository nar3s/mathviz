"""Animated horizontal probability bars with readable labels."""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, WHITE, Create, FadeIn, Line, Rectangle, VGroup

from scenes.base import BaseEngineeringScene, resolve_color


class ProbabilityBarsScene(BaseEngineeringScene):
    title: str = "Probabilities"
    bars: list = []

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        title = self.safe_text(self.title, font_size=36, color=WHITE, weight="BOLD")
        title.to_edge(UP, buff=0.4)
        rows = VGroup()
        for bar in (self.bars or [])[:5]:
            try:
                value = min(1.0, max(0.0, float(bar.get("value", 0))))
            except (TypeError, ValueError):
                value = 0.0
            label = self.safe_text(
                str(bar.get("label", "Probability")),
                font_size=22,
                color=WHITE,
                max_chars_per_line=24,
            )
            label.set_width(min(label.width, 3.0))
            track = Rectangle(width=5.2, height=0.38, stroke_color="#555566", stroke_width=1)
            fill = Rectangle(
                width=max(0.04, 5.2 * value),
                height=0.38,
                stroke_width=0,
                fill_color=resolve_color(bar.get("color", "BLUE")),
                fill_opacity=0.9,
            )
            fill.align_to(track, LEFT)
            value_text = self.safe_text(f"{value:.1%}", font_size=21, color=WHITE)
            row = VGroup(label, track, fill, value_text)
            label.move_to(LEFT * 4.5)
            track.move_to(RIGHT * 0.25)
            fill.align_to(track, LEFT).move_to(track, coor_mask=[0, 1, 0]).align_to(track, LEFT)
            value_text.next_to(track, RIGHT, buff=0.2)
            rows.add(row)
        rows.arrange(DOWN, buff=0.72).move_to(DOWN * 0.2)
        self.fit(rows, margin_x=0.92, margin_y=0.72)

        self.play(FadeIn(title), run_time=0.5)
        for row in rows:
            self.play(FadeIn(row[0]), Create(row[1]), run_time=0.35)
            self.play(FadeIn(VGroup(row[2], row[3]), shift=RIGHT * 0.15), run_time=0.35)
        self.pad_to_duration()
