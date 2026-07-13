"""Tests for whole-video duration balancing."""

import pytest

from renderer.timing import balance_durations


def test_shortfall_is_distributed_to_reach_target():
    result = balance_durations({"a": 5.5, "b": 6.5, "c": 7.0}, 30)
    assert sum(result.values()) == pytest.approx(30)
    assert result["a"] > 5.5


def test_long_narration_is_never_shortened():
    original = {"a": 12.0, "b": 10.0}
    assert balance_durations(original, 20) == original


def test_empty_duration_map_stays_empty():
    assert balance_durations({}, 180) == {}
