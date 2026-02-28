"""
Unit tests for beat JSON parsing and validation.

Covers sections 2.1-2.5:
  2.1 - Beat list parsing (wrapped objects, empty list, single beat)
  2.2 - Unknown/invalid visual types
  2.3 - Missing required visual fields
  2.4 - Renamed fields (Gemini-style)
  2.5 - Wrong field types

Also verifies that build_beat_scene falls back to TextCardScene for invalid types.
All tests are pure Python — no Manim subprocess, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from generator.validator import (
    ALLOWED_BEAT_TYPES,
    REQUIRED_VISUAL_FIELDS,
    validate_beat,
    validate_beats,
)
from scenes import build_beat_scene
from scenes.text_card import TextCardScene

FIXTURES = Path(__file__).parent.parent / "fixtures" / "beats"

SAMPLE_STYLE = {"theme": "dark", "accent_color": "#58C4DD"}


# ── Section 2.1: Beat list structure ─────────────────────────────────────────

class TestBeatListStructure:

    def test_2_1_1_wrapped_object_unwrapped_inner_list_is_valid(self):
        """
        Planner unwraps {"beats": [...]} → inner list.
        Test that the inner list itself validates cleanly.
        """
        wrapped = {
            "beats": [
                {
                    "beat_id": "b1",
                    "narration": "Hello.",
                    "visual": {"type": "text_card", "text": "Hi"},
                }
            ]
        }
        inner = wrapped["beats"]
        errors = validate_beats(inner)
        assert errors == []

    def test_2_1_4_empty_beats_array_returns_no_errors(self):
        """validate_beats([]) returns an empty error list."""
        errors = validate_beats([])
        assert errors == []

    def test_2_1_5_single_beat_not_in_array_can_be_wrapped(self):
        """A single beat dict wrapped in a list validates successfully."""
        beat = {
            "beat_id": "only_1",
            "narration": "The only beat.",
            "visual": {"type": "text_card", "text": "Single slide."},
        }
        errors = validate_beats([beat])
        assert errors == []

    def test_single_beat_fixture_validates(self):
        """single_beat.json fixture validates with zero errors."""
        beats = json.loads((FIXTURES / "single_beat.json").read_text())
        errors = validate_beats(beats)
        assert errors == []

    def test_valid_all_types_fixture_validates(self):
        """valid_all_types.json — all 14 beat types validate cleanly."""
        beats = json.loads((FIXTURES / "valid_all_types.json").read_text())
        errors = validate_beats(beats)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_all_types_has_14_beats(self):
        """valid_all_types.json has exactly 14 beats (one per visual type)."""
        beats = json.loads((FIXTURES / "valid_all_types.json").read_text())
        assert len(beats) == 14

    def test_many_beats_fixture_validates(self):
        """many_beats.json (22 beats) validates cleanly."""
        beats = json.loads((FIXTURES / "many_beats.json").read_text())
        errors = validate_beats(beats)
        assert errors == []

    def test_many_beats_fixture_has_22_beats(self):
        beats = json.loads((FIXTURES / "many_beats.json").read_text())
        assert len(beats) == 22

    def test_duplicate_beat_ids_reported(self):
        """validate_beats catches duplicate beat_ids across beats."""
        beats = [
            {"beat_id": "dup", "narration": "First.", "visual": {"type": "pause"}},
            {"beat_id": "dup", "narration": "Second.", "visual": {"type": "pause"}},
        ]
        errors = validate_beats(beats)
        assert any("duplicate" in e.lower() for e in errors)


# ── Section 2.2: Unknown/invalid visual types ─────────────────────────────────

class TestUnknownVisualTypes:

    def _load_unknown(self):
        return json.loads((FIXTURES / "unknown_types.json").read_text())

    def test_2_2_1_unknown_type_animation_reported(self):
        """Visual type 'animation' is not in ALLOWED_BEAT_TYPES → error reported."""
        beat = {"beat_id": "u1", "narration": "Anim.", "visual": {"type": "animation", "data": "x"}}
        errors = validate_beat(beat)
        assert any("animation" in e or "unknown" in e.lower() for e in errors)

    def test_2_2_2_unknown_type_diagram_reported(self):
        beat = {"beat_id": "u2", "narration": "Dia.", "visual": {"type": "diagram", "data": "x"}}
        errors = validate_beat(beat)
        assert any("diagram" in e or "unknown" in e.lower() for e in errors)

    def test_2_2_3_misspelled_type_reported(self):
        """'equation_reval' is not a known type → error."""
        beat = {"beat_id": "u4", "narration": "Mis.", "visual": {"type": "equation_reval", "latex": "x^2"}}
        errors = validate_beat(beat)
        assert any("unknown" in e.lower() or "equation_reval" in e for e in errors)

    def test_2_2_4_null_type_reported(self):
        """type: null → not in ALLOWED_BEAT_TYPES → error."""
        beat = {"beat_id": "u5", "narration": "Null.", "visual": {"type": None}}
        errors = validate_beat(beat)
        assert len(errors) > 0

    def test_2_2_5_empty_string_type_reported(self):
        """type: '' → not in ALLOWED_BEAT_TYPES → error."""
        beat = {"beat_id": "u6", "narration": "Empty.", "visual": {"type": ""}}
        errors = validate_beat(beat)
        assert len(errors) > 0

    def test_2_2_6_missing_type_field_reported(self):
        """No 'type' field in visual → None not in ALLOWED_BEAT_TYPES → error."""
        beat = {"beat_id": "u7", "narration": "No type.", "visual": {"latex": "x^2"}}
        errors = validate_beat(beat)
        assert len(errors) > 0

    def test_all_unknown_types_from_fixture_have_errors(self):
        """Every beat in unknown_types.json should produce at least one error."""
        beats = self._load_unknown()
        for beat in beats:
            errors = validate_beat(beat)
            assert len(errors) > 0, f"Expected errors for beat {beat['beat_id']}"

    def test_unknown_type_build_beat_scene_falls_back_to_text_card(self):
        """build_beat_scene with unknown type returns a TextCardScene subclass."""
        beat = {"beat_id": "u1", "narration": "Anim.", "visual": {"type": "animation", "data": "x"}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_null_type_build_beat_scene_falls_back(self):
        beat = {"beat_id": "u5", "narration": "Null.", "visual": {"type": None}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_empty_type_build_beat_scene_falls_back(self):
        beat = {"beat_id": "u6", "narration": "Empty.", "visual": {"type": ""}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)

    def test_missing_type_field_build_beat_scene_falls_back(self):
        beat = {"beat_id": "u7", "narration": "No type.", "visual": {"latex": "x^2"}}
        cls = build_beat_scene(beat, SAMPLE_STYLE)
        assert issubclass(cls, TextCardScene)


# ── Section 2.3: Missing required visual fields ───────────────────────────────

class TestMissingRequiredFields:

    def _load_missing(self):
        return json.loads((FIXTURES / "missing_fields.json").read_text())

    def test_2_3_1_equation_reveal_missing_latex(self):
        beat = {"beat_id": "m1", "narration": "No latex.", "visual": {"type": "equation_reveal"}}
        errors = validate_beat(beat)
        assert any("latex" in e for e in errors)

    def test_2_3_2_equation_transform_missing_from_latex(self):
        beat = {
            "beat_id": "m2",
            "narration": "No from.",
            "visual": {"type": "equation_transform", "to_latex": "2x"},
        }
        errors = validate_beat(beat)
        assert any("from_latex" in e for e in errors)

    def test_2_3_3_equation_transform_missing_to_latex(self):
        beat = {
            "beat_id": "m3",
            "narration": "No to.",
            "visual": {"type": "equation_transform", "from_latex": "x^2"},
        }
        errors = validate_beat(beat)
        assert any("to_latex" in e for e in errors)

    def test_2_3_4_graph_plot_missing_functions(self):
        beat = {
            "beat_id": "m4",
            "narration": "No funcs.",
            "visual": {"type": "graph_plot", "x_range": [-3, 3], "y_range": [-9, 9]},
        }
        errors = validate_beat(beat)
        assert any("functions" in e for e in errors)

    def test_2_3_5_highlight_missing_target(self):
        beat = {
            "beat_id": "m5",
            "narration": "No target.",
            "visual": {"type": "highlight", "color": "YELLOW"},
        }
        errors = validate_beat(beat)
        assert any("target" in e for e in errors)

    def test_2_3_6_vector_show_missing_vectors(self):
        beat = {"beat_id": "m6", "narration": "No vec.", "visual": {"type": "vector_show"}}
        errors = validate_beat(beat)
        assert any("vectors" in e for e in errors)

    def test_2_3_7_vector_transform_missing_matrix(self):
        beat = {
            "beat_id": "m7",
            "narration": "No mat.",
            "visual": {"type": "vector_transform", "vectors": [{"coords": [1, 0]}]},
        }
        errors = validate_beat(beat)
        assert any("matrix" in e for e in errors)

    def test_2_3_8_graph_animate_missing_function_expr(self):
        beat = {
            "beat_id": "m8",
            "narration": "No expr.",
            "visual": {"type": "graph_animate", "parameter": "a", "range": [0, 1]},
        }
        errors = validate_beat(beat)
        assert any("function_expr" in e for e in errors)

    def test_2_3_9_matrix_display_missing_matrix_values(self):
        beat = {"beat_id": "m9", "narration": "No vals.", "visual": {"type": "matrix_display"}}
        errors = validate_beat(beat)
        assert any("matrix_values" in e for e in errors)

    def test_2_3_10_summary_card_missing_key_points(self):
        beat = {"beat_id": "m10", "narration": "No pts.", "visual": {"type": "summary_card"}}
        errors = validate_beat(beat)
        assert any("key_points" in e for e in errors)

    def test_2_3_11_theorem_card_missing_statement_latex(self):
        beat = {
            "beat_id": "m11",
            "narration": "No stmt.",
            "visual": {"type": "theorem_card", "theorem_name": "Test"},
        }
        errors = validate_beat(beat)
        assert any("statement_latex" in e for e in errors)

    def test_2_3_12_step_reveal_missing_latex(self):
        beat = {
            "beat_id": "m12",
            "narration": "No latex.",
            "visual": {"type": "step_reveal", "step_number": 1},
        }
        errors = validate_beat(beat)
        assert any("latex" in e for e in errors)

    def test_all_missing_field_beats_have_errors(self):
        """Every beat in missing_fields.json should produce at least one error."""
        beats = self._load_missing()
        for beat in beats:
            errors = validate_beat(beat)
            assert len(errors) > 0, f"Expected errors for beat {beat['beat_id']}"

    def test_pause_has_no_required_fields(self):
        """pause type has no required fields — missing nothing."""
        beat = {"beat_id": "p1", "narration": "Pause.", "visual": {"type": "pause"}}
        errors = validate_beat(beat)
        assert errors == []

    def test_text_card_requires_text(self):
        beat = {"beat_id": "tc", "narration": "No text.", "visual": {"type": "text_card"}}
        errors = validate_beat(beat)
        assert any("text" in e for e in errors)


# ── Section 2.4: Renamed fields (Gemini-style) ───────────────────────────────

class TestRenamedFields:

    def _load_renamed(self):
        return json.loads((FIXTURES / "renamed_fields.json").read_text())

    def test_2_4_1_formula_instead_of_latex_fails(self):
        """'formula' key instead of 'latex' → validate_beat reports missing 'latex'."""
        beat = {"beat_id": "r1", "narration": "Formula.", "visual": {"type": "equation_reveal", "formula": "x^2"}}
        errors = validate_beat(beat)
        assert any("latex" in e for e in errors)

    def test_2_4_2_from_to_instead_of_from_to_latex_fails(self):
        """'from'/'to' instead of 'from_latex'/'to_latex' → both reported missing."""
        beat = {
            "beat_id": "r2",
            "narration": "Renamed.",
            "visual": {"type": "equation_transform", "from": "x^2", "to": "2x"},
        }
        errors = validate_beat(beat)
        assert any("from_latex" in e for e in errors)
        assert any("to_latex" in e for e in errors)

    def test_2_4_3_plots_instead_of_functions_fails(self):
        """'plots' instead of 'functions' → validate_beat reports missing 'functions'."""
        beat = {
            "beat_id": "r3",
            "narration": "Plots.",
            "visual": {"type": "graph_plot", "plots": [{"expr": "x**2"}], "x_range": [-3, 3], "y_range": [-9, 9]},
        }
        errors = validate_beat(beat)
        assert any("functions" in e for e in errors)

    def test_2_4_4_points_instead_of_key_points_fails(self):
        """'points' instead of 'key_points' → validate_beat reports missing 'key_points'."""
        beat = {"beat_id": "r4", "narration": "Points.", "visual": {"type": "summary_card", "points": ["P1."]}}
        errors = validate_beat(beat)
        assert any("key_points" in e for e in errors)

    def test_2_4_5_values_instead_of_matrix_values_fails(self):
        """'values' instead of 'matrix_values' → validate_beat reports missing 'matrix_values'."""
        beat = {
            "beat_id": "r5",
            "narration": "Values.",
            "visual": {"type": "matrix_display", "values": [[1, 2], [3, 4]]},
        }
        errors = validate_beat(beat)
        assert any("matrix_values" in e for e in errors)

    def test_2_4_6_wrong_narration_key_results_in_empty_narration_error(self):
        """
        Beat with 'text' key instead of 'narration' → validate_beat sees empty
        narration and reports it. The text_card visual itself is valid.
        """
        beat = {
            "beat_id": "r6",
            "text": "This is the narration.",  # wrong key
            "visual": {"type": "text_card", "text": "Visual text."},
        }
        errors = validate_beat(beat)
        assert any("narration" in e.lower() for e in errors)

    def test_all_renamed_field_beats_have_errors(self):
        """
        Most beats in renamed_fields.json produce at least one error.
        r6 is a special case: it has a 'narration' key with real text AND a valid
        text_card visual, so validate_beat passes for it. The 'text' sibling key
        is irrelevant to the validator — it's just extra data.
        """
        beats = self._load_renamed()
        # r1-r5 all have missing required fields → should have errors
        beats_expecting_errors = [b for b in beats if b["beat_id"] != "r6"]
        for beat in beats_expecting_errors:
            errors = validate_beat(beat)
            assert len(errors) > 0, f"Expected errors for beat {beat['beat_id']}"


# ── Section 2.5: Wrong field types ───────────────────────────────────────────

class TestWrongFieldTypes:

    def _load_wrong_types(self):
        return json.loads((FIXTURES / "wrong_field_types.json").read_text())

    def test_2_5_1_x_range_string_passes_validator_but_scene_will_fail(self):
        """
        validator only checks presence, not the type of x_range.
        x_range="-5 to 5" (string) passes validate_beat.
        Scene-level error recovery handles the runtime failure.
        """
        beat = {
            "beat_id": "w1",
            "narration": "String range.",
            "visual": {
                "type": "graph_plot",
                "functions": [{"expr": "x**2"}],
                "x_range": "-5 to 5",
                "y_range": [-25, 25],
            },
        }
        # The required fields are all present → validator passes
        errors = validate_beat(beat)
        assert not any("x_range" in e for e in errors)

    def test_2_5_2_functions_as_dict_passes_validator(self):
        """
        functions as a dict (not list) passes validate_beat (presence check only).
        The scene will fail at runtime and use error recovery.
        """
        beat = {
            "beat_id": "w2",
            "narration": "Dict funcs.",
            "visual": {
                "type": "graph_plot",
                "functions": {"expr": "x**2"},
                "x_range": [-3, 3],
                "y_range": [-9, 9],
            },
        }
        errors = validate_beat(beat)
        # No field is missing — validator passes the type check (presence only)
        assert not any("functions" in e for e in errors)

    def test_2_5_3_step_number_string_passes_validator(self):
        """step_number='1' (string) — validator checks presence, not type."""
        beat = {
            "beat_id": "w3",
            "narration": "String step.",
            "visual": {"type": "step_reveal", "latex": "x^2", "step_number": "1"},
        }
        errors = validate_beat(beat)
        assert not any("step_number" in e for e in errors)

    def test_2_5_4_key_points_as_string_passes_validator(self):
        """key_points as a plain string passes the presence check."""
        beat = {
            "beat_id": "w4",
            "narration": "String pts.",
            "visual": {"type": "summary_card", "key_points": "Only one point."},
        }
        errors = validate_beat(beat)
        assert not any("key_points" in e for e in errors)

    def test_2_5_7_color_as_array_passes_validator(self):
        """color=[255,0,0] passes validate_beat — only 'target' and 'color' presence is checked."""
        beat = {
            "beat_id": "w7",
            "narration": "Array color.",
            "visual": {"type": "highlight", "target": "x^2", "color": [255, 0, 0]},
        }
        errors = validate_beat(beat)
        assert errors == []

    def test_wrong_field_types_fixture_all_have_required_fields(self):
        """
        wrong_field_types.json beats all have required fields present (wrong type,
        not missing). So validate_beat should not report missing field errors.
        """
        beats = self._load_wrong_types()
        for beat in beats:
            errors = validate_beat(beat)
            # Should not be complaining about missing required fields
            assert not any("missing required field" in e for e in errors), (
                f"Unexpected missing field error for {beat['beat_id']}: {errors}"
            )
