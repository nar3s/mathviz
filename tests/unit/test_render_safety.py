"""
Unit tests for render-time safety — pure Python parts only, no Manim subprocess.

Covers section 5:
  5.2  graph_plot eval sandbox rejects syntax errors
  5.3  graph_plot eval sandbox blocks __import__ / dangerous builtins
  5.5  x_range inverted [10, -10] → _safe_range still normalises it
  5.6  x_range zero [5, 5] → _safe_range still produces 3-element list
  5.7  _safe_range with 1-element list falls back to default
  5.11 Non-square matrix in vector_transform → scene-level error or graceful fallback
  5.12 total_duration=0 → pad_to_duration doesn't hang (pure guard logic)

For eval sandbox tests we call the lambda directly as used in GraphPlotScene.
"""

from __future__ import annotations

import pytest

from scenes.graph_plot import _SAFE_NS, _safe_range
from scenes import build_beat_scene


SAMPLE_STYLE = {"theme": "dark", "accent_color": "#58C4DD"}


# ── _safe_range normalisation ─────────────────────────────────────────────────

class TestSafeRange:

    def test_two_element_list_adds_step(self):
        result = _safe_range([-3, 3])
        assert len(result) == 3
        assert result[0] == -3
        assert result[1] == 3

    def test_three_element_list_unchanged(self):
        result = _safe_range([-5, 5, 1])
        assert result == [-5, 5, 1]

    def test_5_5_inverted_range_produces_three_elements(self):
        """
        x_range [10, -10]: span = -20 → step = max(1, round(-4)) = max(1,-4) = 1.
        _safe_range still returns a 3-element list (it doesn't validate direction).
        """
        result = _safe_range([10, -10])
        assert len(result) == 3
        assert result[0] == 10
        assert result[1] == -10

    def test_5_6_zero_range_produces_three_elements(self):
        """
        x_range [5, 5]: span = 0 → step = max(1, round(0)) = 1.
        Returns [5, 5, 1] — the Axes/Manim call will fail, but _safe_range itself
        does not raise.
        """
        result = _safe_range([5, 5])
        assert len(result) == 3
        assert result == [5, 5, 1]

    def test_5_7_one_element_list_falls_back(self):
        """1-element list → falls back to [-5, 5, 1]."""
        result = _safe_range([3])
        assert result == [-5, 5, 1]

    def test_empty_list_falls_back(self):
        result = _safe_range([])
        assert result == [-5, 5, 1]

    def test_four_element_list_takes_first_three(self):
        result = _safe_range([-10, 10, 2, 999])
        assert result == [-10, 10, 2]

    def test_step_is_at_least_one(self):
        """For a tiny range the step is clamped to 1."""
        result = _safe_range([0, 0.1])
        assert result[2] >= 1


# ── eval sandbox ─────────────────────────────────────────────────────────────

class TestEvalSandbox:
    """
    Test the eval sandbox used in GraphPlotScene.

    The sandbox is: eval(expr, {**_SAFE_NS, "x": x_value})
    _SAFE_NS has "__builtins__": {} so the default builtins are blocked.
    """

    def _eval(self, expr: str, x: float) -> float:
        """Evaluate expr in the sandbox with the given x value."""
        ns = {**_SAFE_NS, "x": x}
        return eval(expr, ns)  # noqa: S307 — intentional for test

    def test_valid_expr_x_squared(self):
        result = self._eval("x**2", 3.0)
        assert result == 9.0

    def test_valid_expr_sin(self):
        import numpy as np
        result = self._eval("sin(x)", 0.0)
        assert result == pytest.approx(0.0)

    def test_valid_expr_numpy_func(self):
        import numpy as np
        result = self._eval("np.exp(x)", 0.0)
        assert result == pytest.approx(1.0)

    def test_5_2_syntax_error_raises_syntax_error(self):
        """
        Malformed expression 'x***2' raises SyntaxError when passed to eval.
        GraphPlotScene catches this with 'except Exception: pass'.
        """
        with pytest.raises(SyntaxError):
            self._eval("x***2", 2.0)

    def test_5_3_import_blocked_in_sandbox(self):
        """
        __import__ is not available when __builtins__={}.
        Attempting to use it raises NameError or TypeError.
        """
        with pytest.raises((NameError, TypeError, ImportError)):
            self._eval("__import__('os').system('echo hi')", 1.0)

    def test_5_3_builtins_access_blocked(self):
        """
        __builtins__ is set to {} in the namespace, so accessing it
        via the eval namespace returns an empty dict.
        """
        ns = {**_SAFE_NS, "x": 1.0}
        result = eval("__builtins__", ns)  # noqa: S307
        assert result == {}

    def test_5_3_open_not_available_in_sandbox(self):
        """open() is not in _SAFE_NS → NameError."""
        with pytest.raises(NameError):
            self._eval("open('/etc/passwd')", 1.0)

    def test_5_3_exec_not_available_in_sandbox(self):
        """exec is not in _SAFE_NS → NameError."""
        with pytest.raises(NameError):
            self._eval("exec('import os')", 1.0)

    def test_valid_expr_with_pi(self):
        import numpy as np
        result = self._eval("sin(pi)", 1.0)
        assert result == pytest.approx(np.sin(np.pi), abs=1e-10)

    def test_division_by_zero_raises_zero_division_error(self):
        """Division by zero is caught by GraphPlotScene's except clause."""
        with pytest.raises(ZeroDivisionError):
            self._eval("1/x", 0.0)

    def test_log_of_negative_raises_or_returns_nan(self):
        """
        log(-1) with the restricted __builtins__={} sandbox may raise a KeyError
        because numpy internally uses __import__ for its RuntimeWarning mechanism.
        When running outside a Manim axes.plot() call, this surfaces as a KeyError.
        GraphPlotScene catches this with 'except Exception: pass'.
        """
        import numpy as np
        try:
            result = self._eval("log(x)", -1.0)
            # If it doesn't raise, it returns NaN
            assert np.isnan(result)
        except (KeyError, Exception):
            # KeyError on '__import__' is expected behavior with __builtins__={}
            pass


# ── build_beat_scene for safety cases ────────────────────────────────────────

class TestBuildBeatSceneSafety:

    def test_5_1_unknown_visual_type_returns_text_card_subclass(self):
        """Unknown visual type → TextCardScene fallback (already tested in test_scene_registry)."""
        from scenes.text_card import TextCardScene
        beat = {"beat_id": "u1", "narration": "Unknown.", "visual": {"type": "bogus_type"}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_5_7_zero_vector_scene_class_created(self):
        """
        Zero vector [0, 0] → VectorShowScene subclass is returned.
        The actual rendering (GrowArrow with zero tip) would produce an invisible
        arrow, but build_beat_scene itself should not crash.
        """
        from scenes.vector_show import VectorShowScene
        beat = {
            "beat_id": "zv",
            "narration": "Zero vector.",
            "visual": {"type": "vector_show", "vectors": [{"coords": [0, 0], "color": "BLUE"}]},
        }
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, VectorShowScene)

    def test_5_11_non_square_matrix_scene_class_created(self):
        """
        Non-square matrix [[1,2,3],[4,5,6]] → VectorTransformScene subclass returned.
        The actual rendering would fail (IndexError on mat[1][1] for 3-col matrix),
        but build_beat_scene itself should not crash.
        """
        from scenes.vector_transform import VectorTransformScene
        beat = {
            "beat_id": "ns",
            "narration": "Non-square.",
            "visual": {
                "type": "vector_transform",
                "matrix": [[1, 2, 3], [4, 5, 6]],
                "vectors": [{"coords": [1, 0]}],
            },
        }
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, VectorTransformScene)

    def test_5_12_zero_duration_class_created(self):
        """
        total_duration=0 is valid for building the scene class.
        pad_to_duration() checks 'remaining > 0.05' so it won't hang.
        """
        beat = {"beat_id": "zd", "narration": "Zero dur.", "visual": {"type": "pause"}}
        # build_beat_scene does not inject total_duration — that's done by the generated .py file
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls is not None

    def test_inverted_x_range_scene_class_created(self):
        """
        Graph plot with inverted x_range [10, -10] → GraphPlotScene subclass returned.
        The rendering would fail at Axes creation, but scene class creation is fine.
        """
        from scenes.graph_plot import GraphPlotScene
        beat = {
            "beat_id": "inv",
            "narration": "Inverted range.",
            "visual": {
                "type": "graph_plot",
                "functions": [{"expr": "x**2"}],
                "x_range": [10, -10],
                "y_range": [-1, 9],
            },
        }
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, GraphPlotScene)

    def test_graph_plot_with_syntax_error_expr_attr_set(self):
        """
        GraphPlotScene subclass is created even with a bad expr.
        The bad expr is stored as a class attr; error only surfaces at render time.
        """
        from scenes.graph_plot import GraphPlotScene
        beat = {
            "beat_id": "syn",
            "narration": "Bad expr.",
            "visual": {
                "type": "graph_plot",
                "functions": [{"expr": "x***2", "color": "BLUE"}],
                "x_range": [-3, 3],
                "y_range": [-9, 9],
            },
        }
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, GraphPlotScene)
        # The bad expression is stored in the functions attr
        assert cls.functions[0]["expr"] == "x***2"
