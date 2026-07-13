"""Render the probability-native scenes with the canonical Bayes example."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator.planner import (  # noqa: E402
    _bars_visual,
    _bayes_update_visual,
    _normalise_lesson_context,
    _population_visual,
    _tree_visual,
)
from renderer import render_engine, scene_builder  # noqa: E402


async def main() -> None:
    outline = {"title": "Bayes theorem medical test", "lesson_context": {}}
    context = _normalise_lesson_context("Bayes theorem", outline)
    visuals = {
        "population": _population_visual(context),
        "tree": _tree_visual(context),
        "bars": _bars_visual(context),
        "update": _bayes_update_visual(context),
    }
    beats = [
        {"beat_id": beat_id, "narration": "Visual verification.", "visual": visual}
        for beat_id, visual in visuals.items()
    ]
    root = ROOT / "output" / "verification"
    entries = scene_builder.build_all_scene_files(
        beats=beats,
        style={"theme": "dark", "accent_color": "#58C4DD"},
        durations={beat_id: 5.5 for beat_id in visuals},
        audio_paths={},
        scene_dir=root / "scene_files",
    )
    tasks = [
        (beat_id, scene_file, class_name, root / "media" / beat_id)
        for beat_id, scene_file, class_name in entries
    ]
    rendered, errors = await render_engine.render_all_parallel(
        tasks, quality="low", max_workers=1
    )
    if errors:
        raise RuntimeError(errors)
    print("\n".join(str(path) for path in rendered.values()))


if __name__ == "__main__":
    asyncio.run(main())
