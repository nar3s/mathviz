"""
VectorTransformScene — apply a 2×2 linear transformation to vectors.

Beat params:
  matrix:  list[list] — 2×2 matrix [[a, b], [c, d]]
  vectors: list       — list of [x, y] coordinate pairs to transform
"""

from __future__ import annotations

import numpy as np
from manim import (
    BLUE,
    GREEN,
    ORIGIN,
    RED,
    YELLOW,
    ApplyMatrix,
    Arrow,
    GrowArrow,
    MathTex,
    Matrix,
    NumberPlane,
    VGroup,
    Write,
    Create,
    FadeIn,
)

from scenes.base import BaseEngineeringScene

_COLORS = [BLUE, GREEN, RED, YELLOW]


class VectorTransformScene(BaseEngineeringScene):
    matrix:  list = [[1, 0], [0, 1]]
    vectors: list = [[1, 0], [0, 1]]

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        mat = [[float(self.matrix[r][c]) for c in range(2)] for r in range(2)]
        np_mat = np.array(mat)

        plane = NumberPlane(
            x_range=[-4, 4, 1],
            y_range=[-3, 3, 1],
            background_line_style={"stroke_opacity": 0.3},
        )
        self.play(Create(plane), run_time=0.7)

        arrows: list[Arrow] = []
        for i, v in enumerate(self.vectors):
            color = _COLORS[i % len(_COLORS)]
            tip   = np.array([float(v[0]), float(v[1]), 0.0])
            arrow = Arrow(ORIGIN, tip, color=color, buff=0, stroke_width=4)
            arrows.append(arrow)
            self.play(GrowArrow(arrow), run_time=0.5)

        # Show matrix label
        mat_mob = Matrix(self.matrix, element_to_mobject_config={"font_size": 24})
        mat_mob.scale(0.7)
        mat_mob.to_corner(np.array([-1, 1, 0]) * 2)
        self.play(Write(mat_mob), run_time=0.7)

        # Apply transformation
        self.wait(0.3)
        for arrow in arrows:
            self.play(
                ApplyMatrix(
                    np.array([[mat[0][0], mat[0][1], 0],
                               [mat[1][0], mat[1][1], 0],
                               [0,         0,         1]]),
                    arrow,
                ),
                run_time=1.0,
            )

        self.pad_to_duration()
