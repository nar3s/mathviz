"""
Safe-zone constants and fit helpers for ManimCE frame boundaries.

Manim frame (1080p, 16:9): 14.222... × 8 units
Safe zone: [-6.5, 6.5] × [-3.5, 3.5]  (0.36 unit margin on each side)
"""

from __future__ import annotations

from manim import Mobject, config as manim_config

# Total safe dimensions (units)
SAFE_WIDTH: float = 13.0   # 6.5 × 2
SAFE_HEIGHT: float = 7.0   # 3.5 × 2

# As fractions of the full frame (for margin_x / margin_y usage)
MARGIN_X: float = SAFE_WIDTH  / manim_config.frame_width   # ~0.914
MARGIN_Y: float = SAFE_HEIGHT / manim_config.frame_height  # ~0.875


def fit_mobject(
    mob: Mobject,
    max_width: float = SAFE_WIDTH,
    max_height: float = SAFE_HEIGHT,
) -> Mobject:
    """Scale `mob` down so it fits within the safe zone. Never scales up."""
    if mob.width > max_width:
        mob.scale(max_width / mob.width)
    if mob.height > max_height:
        mob.scale(max_height / mob.height)
    return mob


def fit_to_width(mob: Mobject, max_width: float = SAFE_WIDTH) -> Mobject:
    """Scale `mob` down if its width exceeds `max_width`. Never scales up."""
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    return mob


def fit_to_height(mob: Mobject, max_height: float = SAFE_HEIGHT) -> Mobject:
    """Scale `mob` down if its height exceeds `max_height`. Never scales up."""
    if mob.height > max_height:
        mob.scale_to_fit_height(max_height)
    return mob
