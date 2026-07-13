"""Animated two-level probability tree."""

from __future__ import annotations

from manim import LEFT, RIGHT, UP, WHITE, Circle, Create, FadeIn, Line, VGroup

from scenes.base import BaseEngineeringScene


class ProbabilityTreeScene(BaseEngineeringScene):
    root_label: str = "Start"
    branches: list = []

    def _node(self, label: str, probability: object | None = None) -> VGroup:
        circle = Circle(radius=0.36, color=self.accent_color, stroke_width=2)
        text = self.safe_text(label, font_size=18, color=WHITE, max_chars_per_line=16)
        text.move_to(circle)
        node = VGroup(circle, text)
        if probability is not None:
            try:
                probability_text = f"{float(probability):.1%}"
            except (TypeError, ValueError):
                probability_text = str(probability)
            value = self.safe_text(probability_text, font_size=17, color=self.accent_color)
            value.next_to(circle, UP, buff=0.08)
            node.add(value)
        return node

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        branches = (self.branches or [])[:2]
        root = self._node(self.root_label).move_to(LEFT * 5)
        branch_nodes = VGroup()
        child_nodes = VGroup()
        lines = VGroup()

        y_positions = [1.8, -1.8]
        child_offsets = [0.72, -0.72]
        for i, branch in enumerate(branches):
            branch_node = self._node(
                str(branch.get("label", "Branch")), branch.get("probability")
            ).move_to(LEFT * 1.4 + UP * y_positions[i])
            branch_nodes.add(branch_node)
            lines.add(Line(root.get_right(), branch_node.get_left(), color=self.accent_color))
            for child_index, child in enumerate((branch.get("children") or [])[:2]):
                child_node = self._node(
                    str(child.get("label", "Outcome")), child.get("probability")
                ).move_to(RIGHT * 3.3 + UP * (y_positions[i] + child_offsets[child_index]))
                child_nodes.add(child_node)
                lines.add(Line(branch_node.get_right(), child_node.get_left(), color=WHITE))

        diagram = VGroup(root, lines, branch_nodes, child_nodes)
        self.fit(diagram, margin_x=0.9, margin_y=0.8)
        self.play(FadeIn(root), run_time=0.45)
        if lines:
            self.play(Create(lines), run_time=0.9)
        self.play(FadeIn(branch_nodes, lag_ratio=0.2), run_time=0.7)
        self.play(FadeIn(child_nodes, lag_ratio=0.15), run_time=0.8)
        self.pad_to_duration()
