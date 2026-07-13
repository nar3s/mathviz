"""Deterministic regression tests for Bayes lesson coherence and visuals."""

from generator.planner import (
    _normalise_lesson_context,
    _postprocess_beats,
    _target_beat_count,
)
from generator.validator import validate_plan_quality


def _outline():
    return {
        "title": "Bayes' theorem with medical tests",
        "total_duration_mins": 3,
        "lesson_context": {},
        "chapters": [
            {"id": "why", "role": "why"},
            {"id": "what", "role": "what"},
            {"id": "how", "role": "how"},
            {"id": "example", "role": "example"},
            {"id": "insight", "role": "insight"},
        ],
    }


def test_three_minute_target_uses_twenty_six_beats():
    assert _target_beat_count(3) == 26


def test_bayes_context_computes_correct_posterior():
    outline = _outline()
    context = _normalise_lesson_context("Explain Bayes theorem", outline)
    assert context["derived"]["true_positives"] == 95
    assert context["derived"]["false_positives"] == 99
    assert context["derived"]["positive_tests"] == 194
    assert context["derived"]["posterior_percent"] == 48.97


def test_bayes_postprocessing_replaces_gaussian_and_injects_native_visuals():
    outline = _outline()
    outline["lesson_context"] = _normalise_lesson_context("Bayes theorem", outline)
    beats = []
    for chapter in outline["chapters"]:
        for i in range(1, 6):
            beats.append({
                "beat_id": f"{chapter['id']}_{i}",
                "narration": "A consistent explanation.",
                "visual": {
                    "type": "graph_plot",
                    "functions": [{"expr": "np.exp(-x**2)"}],
                    "x_range": [-3, 3],
                    "y_range": [0, 1],
                },
            })
    processed = _postprocess_beats(beats, outline, "Bayes theorem", "en")
    types = {beat["visual"]["type"] for beat in processed}
    assert "graph_plot" not in types
    assert {"population_grid", "probability_tree", "probability_bars", "bayes_update"} <= types
    assert validate_plan_quality(processed, "Bayes theorem", 3) == []


def test_raw_latex_text_card_is_routed_to_equation_scene():
    outline = _outline()
    beat = {
        "beat_id": "what_1",
        "narration": "Now compute the fraction.",
        "visual": {"type": "text_card", "text": r"P(A|B)=\frac{P(B|A)P(A)}{P(B)}"},
    }
    processed = _postprocess_beats([beat], outline, "conditional probability", "en")
    assert processed[0]["visual"]["type"] == "equation_reveal"
