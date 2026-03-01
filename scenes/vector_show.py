"""
VectorShowScene — display labeled vectors on a 2D number plane.

Beat params:
  vectors: list[dict] — [{coords: [x, y], label: str, color: str}, ...]
"""

from __future__ import annotations

import numpy as np
from manim import (
    BLUE,
    ORIGIN,
    UP,
    Arrow,
    Create,
    FadeIn,
    GrowArrow,
    NumberPlane,
    Text,
)

from scenes.base import BaseEngineeringScene, resolve_color


class VectorShowScene(BaseEngineeringScene):
    vectors: list = [{"coords": [1, 0], "label": "e_1", "color": "BLUE"}]

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-3, 3, 1],
            background_line_style={"stroke_opacity": 0.3},
        )
        self.play(Create(plane), run_time=1.5)

        for v in self.vectors:
            coords = v.get("coords", [1, 0])
            color  = resolve_color(v.get("color", "BLUE"), fallback=BLUE)
            label  = v.get("label", "")

            tip = np.array([float(coords[0]), float(coords[1]), 0.0])
            arrow = Arrow(ORIGIN, tip, color=color, buff=0, stroke_width=4)
            self.play(GrowArrow(arrow), run_time=1.5)

            if label:
                lbl = Text(label, color=color, font_size=24)
                lbl.next_to(arrow.get_end(), UP * 0.3, buff=0.15)
                self.play(FadeIn(lbl), run_time=0.6)

        self.pad_to_duration()
