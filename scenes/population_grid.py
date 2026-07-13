"""Animated population grid for discrete probability and screening examples."""

from __future__ import annotations

from manim import DOWN, LEFT, ORIGIN, RIGHT, UP, WHITE, Dot, FadeIn, VGroup

from scenes.base import BaseEngineeringScene, resolve_color


class PopulationGridScene(BaseEngineeringScene):
    title: str = "Population"
    total: int = 100
    groups: list = []

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        title = self.safe_text(self.title, font_size=36, color=WHITE, weight="BOLD")
        title.to_edge(UP, buff=0.45)

        total = max(1, int(self.total))
        groups = self.groups or [{"label": "Population", "count": total, "color": "BLUE"}]
        raw_sizes = [max(0, int(group.get("count", 0))) for group in groups]
        dot_sizes = [round(100 * size / total) for size in raw_sizes]
        if dot_sizes:
            dot_sizes[-1] += 100 - sum(dot_sizes)

        dots = VGroup()
        for group, size in zip(groups, dot_sizes):
            color = resolve_color(group.get("color", "BLUE"))
            for _ in range(max(0, size)):
                dots.add(Dot(radius=0.095, color=color))
        while len(dots) < 100:
            dots.add(Dot(radius=0.095, color=resolve_color("BLUE")))
        dots.arrange_in_grid(rows=10, cols=10, buff=0.15)
        dots.scale(0.9).move_to(LEFT * 2.4 + DOWN * 0.2)

        legend_rows = []
        for group in groups:
            swatch = Dot(radius=0.1, color=resolve_color(group.get("color", "BLUE")))
            label = self.safe_text(
                f"{group.get('label', 'Group')}: {int(group.get('count', 0)):,}",
                font_size=22,
                color=WHITE,
                max_chars_per_line=28,
            )
            legend_rows.append(VGroup(swatch, label).arrange(RIGHT, buff=0.18))
        legend = VGroup(*legend_rows).arrange(DOWN, buff=0.32, aligned_edge=LEFT)
        legend.move_to(RIGHT * 3.1 + DOWN * 0.15)
        self.fit(VGroup(dots, legend), margin_x=0.9, margin_y=0.72)

        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.5)
        self.play(FadeIn(dots, lag_ratio=0.015), run_time=1.1)
        self.play(FadeIn(legend, shift=RIGHT * 0.2), run_time=0.8)
        self.pad_to_duration()
