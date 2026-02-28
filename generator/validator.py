"""
Beat and outline JSON validation — deterministic, zero LLM cost.

Validation layers:
  1. Beat schema (required fields, allowed types)
  2. LaTeX brace matching
  3. LaTeX command whitelist
  4. Outline schema (chapters, n_beats)
"""

from __future__ import annotations

import re

# ── Beat types ────────────────────────────────────────────────────────────────

ALLOWED_BEAT_TYPES = {
    "title_card",
    "equation_reveal",
    "equation_transform",
    "highlight",
    "step_reveal",
    "graph_plot",
    "graph_animate",
    "vector_show",
    "vector_transform",
    "matrix_display",
    "summary_card",
    "theorem_card",
    "text_card",
    "pause",
}

# Fields required in visual{} for each beat type
REQUIRED_VISUAL_FIELDS: dict[str, list[str]] = {
    "title_card":         ["title"],
    "equation_reveal":    ["latex"],
    "equation_transform": ["from_latex", "to_latex"],
    "highlight":          ["target", "color"],
    "step_reveal":        ["latex", "step_number"],
    "graph_plot":         ["functions", "x_range", "y_range"],
    "graph_animate":      ["function_expr", "parameter", "range"],
    "vector_show":        ["vectors"],
    "vector_transform":   ["matrix", "vectors"],
    "matrix_display":     ["matrix_values"],
    "summary_card":       ["key_points"],
    "theorem_card":       ["theorem_name", "statement_latex"],
    "text_card":          ["text"],
    "pause":              [],
}

# LaTeX fields that should pass brace validation
_LATEX_FIELDS = {"latex", "from_latex", "to_latex", "target", "statement_latex"}

# ── Layer 1: Brace matching ───────────────────────────────────────────────────

def check_braces(latex: str) -> bool:
    """Return True if { } braces in `latex` are balanced."""
    depth = 0
    for char in latex:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


# ── Layer 2: Command whitelist ────────────────────────────────────────────────

ALLOWED_COMMANDS: set[str] = {
    # Fractions & operators
    r"\frac", r"\dfrac", r"\sqrt", r"\pm", r"\mp", r"\cdot",
    r"\times", r"\div",
    # Greek letters
    r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon", r"\theta",
    r"\lambda", r"\mu", r"\sigma", r"\phi", r"\psi", r"\omega", r"\pi",
    r"\eta", r"\kappa", r"\nu", r"\rho", r"\tau", r"\xi", r"\zeta",
    r"\Gamma", r"\Delta", r"\Theta", r"\Lambda", r"\Sigma", r"\Phi",
    r"\Psi", r"\Omega", r"\Pi",
    # Calculus
    r"\int", r"\iint", r"\iiint", r"\oint", r"\sum", r"\prod",
    r"\lim", r"\infty", r"\partial", r"\nabla",
    # Linear algebra
    r"\vec", r"\hat", r"\bar", r"\dot", r"\ddot",
    r"\begin", r"\end",
    r"\det", r"\tr", r"\rank",
    # Relations
    r"\leq", r"\geq", r"\neq", r"\approx", r"\equiv", r"\sim",
    r"\rightarrow", r"\Rightarrow", r"\leftarrow", r"\Leftarrow",
    r"\leftrightarrow", r"\implies", r"\iff",
    r"\in", r"\notin", r"\subset", r"\subseteq", r"\cup", r"\cap",
    r"\forall", r"\exists",
    # Formatting
    r"\text", r"\mathrm", r"\mathbf", r"\mathbb", r"\mathcal",
    r"\left", r"\right", r"\big", r"\Big", r"\bigg", r"\Bigg",
    r"\quad", r"\qquad", r"\,", r"\;", r"\:", r"\!",
    r"\underbrace", r"\overbrace",
    r"\overline", r"\underline",
    r"\binom", r"\choose",
    r"\cdots", r"\ldots", r"\ddots", r"\vdots",
    r"\not", r"\mid",
    # Standard functions
    r"\sin", r"\cos", r"\tan", r"\cot", r"\sec", r"\csc",
    r"\arcsin", r"\arccos", r"\arctan",
    r"\sinh", r"\cosh", r"\tanh",
    r"\log", r"\ln", r"\exp",
    r"\max", r"\min", r"\sup", r"\inf", r"\arg",
    r"\Re", r"\Im",
    r"\gcd", r"\lcm",
}


def check_commands(latex: str) -> list[str]:
    """Return list of LaTeX commands that are NOT in the allowed set."""
    commands = re.findall(r"\\[a-zA-Z]+", latex)
    return [cmd for cmd in commands if cmd not in ALLOWED_COMMANDS]


# ── Beat validation ───────────────────────────────────────────────────────────

def validate_beat(beat: dict) -> list[str]:
    """Validate a single beat dict. Returns a list of error strings (empty = OK)."""
    errors: list[str] = []
    bid = beat.get("beat_id", "?")

    if not beat.get("beat_id"):
        errors.append("Beat missing 'beat_id'")

    if not beat.get("narration", "").strip():
        errors.append(f"Beat '{bid}': empty narration")

    visual = beat.get("visual")
    if not visual:
        errors.append(f"Beat '{bid}': missing 'visual'")
        return errors

    beat_type = visual.get("type")
    if beat_type not in ALLOWED_BEAT_TYPES:
        errors.append(
            f"Beat '{bid}': unknown visual type '{beat_type}'. "
            f"Allowed: {sorted(ALLOWED_BEAT_TYPES)}"
        )
        return errors

    for field in REQUIRED_VISUAL_FIELDS.get(beat_type, []):
        if field not in visual:
            errors.append(f"Beat '{bid}' ({beat_type}): missing required field '{field}'")

    for latex_field in _LATEX_FIELDS:
        val = visual.get(latex_field, "")
        if val and not check_braces(str(val)):
            errors.append(
                f"Beat '{bid}': unbalanced braces in '{latex_field}': {str(val)[:80]}"
            )

    return errors


def validate_beats(beats: list[dict]) -> list[str]:
    """Validate a list of beats. Returns combined error list."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    for beat in beats:
        bid = beat.get("beat_id", "")
        if bid and bid in seen_ids:
            errors.append(f"Duplicate beat_id: '{bid}'")
        if bid:
            seen_ids.add(bid)
        errors.extend(validate_beat(beat))

    return errors


# ── Outline validation ────────────────────────────────────────────────────────

def validate_outline(outline: dict) -> list[str]:
    """Validate a Phase-1 outline dict. Returns list of error strings."""
    errors: list[str] = []

    if not outline.get("title"):
        errors.append("Outline missing 'title'")

    chapters = outline.get("chapters")
    if not chapters:
        errors.append("Outline has no 'chapters'")
        return errors

    if not isinstance(chapters, list):
        errors.append("Outline 'chapters' must be a list")
        return errors

    seen_ids: set[str] = set()
    for i, ch in enumerate(chapters):
        cid = ch.get("id", f"chapter_{i}")
        if not ch.get("id"):
            errors.append(f"Chapter {i}: missing 'id'")
        elif cid in seen_ids:
            errors.append(f"Duplicate chapter id: '{cid}'")
        else:
            seen_ids.add(cid)

        if not ch.get("title"):
            errors.append(f"Chapter '{cid}': missing 'title'")

        n = ch.get("n_beats")
        if n is None:
            errors.append(f"Chapter '{cid}': missing 'n_beats'")
        elif not isinstance(n, int) or n < 1:
            errors.append(f"Chapter '{cid}': 'n_beats' must be a positive integer, got {n!r}")

    return errors
