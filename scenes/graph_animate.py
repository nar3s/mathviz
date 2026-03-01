"""
GraphAnimateScene — animate a function as a parameter sweeps through a range.

Beat params:
  function_expr: str  — Python expression in x and parameter, e.g. "np.sin(x * t)"
  parameter:     str  — parameter name that changes (e.g. "t")
  range:         list — [start, end] for the parameter
"""

from __future__ import annotations

import numpy as np
from manim import BLUE_C, Create, ValueTracker

from scenes.base import BaseEngineeringScene

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


class GraphAnimateScene(BaseEngineeringScene):
    function_expr: str  = "np.sin(x)"
    parameter:     str  = "t"
    range:         list = [0, 5]

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        axes = self.create_axes(x_range=[-4, 4, 1], y_range=[-2, 2, 1])
        self.play(Create(axes), run_time=1.5)

        param_name = str(self.parameter)
        expr       = str(self.function_expr)
        p_start, p_end = float(self.range[0]), float(self.range[1])

        tracker = ValueTracker(p_start)

        def _make_graph():
            p_val = tracker.get_value()
            ns = {**_SAFE_NS, "x": 0, param_name: p_val}
            try:
                return axes.plot(
                    lambda x, _p=p_val: eval(expr, {**_SAFE_NS, "x": x, param_name: _p}),
                    color=BLUE_C,
                    x_range=[-4, 4],
                    use_smoothing=True,
                )
            except Exception:  # noqa: BLE001
                return axes.plot(lambda x: 0, color=BLUE_C)

        graph = _make_graph()
        graph.add_updater(lambda g: g.become(_make_graph()))
        self.add(graph)

        anim_time = max(self.total_duration - 2.5, 1.0)
        self.play(tracker.animate.set_value(p_end), run_time=anim_time)
        graph.clear_updaters()

        self.pad_to_duration()
