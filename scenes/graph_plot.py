"""
GraphPlotScene — plot one or more functions on labeled axes.

Beat params:
  functions: list[dict]  — [{expr: str, label: str, color: str}, ...]
                            expr is a Python expression in x, e.g. "x**2"
  x_range:   list        — [x_min, x_max] or [x_min, x_max, step]
  y_range:   list        — [y_min, y_max] or [y_min, y_max, step]
"""

from __future__ import annotations

import numpy as np
from manim import (
    BLUE_C,
    Axes,
    Create,
    FadeIn,
    Write,
)

from scenes.base import BaseEngineeringScene, resolve_color

_SAFE_NS: dict = {
    "__builtins__": {},
    "np": np,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "exp": np.exp,
    "log": np.log,
    "sqrt": np.sqrt,
    "abs": abs,
    "pi": np.pi,
    "e": np.e,
}


def _safe_range(r: list) -> list:
    """Normalise x_range/y_range to always have 3 elements [min, max, step]."""
    if len(r) >= 3:
        return list(r[:3])
    if len(r) == 2:
        span = r[1] - r[0]
        step = max(1, round(span / 5))
        return [r[0], r[1], step]
    return [-5, 5, 1]


class GraphPlotScene(BaseEngineeringScene):
    functions: list = [{"expr": "x**2", "label": "f(x)=x²", "color": "BLUE"}]
    x_range:   list = [-5, 5, 1]
    y_range:   list = [-1, 10, 1]

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        xr = _safe_range(self.x_range)
        yr = _safe_range(self.y_range)

        axes = self.create_axes(
            x_range=xr,
            y_range=yr,
            x_length=8.0,
            y_length=5.5,
        )
        self.play(Create(axes), run_time=1.5)

        for fn in self.functions:
            expr  = str(fn.get("expr",  "x"))
            label = str(fn.get("label", ""))
            color = resolve_color(fn.get("color", "BLUE"), fallback=BLUE_C)

            try:
                graph = axes.plot(
                    lambda x, _e=expr: eval(_e, {**_SAFE_NS, "x": x}),
                    color=color,
                    x_range=[xr[0], xr[1]],
                    use_smoothing=True,
                )
                self.play(Create(graph), run_time=2.0)

                if label:
                    gl = axes.get_graph_label(graph, label, color=color, font_size=20)
                    self.play(FadeIn(gl), run_time=0.8)
            except Exception:  # noqa: BLE001
                pass

        self.pad_to_duration()
