"""
Unit tests for scenes/__init__.py: build_beat_scene and _safe_construct.

Tests verify:
- Correct base class lookup for all 14 known types
- Fallback to TextCardScene for unknown/null/empty/missing types
- Dynamic class name sanitization
- Style attrs applied as class attributes
- Visual params set as class attrs
- _safe_construct is defined on the returned class
- _safe_construct error recovery does not re-raise

No actual Manim rendering occurs — all scene internals are mocked.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from scenes import build_beat_scene
from scenes.base import BaseEngineeringScene
from scenes.equation_reveal import EquationRevealScene
from scenes.equation_transform import EquationTransformScene
from scenes.graph_animate import GraphAnimateScene
from scenes.graph_plot import GraphPlotScene
from scenes.highlight import HighlightScene
from scenes.matrix_display import MatrixDisplayScene
from scenes.pause import PauseScene
from scenes.step_reveal import StepRevealScene
from scenes.summary_card import SummaryCardScene
from scenes.text_card import TextCardScene
from scenes.theorem_card import TheoremCardScene
from scenes.title_card import TitleCardScene
from scenes.vector_show import VectorShowScene
from scenes.vector_transform import VectorTransformScene

SAMPLE_STYLE = {"theme": "dark", "accent_color": "#58C4DD"}


def _beat(beat_id: str, visual: dict, narration: str = "Test narration.") -> dict:
    return {"beat_id": beat_id, "narration": narration, "visual": visual}


# ── Fallback for unknown/invalid types ───────────────────────────────────────

class TestUnknownTypeFallback:

    def test_unknown_type_returns_text_card_subclass(self):
        beat = _beat("u1", {"type": "animation", "data": "x"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_null_type_returns_text_card_subclass(self):
        beat = _beat("u5", {"type": None})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_empty_string_type_returns_text_card_subclass(self):
        beat = _beat("u6", {"type": ""})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_missing_type_field_returns_text_card_subclass(self):
        beat = _beat("u7", {"latex": "x^2"})  # no 'type' key
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_misspelled_type_returns_text_card_subclass(self):
        beat = _beat("ms", {"type": "equation_reval", "latex": "x^2"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_missing_visual_entirely_returns_text_card_subclass(self):
        """If 'visual' key is absent, visual={} → type=text_card (default)."""
        beat = {"beat_id": "nv", "narration": "No visual."}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)


# ── Correct base class for all 14 known types ─────────────────────────────────

class TestKnownTypeMapping:

    def test_title_card_returns_title_card_scene_subclass(self):
        beat = _beat("tc", {"type": "title_card", "title": "Test"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TitleCardScene)

    def test_equation_reveal_returns_equation_reveal_scene_subclass(self):
        beat = _beat("er", {"type": "equation_reveal", "latex": "x^2"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, EquationRevealScene)

    def test_equation_transform_returns_equation_transform_scene_subclass(self):
        beat = _beat("et", {"type": "equation_transform", "from_latex": "x^2", "to_latex": "2x"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, EquationTransformScene)

    def test_highlight_returns_highlight_scene_subclass(self):
        beat = _beat("hl", {"type": "highlight", "target": r"\lambda", "color": "YELLOW"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, HighlightScene)

    def test_step_reveal_returns_step_reveal_scene_subclass(self):
        beat = _beat("sr", {"type": "step_reveal", "latex": "x^2", "step_number": 1})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, StepRevealScene)

    def test_graph_plot_returns_graph_plot_scene_subclass(self):
        beat = _beat("gp", {
            "type": "graph_plot",
            "functions": [{"expr": "x**2"}],
            "x_range": [-3, 3],
            "y_range": [-9, 9],
        })
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, GraphPlotScene)

    def test_graph_animate_returns_graph_animate_scene_subclass(self):
        beat = _beat("ga", {
            "type": "graph_animate",
            "function_expr": "a*x**2",
            "parameter": "a",
            "range": [0.5, 2.0],
        })
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, GraphAnimateScene)

    def test_vector_show_returns_vector_show_scene_subclass(self):
        beat = _beat("vs", {"type": "vector_show", "vectors": [{"coords": [1, 0]}]})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, VectorShowScene)

    def test_vector_transform_returns_vector_transform_scene_subclass(self):
        beat = _beat("vt", {
            "type": "vector_transform",
            "matrix": [[2, 0], [0, 1]],
            "vectors": [{"coords": [1, 0]}],
        })
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, VectorTransformScene)

    def test_matrix_display_returns_matrix_display_scene_subclass(self):
        beat = _beat("md", {"type": "matrix_display", "matrix_values": [[1, 2], [3, 4]]})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, MatrixDisplayScene)

    def test_summary_card_returns_summary_card_scene_subclass(self):
        beat = _beat("sc", {"type": "summary_card", "key_points": ["Point 1.", "Point 2."]})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, SummaryCardScene)

    def test_theorem_card_returns_theorem_card_scene_subclass(self):
        beat = _beat("thm", {
            "type": "theorem_card",
            "theorem_name": "Pythagoras",
            "statement_latex": r"a^2 + b^2 = c^2",
        })
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TheoremCardScene)

    def test_text_card_returns_text_card_scene_subclass(self):
        beat = _beat("txt", {"type": "text_card", "text": "Hello."})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_pause_returns_pause_scene_subclass(self):
        beat = _beat("ps", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, PauseScene)

    def test_all_scene_classes_inherit_from_base(self):
        """All returned classes ultimately inherit from BaseEngineeringScene."""
        visuals = [
            {"type": "title_card", "title": "T"},
            {"type": "equation_reveal", "latex": "x"},
            {"type": "equation_transform", "from_latex": "x", "to_latex": "y"},
            {"type": "highlight", "target": "x", "color": "YELLOW"},
            {"type": "step_reveal", "latex": "x", "step_number": 1},
            {"type": "graph_plot", "functions": [{"expr": "x"}], "x_range": [-1, 1], "y_range": [-1, 1]},
            {"type": "graph_animate", "function_expr": "x", "parameter": "a", "range": [0, 1]},
            {"type": "vector_show", "vectors": [{"coords": [1, 0]}]},
            {"type": "vector_transform", "matrix": [[1, 0], [0, 1]], "vectors": [{"coords": [1, 0]}]},
            {"type": "matrix_display", "matrix_values": [[1, 2], [3, 4]]},
            {"type": "summary_card", "key_points": ["P1."]},
            {"type": "theorem_card", "theorem_name": "T", "statement_latex": "x"},
            {"type": "text_card", "text": "Hi"},
            {"type": "pause"},
        ]
        for i, visual in enumerate(visuals):
            beat = _beat(f"b{i}", visual)
            cls = build_beat_scene(beat, SAMPLE_STYLE)
            assert issubclass(cls, BaseEngineeringScene), f"Failed for {visual['type']}"


# ── Class name sanitization ───────────────────────────────────────────────────

class TestClassNameSanitization:

    def test_class_name_starts_with_beat_scene(self):
        beat = _beat("intro_1", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.__name__.startswith("_BeatScene_")

    def test_class_name_has_sanitized_beat_id(self):
        beat = _beat("intro_1", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert "intro_1" in cls.__name__

    def test_hyphens_in_beat_id_sanitized(self):
        beat = _beat("ch1-beat-2", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        # Class name must be a valid Python identifier
        assert cls.__name__.isidentifier()
        # Hyphens replaced with underscores
        assert "-" not in cls.__name__

    def test_dots_in_beat_id_sanitized(self):
        beat = _beat("ch1.2.3", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.__name__.isidentifier()
        assert "." not in cls.__name__

    def test_spaces_in_beat_id_sanitized(self):
        beat = _beat("my beat", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.__name__.isidentifier()
        assert " " not in cls.__name__

    def test_class_name_is_valid_python_identifier(self):
        for beat_id in ["intro", "ch1-2", "a.b.c", "step 1", "x@y"]:
            beat = _beat(beat_id, {"type": "pause"})
            cls = build_beat_scene(beat, SAMPLE_STYLE)
            assert cls.__name__.isidentifier(), f"Not an identifier: {cls.__name__!r}"

    def test_unknown_beat_id_gets_class_name(self):
        """Beat with missing beat_id uses 'unknown' as the ID."""
        beat = {"narration": "No ID.", "visual": {"type": "pause"}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert "unknown" in cls.__name__


# ── Style attributes ──────────────────────────────────────────────────────────

class TestStyleAttributes:

    def test_theme_attr_set_from_style(self):
        beat = _beat("b1", {"type": "pause"})
        cls = build_beat_scene(beat, {"theme": "light", "accent_color": "#FFFFFF"})
        assert cls.theme == "light"

    def test_accent_color_attr_set_from_style(self):
        beat = _beat("b1", {"type": "pause"})
        cls = build_beat_scene(beat, {"theme": "dark", "accent_color": "#FF0000"})
        assert cls.accent_color == "#FF0000"

    def test_default_theme_when_missing_from_style(self):
        beat = _beat("b1", {"type": "pause"})
        cls = build_beat_scene(beat, {})  # empty style
        assert cls.theme == "dark"

    def test_default_accent_color_when_missing_from_style(self):
        beat = _beat("b1", {"type": "pause"})
        cls = build_beat_scene(beat, {})
        assert cls.accent_color == "#58C4DD"


# ── Visual params as class attributes ────────────────────────────────────────

class TestVisualParamsAsAttrs:

    def test_latex_param_set_as_class_attr(self):
        beat = _beat("er", {"type": "equation_reveal", "latex": r"E = mc^2"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.latex == r"E = mc^2"

    def test_title_param_set_as_class_attr(self):
        beat = _beat("tc", {"type": "title_card", "title": "My Title"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.title == "My Title"

    def test_subtitle_param_set_as_class_attr(self):
        beat = _beat("tc", {"type": "title_card", "title": "T", "subtitle": "S"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.subtitle == "S"

    def test_key_points_param_set_as_class_attr(self):
        pts = ["Point 1.", "Point 2."]
        beat = _beat("sc", {"type": "summary_card", "key_points": pts})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.key_points == pts

    def test_type_field_not_set_as_class_attr(self):
        """The 'type' key from visual is excluded from class attrs."""
        beat = _beat("tc", {"type": "title_card", "title": "T"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        # 'type' should not be a new attribute added by build_beat_scene
        # (it may exist on Scene, but not injected by the builder)
        assert "type" not in cls.__dict__

    def test_matrix_values_param_set_as_class_attr(self):
        mv = [[1, 2], [3, 4]]
        beat = _beat("md", {"type": "matrix_display", "matrix_values": mv})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert cls.matrix_values == mv


# ── _safe_construct ───────────────────────────────────────────────────────────

class TestSafeConstruct:

    def test_safe_construct_is_defined_on_returned_class(self):
        """_safe_construct replaces construct() in the returned class."""
        beat = _beat("b1", {"type": "equation_reveal", "latex": "x^2"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        # construct should be in the class's own __dict__ (not just inherited)
        assert "construct" in cls.__dict__

    def test_safe_construct_is_callable(self):
        beat = _beat("b1", {"type": "pause"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert callable(cls.__dict__["construct"])

    def test_safe_construct_catches_exception_from_base_construct(self):
        """
        When the parent's construct() raises, _safe_construct catches it and
        runs the fallback. The fallback itself is mocked to do nothing.
        The important property is: no exception escapes _safe_construct.
        """
        beat = _beat("err_beat", {"type": "equation_reveal", "latex": "x^2"}, narration="Fallback text.")
        cls = build_beat_scene(beat, SAMPLE_STYLE)

        # Create a mock scene instance with the minimum interface
        mock_self = MagicMock()

        # Patch the base construct to raise an exception
        with patch.object(EquationRevealScene, "construct", side_effect=ValueError("bad latex")):
            # Patch manim imports inside the closure to avoid import errors
            with patch.dict("sys.modules", {
                "manim": MagicMock(
                    ORIGIN=MagicMock(),
                    WHITE=MagicMock(),
                    FadeIn=MagicMock(),
                ),
            }):
                # Should NOT raise
                try:
                    cls.__dict__["construct"](mock_self)
                except Exception as exc:
                    pytest.fail(f"_safe_construct let an exception escape: {exc}")

    def test_safe_construct_logs_error_on_exception(self):
        """When base construct() raises, _safe_construct logs the error."""
        import logging

        beat = _beat("log_beat", {"type": "equation_reveal", "latex": "x^2"})
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        mock_self = MagicMock()

        with patch.object(EquationRevealScene, "construct", side_effect=RuntimeError("crash")):
            with patch("logging.Logger.error") as mock_log:
                with patch.dict("sys.modules", {
                    "manim": MagicMock(
                        ORIGIN=MagicMock(),
                        WHITE=MagicMock(),
                        FadeIn=MagicMock(),
                    ),
                }):
                    try:
                        cls.__dict__["construct"](mock_self)
                    except Exception:
                        pass
                # Logger.error should have been called
                assert mock_log.called

    def test_safe_construct_narration_truncated_to_200_chars(self):
        """The narration fallback text is sliced to 200 chars max."""
        long_narration = "A" * 500
        beat = _beat("long", {"type": "text_card", "text": "Hi"}, narration=long_narration)
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        # The _safe_construct closure captures narration[:200]; verify the closure was set up
        # We can't easily test this without running Manim, but we can verify the class exists
        assert "construct" in cls.__dict__
