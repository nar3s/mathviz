"""
TitleCardScene — animated title + subtitle intro beat.

Beat params (set as class attributes by the registry):
  title:    str   — main title text
  subtitle: str   — optional subtitle (default None)
"""

from __future__ import annotations

from manim import DOWN, UP, FadeIn, FadeOut, VGroup, WHITE

from scenes.base import BaseEngineeringScene


class TitleCardScene(BaseEngineeringScene):
    title: str = "Title"
    subtitle: str | None = None

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()
        self.show_title(
            str(self.title),
            subtitle=str(self.subtitle) if self.subtitle else None,
            duration=self.total_duration,
        )
        self.pad_to_duration()
