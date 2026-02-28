"""
MatrixDisplayScene — show a matrix with optional element highlighting.

Beat params:
  matrix_values:      list[list] — 2D array of numbers
  highlight_elements: list       — [[row, col], ...] pairs to highlight (optional)
"""

from __future__ import annotations

from manim import ORIGIN, YELLOW, Write, Matrix

from scenes.base import BaseEngineeringScene


class MatrixDisplayScene(BaseEngineeringScene):
    matrix_values:      list = [[1, 0], [0, 1]]
    highlight_elements: list = []

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        mat = Matrix(
            self.matrix_values,
            element_to_mobject_config={"font_size": 36},
        )
        self.fit(mat)
        mat.move_to(ORIGIN)

        self.play(Write(mat), run_time=1.5)

        if self.highlight_elements:
            n_cols = len(self.matrix_values[0]) if self.matrix_values else 1
            entries = mat.get_entries()
            for pair in self.highlight_elements:
                try:
                    # Accept both [row, col] lists and {"row": r, "col": c} dicts
                    if isinstance(pair, dict):
                        row, col = int(pair["row"]), int(pair["col"])
                    else:
                        row, col = int(pair[0]), int(pair[1])
                    idx = row * n_cols + col
                    if 0 <= idx < len(entries):
                        self.play(
                            entries[idx].animate.set_color(YELLOW),
                            run_time=0.4,
                        )
                except (IndexError, KeyError, TypeError, ValueError):
                    pass

        self.pad_to_duration()
