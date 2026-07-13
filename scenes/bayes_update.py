"""Prior-to-posterior Bayes update with exact screening-test counts."""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, WHITE, FadeIn, Rectangle, Transform, VGroup

from scenes.base import BaseEngineeringScene


class BayesUpdateScene(BaseEngineeringScene):
    prior: float = 0.01
    sensitivity: float = 0.95
    specificity: float = 0.99
    sample_size: int = 10_000

    def construct(self) -> None:
        self.setup_theme()
        self.add_audio()

        prior = min(1.0, max(0.0, float(self.prior)))
        sensitivity = min(1.0, max(0.0, float(self.sensitivity)))
        specificity = min(1.0, max(0.0, float(self.specificity)))
        sample_size = max(1, int(self.sample_size))
        diseased = round(sample_size * prior)
        healthy = sample_size - diseased
        true_positives = round(diseased * sensitivity)
        false_positives = round(healthy * (1 - specificity))
        denominator = true_positives + false_positives
        posterior = true_positives / denominator if denominator else 0.0

        title = self.safe_text("Bayes update", font_size=40, color=WHITE, weight="BOLD")
        title.to_edge(UP, buff=0.35)
        prior_label = self.safe_text("Prior", font_size=25, color=WHITE)
        posterior_label = self.safe_text("Posterior after +", font_size=25, color=WHITE)
        prior_label.move_to(LEFT * 3.8 + UP * 1.25)
        posterior_label.move_to(LEFT * 3.8 + DOWN * 0.05)

        prior_bar = Rectangle(
            width=max(0.06, 6.3 * prior), height=0.48,
            fill_color="#58C4DD", fill_opacity=0.9, stroke_width=0,
        ).align_to(LEFT * 1.7, LEFT).move_to(LEFT * 1.7 + UP * 1.25, coor_mask=[0, 1, 0])
        prior_bar.align_to(LEFT * 1.7, LEFT)
        posterior_bar = Rectangle(
            width=max(0.06, 6.3 * posterior), height=0.48,
            fill_color="#9A72AC", fill_opacity=0.95, stroke_width=0,
        ).align_to(LEFT * 1.7, LEFT).move_to(LEFT * 1.7 + DOWN * 0.05, coor_mask=[0, 1, 0])
        posterior_bar.align_to(LEFT * 1.7, LEFT)
        prior_number = self.safe_text(f"{prior:.2%}", font_size=27, color=WHITE)
        prior_number.next_to(prior_bar, RIGHT, buff=0.15)
        posterior_number = self.safe_text(f"{posterior:.2%}", font_size=27, color=WHITE)
        posterior_number.next_to(posterior_bar, RIGHT, buff=0.15)

        counts = self.safe_text(
            f"{true_positives} true positives  ÷  "
            f"({true_positives} true + {false_positives} false positives)",
            font_size=24,
            color=WHITE,
            max_chars_per_line=58,
        ).move_to(DOWN * 1.35)
        formula = self.safe_text(
            f"P(D | +) = {true_positives} / ({true_positives} + {false_positives}) "
            f"≈ {posterior:.4f}",
            font_size=30,
            color=self.accent_color,
            max_chars_per_line=58,
        ).move_to(DOWN * 2.35)

        self.play(FadeIn(VGroup(title, prior_label, prior_bar, prior_number)), run_time=0.7)
        update_bar = prior_bar.copy()
        self.add(update_bar)
        self.play(
            Transform(update_bar, posterior_bar),
            FadeIn(VGroup(posterior_label, posterior_number)),
            run_time=1.1,
        )
        self.play(FadeIn(counts, shift=UP * 0.15), run_time=0.6)
        self.play(FadeIn(formula), run_time=0.7)
        self.pad_to_duration()
