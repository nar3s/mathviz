"""Helpers for keeping the assembled video close to its requested duration."""

from __future__ import annotations


def balance_durations(
    durations: dict[str, float], target_seconds: float
) -> dict[str, float]:
    """Spread a duration shortfall across beats as readable visual hold time.

    Narration is never shortened. If speech already exceeds the requested
    duration, the original durations are returned unchanged.
    """
    balanced = {beat_id: max(0.0, float(value)) for beat_id, value in durations.items()}
    if not balanced:
        return balanced
    shortfall = float(target_seconds) - sum(balanced.values())
    if shortfall <= 0:
        return balanced
    extra_per_beat = shortfall / len(balanced)
    return {
        beat_id: value + extra_per_beat
        for beat_id, value in balanced.items()
    }
