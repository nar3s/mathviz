"""
Unit tests for renderer/scene_builder.py

All tests are pure Python — no Manim, no subprocesses, no API calls.
"""

import json
import py_compile
from pathlib import Path

import pytest

from renderer.scene_builder import (
    _to_class_name,
    build_all_scene_files,
    build_scene_file,
)


# ── Sample beats for all supported visual types ──────────────────────────────

ALL_BEAT_TYPES = [
    pytest.param(
        {
            "beat_id": "intro_1",
            "narration": "Welcome to the lesson.",
            "visual": {"type": "title_card", "title": "Introduction", "subtitle": "Getting started"},
        },
        id="title_card",
    ),
    pytest.param(
        {
            "beat_id": "def_1",
            "narration": "The famous energy equation.",
            "visual": {"type": "equation_reveal", "latex": r"E = mc^2", "label": "Energy"},
        },
        id="equation_reveal",
    ),
    pytest.param(
        {
            "beat_id": "def_2",
            "narration": "One equation transforms into another.",
            "visual": {
                "type": "equation_transform",
                "from_latex": r"A\vec{v} = \lambda\vec{v}",
                "to_latex": r"\det(A - \lambda I) = 0",
            },
        },
        id="equation_transform",
    ),
    pytest.param(
        {
            "beat_id": "def_3",
            "narration": "Lambda is highlighted.",
            "visual": {"type": "highlight", "target": r"\lambda", "color": "YELLOW"},
        },
        id="highlight",
    ),
    pytest.param(
        {
            "beat_id": "ex_1",
            "narration": "Step one of the derivation.",
            "visual": {"type": "step_reveal", "latex": r"2x = 6", "step_number": 1},
        },
        id="step_reveal",
    ),
    pytest.param(
        {
            "beat_id": "graph_1",
            "narration": "Here is the parabola.",
            "visual": {
                "type": "graph_plot",
                "functions": [{"expr": "x**2", "label": "f(x)", "color": "BLUE"}],
                "x_range": [-3, 3],
                "y_range": [-1, 9],
            },
        },
        id="graph_plot",
    ),
    pytest.param(
        {
            "beat_id": "graph_2",
            "narration": "Watch the sine wave change.",
            "visual": {
                "type": "graph_animate",
                "function_expr": "np.sin(x * t)",
                "parameter": "t",
                "range": [1, 4],
            },
        },
        id="graph_animate",
    ),
    pytest.param(
        {
            "beat_id": "vec_1",
            "narration": "Here are two vectors.",
            "visual": {
                "type": "vector_show",
                "vectors": [{"coords": [1, 0], "label": "e_1", "color": "BLUE"}],
            },
        },
        id="vector_show",
    ),
    pytest.param(
        {
            "beat_id": "vec_2",
            "narration": "The transformation stretches the vectors.",
            "visual": {
                "type": "vector_transform",
                "matrix": [[2, 0], [0, 1]],
                "vectors": [[1, 0], [0, 1]],
            },
        },
        id="vector_transform",
    ),
    pytest.param(
        {
            "beat_id": "mat_1",
            "narration": "Here is matrix A.",
            "visual": {
                "type": "matrix_display",
                "matrix_values": [[1, 2], [3, 4]],
                "highlight_elements": [[0, 0]],
            },
        },
        id="matrix_display",
    ),
    pytest.param(
        {
            "beat_id": "thm_1",
            "narration": "The Pythagorean theorem.",
            "visual": {
                "type": "theorem_card",
                "theorem_name": "Pythagoras",
                "statement_latex": r"a^2 + b^2 = c^2",
            },
        },
        id="theorem_card",
    ),
    pytest.param(
        {
            "beat_id": "sum_1",
            "narration": "In summary.",
            "visual": {
                "type": "summary_card",
                "key_points": ["Eigenvalues scale eigenvectors.", r"Use \det(A - \lambda I) = 0."],
            },
        },
        id="summary_card",
    ),
    pytest.param(
        {
            "beat_id": "txt_1",
            "narration": "A plain text beat.",
            "visual": {"type": "text_card", "text": "Hello world"},
        },
        id="text_card",
    ),
    pytest.param(
        {
            "beat_id": "pause_1",
            "narration": "A brief pause.",
            "visual": {"type": "pause"},
        },
        id="pause",
    ),
]


# ── _to_class_name ────────────────────────────────────────────────────────────

class TestToClassName:

    def test_simple_id(self):
        assert _to_class_name("intro") == "MathVizScene_intro"

    def test_hyphens_replaced_with_underscores(self):
        assert _to_class_name("step-by-step") == "MathVizScene_step_by_step"

    def test_dots_replaced_with_underscores(self):
        assert _to_class_name("ch1.2") == "MathVizScene_ch1_2"

    def test_leading_digit_gets_prefix(self):
        result = _to_class_name("1beat")
        class_part = result[len("MathVizScene_"):]
        assert class_part[0].isalpha() or class_part[0] == "_"

    def test_spaces_replaced(self):
        result = _to_class_name("my beat")
        assert " " not in result
        assert result.startswith("MathVizScene_")

    def test_underscores_preserved(self):
        assert _to_class_name("ch1_1") == "MathVizScene_ch1_1"

    def test_mixed_case_preserved(self):
        assert _to_class_name("myBeat") == "MathVizScene_myBeat"

    def test_result_is_valid_python_identifier(self):
        for beat_id in ["intro", "ch1-2", "1start", "a.b.c", "my beat"]:
            result = _to_class_name(beat_id)
            assert result.isidentifier(), f"{result!r} is not a valid identifier"


# ── build_scene_file ──────────────────────────────────────────────────────────

class TestBuildSceneFile:

    def test_creates_output_file(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene_intro.py"
        file_path, _ = build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        assert file_path.exists()
        assert file_path == out

    def test_returns_correct_class_name(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        _, class_name = build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        assert class_name == "MathVizScene_intro_1"

    def test_generated_file_is_valid_python(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        file_path, _ = build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        py_compile.compile(str(file_path), doraise=True)

    def test_duration_injected_in_file(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=12.345,
            audio_path=None,
            output_file=out,
        )
        content = out.read_text(encoding="utf-8")
        assert "12.345" in content

    def test_audio_path_injected_in_file(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        audio = tmp_path / "intro_1.wav"
        build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=audio,
            output_file=out,
        )
        content = out.read_text(encoding="utf-8")
        assert "intro_1.wav" in content

    def test_audio_path_none_sets_none(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        content = out.read_text(encoding="utf-8")
        assert "_AUDIO_FILE = None" in content

    def test_latex_backslashes_embedded_safely(self, tmp_path, sample_style):
        beat = {
            "beat_id": "eq_1",
            "narration": "A partial derivative.",
            "visual": {"type": "equation_reveal", "latex": r"\frac{\partial f}{\partial x}"},
        }
        out = tmp_path / "scene.py"
        file_path, _ = build_scene_file(
            beat_config=beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        py_compile.compile(str(file_path), doraise=True)

    def test_double_quotes_in_narration_safe(self, tmp_path, sample_style):
        beat = {
            "beat_id": "q_1",
            "narration": 'He said "hello" and it worked.',
            "visual": {"type": "text_card", "text": "Hello"},
        }
        out = tmp_path / "scene.py"
        file_path, _ = build_scene_file(
            beat_config=beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        py_compile.compile(str(file_path), doraise=True)

    def test_unicode_narration_safe(self, tmp_path, sample_style):
        beat = {
            "beat_id": "hindi_1",
            "narration": "मैं गणित पढ़ता हूं।",
            "visual": {"type": "text_card", "text": "गणित"},
        }
        out = tmp_path / "scene.py"
        file_path, _ = build_scene_file(
            beat_config=beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        py_compile.compile(str(file_path), doraise=True)

    def test_creates_nested_parent_dirs(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "nested" / "deep" / "scene.py"
        build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        assert out.exists()

    def test_duration_rounded_to_three_decimals(self, tmp_path, sample_beat, sample_style):
        out = tmp_path / "scene.py"
        build_scene_file(
            beat_config=sample_beat,
            style=sample_style,
            total_duration=10.123456789,
            audio_path=None,
            output_file=out,
        )
        content = out.read_text(encoding="utf-8")
        assert "10.123" in content

    @pytest.mark.parametrize("beat", ALL_BEAT_TYPES)
    def test_all_beat_types_produce_valid_python(self, tmp_path, sample_style, beat):
        bid = beat["beat_id"]
        out = tmp_path / f"scene_{bid}.py"
        file_path, class_name = build_scene_file(
            beat_config=beat,
            style=sample_style,
            total_duration=8.0,
            audio_path=None,
            output_file=out,
        )
        assert file_path.exists()
        py_compile.compile(str(file_path), doraise=True)
        assert class_name.startswith("MathVizScene_")

    def test_beat_json_roundtrips_in_file(self, tmp_path, sample_style):
        """The embedded JSON must decode back to the original beat dict."""
        beat = {
            "beat_id": "mat_1",
            "narration": r"Matrix A has eigenvalues \lambda_1 and \lambda_2.",
            "visual": {"type": "matrix_display", "matrix_values": [[1, 2], [3, 4]]},
        }
        out = tmp_path / "scene.py"
        file_path, _ = build_scene_file(
            beat_config=beat,
            style=sample_style,
            total_duration=5.0,
            audio_path=None,
            output_file=out,
        )
        content = out.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("_BEAT = json.loads("):
                repr_str = line[len("_BEAT = json.loads("):-1]
                decoded_json = eval(repr_str)
                recovered = json.loads(decoded_json)
                assert recovered["beat_id"] == beat["beat_id"]
                assert recovered["visual"]["matrix_values"] == [[1, 2], [3, 4]]
                break


# ── build_all_scene_files ─────────────────────────────────────────────────────

class TestBuildAllSceneFiles:

    def _beat(self, bid: str) -> dict:
        return {
            "beat_id": bid,
            "narration": f"Narration for {bid}.",
            "visual": {"type": "text_card", "text": bid},
        }

    def test_returns_ordered_list(self, tmp_path, sample_style):
        beats = [self._beat("ch1_1"), self._beat("ch1_2"), self._beat("ch1_3")]
        results = build_all_scene_files(
            beats=beats,
            style=sample_style,
            durations={"ch1_1": 5.0, "ch1_2": 8.0, "ch1_3": 6.0},
            audio_paths={},
            scene_dir=tmp_path,
        )
        assert len(results) == 3
        assert [r[0] for r in results] == ["ch1_1", "ch1_2", "ch1_3"]

    def test_all_files_created_on_disk(self, tmp_path, sample_style):
        beats = [self._beat("b1"), self._beat("b2")]
        results = build_all_scene_files(
            beats=beats,
            style=sample_style,
            durations={"b1": 5.0, "b2": 7.0},
            audio_paths={},
            scene_dir=tmp_path,
        )
        for _, file_path, _ in results:
            assert file_path.exists()

    def test_missing_duration_defaults_to_ten(self, tmp_path, sample_style):
        beats = [self._beat("b1")]
        results = build_all_scene_files(
            beats=beats,
            style=sample_style,
            durations={},
            audio_paths={},
            scene_dir=tmp_path,
        )
        _, file_path, _ = results[0]
        content = file_path.read_text(encoding="utf-8")
        assert "10.0" in content

    def test_audio_path_injected_per_beat(self, tmp_path, sample_style):
        beats = [self._beat("b1")]
        audio = tmp_path / "b1.wav"
        results = build_all_scene_files(
            beats=beats,
            style=sample_style,
            durations={"b1": 5.0},
            audio_paths={"b1": audio},
            scene_dir=tmp_path,
        )
        _, file_path, _ = results[0]
        content = file_path.read_text(encoding="utf-8")
        assert "b1.wav" in content

    def test_returns_tuple_of_id_path_classname(self, tmp_path, sample_style):
        beats = [self._beat("intro_1")]
        results = build_all_scene_files(
            beats=beats,
            style=sample_style,
            durations={},
            audio_paths={},
            scene_dir=tmp_path,
        )
        bid, file_path, class_name = results[0]
        assert bid == "intro_1"
        assert isinstance(file_path, Path)
        assert class_name == "MathVizScene_intro_1"

    def test_empty_beats_returns_empty_list(self, tmp_path, sample_style):
        results = build_all_scene_files(
            beats=[],
            style=sample_style,
            durations={},
            audio_paths={},
            scene_dir=tmp_path,
        )
        assert results == []
