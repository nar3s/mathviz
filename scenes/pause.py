"""
PauseScene — a brief visual pause where nothing changes.

Beat params: (none)
"""

from __future__ import annotations

from scenes.base import BaseEngineeringScene


class PauseScene(BaseEngineeringScene):
    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()
        self.pad_to_duration()
