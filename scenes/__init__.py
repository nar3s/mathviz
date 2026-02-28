"""
Beat scene registry.

build_beat_scene(beat, style) → a dynamically created Scene subclass
    configured with the beat's visual parameters and style.

The returned class can be subclassed (by the generated .py file) to inject
total_duration and audio_file.
"""

from __future__ import annotations

import re

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

_REGISTRY: dict[str, type[BaseEngineeringScene]] = {
    "title_card":         TitleCardScene,
    "equation_reveal":    EquationRevealScene,
    "equation_transform": EquationTransformScene,
    "highlight":          HighlightScene,
    "step_reveal":        StepRevealScene,
    "graph_plot":         GraphPlotScene,
    "graph_animate":      GraphAnimateScene,
    "vector_show":        VectorShowScene,
    "vector_transform":   VectorTransformScene,
    "matrix_display":     MatrixDisplayScene,
    "summary_card":       SummaryCardScene,
    "theorem_card":       TheoremCardScene,
    "text_card":          TextCardScene,
    "pause":              PauseScene,
}


def build_beat_scene(beat: dict, style: dict) -> type[BaseEngineeringScene]:
    """
    Return a BaseEngineeringScene subclass configured for this beat's visual.

    The returned class has the visual params and style set as class attributes.
    The generated .py subclasses it to inject total_duration and audio_file.

    Args:
        beat:  Beat dict with 'beat_id', 'narration', and 'visual'.
        style: Style dict with 'theme' and 'accent_color'.

    Returns:
        A dynamically created class inheriting from the appropriate scene class.
    """
    visual    = beat.get("visual", {})
    beat_type = visual.get("type", "text_card")
    base      = _REGISTRY.get(beat_type, TextCardScene)

    # Class attributes: visual fields (minus 'type') + style
    attrs: dict = {k: v for k, v in visual.items() if k != "type"}
    attrs["theme"]        = style.get("theme",        "dark")
    attrs["accent_color"] = style.get("accent_color", "#58C4DD")

    beat_id  = beat.get("beat_id", "unknown")
    safe_id  = re.sub(r"[^a-zA-Z0-9]", "_", beat_id)
    cls_name = f"_BeatScene_{safe_id}"

    return type(cls_name, (base,), attrs)


__all__ = [
    "build_beat_scene",
    "BaseEngineeringScene",
    "TitleCardScene",
    "EquationRevealScene",
    "EquationTransformScene",
    "HighlightScene",
    "StepRevealScene",
    "GraphPlotScene",
    "GraphAnimateScene",
    "VectorShowScene",
    "VectorTransformScene",
    "MatrixDisplayScene",
    "SummaryCardScene",
    "TheoremCardScene",
    "TextCardScene",
    "PauseScene",
]
