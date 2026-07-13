"""
Two-phase scene planner — uses any LLM provider to produce a beat-level plan.

Phase 1 — Outline (one call, ~300 tokens out):
    Topic → chapter structure {title, chapters: [{id, title, concepts, n_beats}]}

Phase 2 — Beats (parallel calls per chapter, ~400 tokens each):
    Chapter context → list of beats [{beat_id, narration, visual: {...}}]

Beats per chapter scale with the requested duration (~10 s/beat), capped
by settings.max_beats_per_chapter to keep each call's output bounded.
Each chapter call retries up to 3 times on failure.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
import re

from config.settings import settings
from generator.llm_client import LLMClient, get_llm_client
from generator.prompts import (
    CHAPTER_JSON_FORMAT,
    CHAPTER_SYSTEM_PROMPT,
    OUTLINE_JSON_FORMAT,
    OUTLINE_SYSTEM_PROMPT,
)
from generator.validator import validate_beats, validate_outline, validate_plan_quality

log = logging.getLogger(__name__)

_MAX_CHAPTER_RETRIES = 3
_MAX_OUTLINE_RETRIES = 3


# ── JSON fence stripper ────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    """Remove accidental ```json ... ``` markdown fences from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        inner = parts[1] if len(parts) > 1 else raw
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.rsplit("```", 1)[0].strip()
    return raw


def _extract_json_region(raw: str) -> str:
    """Remove prose around the first JSON object/array returned by an LLM."""
    raw = _strip_fences(raw)
    starts = [index for index in (raw.find("{"), raw.find("[")) if index >= 0]
    if not starts:
        return raw
    start = min(starts)
    candidate = raw[start:]
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"}": "{", "]": "["}
    for index, char in enumerate(candidate):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
                if not stack:
                    return candidate[: index + 1]
    return candidate


def _escape_string_controls(raw: str) -> str:
    """Escape literal newlines/tabs inside JSON strings without changing layout."""
    result: list[str] = []
    in_string = False
    escaped = False
    replacements = {"\n": r"\n", "\r": r"\r", "\t": r"\t"}
    for char in raw:
        if in_string:
            if escaped:
                result.append(char)
                escaped = False
                continue
            if char == "\\":
                result.append(char)
                escaped = True
                continue
            if char == '"':
                in_string = False
                result.append(char)
                continue
            if ord(char) < 0x20:
                result.append(replacements.get(char, f"\\u{ord(char):04x}"))
                continue
        elif char == '"':
            in_string = True
        result.append(char)
    return "".join(result)


def _close_truncated_json(raw: str) -> str:
    """Conservatively close an EOF-truncated string/object/array."""
    candidate = _escape_string_controls(raw).rstrip()
    stack: list[str] = []
    in_string = False
    escaped = False
    pairs = {"}": "{", "]": "["}
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack and stack[-1] == pairs[char]:
            stack.pop()

    if in_string:
        if escaped:
            candidate += "\\"
        candidate += '"'
    candidate = candidate.rstrip()
    if candidate.endswith(":"):
        candidate += " null"
    if candidate.endswith(","):
        candidate = candidate[:-1]
    closers = {"{": "}", "[": "]"}
    candidate += "".join(closers[opening] for opening in reversed(stack))
    # Models commonly leave a comma immediately before a closing delimiter.
    return re.sub(r",\s*([}\]])", r"\1", candidate)


def _loads_llm_json(raw: str) -> object:
    """Parse common imperfect LLM JSON while remaining deterministic."""
    region = _extract_json_region(raw)
    candidates = [region, _escape_string_controls(region), _close_truncated_json(region)]
    first_error: json.JSONDecodeError | None = None
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
    if first_error is not None:
        raise first_error
    raise json.JSONDecodeError("No JSON object or array found", raw, 0)


def _numeric_setting(name: str, default: float) -> float:
    """Read a numeric setting without letting a mocked Settings object leak in."""
    value = getattr(settings, name, default)
    return float(value) if isinstance(value, (int, float)) else default


def _target_beat_count(duration_mins: int | float) -> int:
    """Number of beats needed to land close to the requested wall-clock time."""
    seconds_per_beat = max(4.0, _numeric_setting("target_beat_duration", 7.0))
    return max(12, math.ceil(float(duration_mins) * 60 / seconds_per_beat))


def _chapter_quota(outline: dict, chapter_index: int) -> int:
    """Distribute the exact content-beat budget across chapters."""
    chapters = outline.get("chapters", [])
    n_chapters = max(1, len(chapters))
    # There is one separator between chapters and one controlled outro.
    content_beats = max(
        n_chapters * 3,
        _target_beat_count(outline.get("total_duration_mins", 5)) - n_chapters,
    )
    base, remainder = divmod(content_beats, n_chapters)
    quota = base + (1 if chapter_index < remainder else 0)
    max_per_chapter = getattr(settings, "max_beats_per_chapter", 8)
    if not isinstance(max_per_chapter, int):
        max_per_chapter = 8
    return min(max_per_chapter, max(3, quota))


def _as_probability(value: object, default: float) -> float:
    """Coerce values such as 0.95, '95%', or '0.95' into [0, 1]."""
    try:
        raw = str(value).strip()
        number = float(raw.rstrip("%"))
        if raw.endswith("%") or number > 1:
            number /= 100
        return min(1.0, max(0.0, number))
    except (TypeError, ValueError):
        return default


def _normalise_lesson_context(topic: str, outline: dict) -> dict:
    """Create a single source of truth shared by all parallel chapter calls."""
    supplied = outline.get("lesson_context")
    context = copy.deepcopy(supplied) if isinstance(supplied, dict) else {}
    context.setdefault("central_example", "A single example carried through the lesson")
    context.setdefault("givens", {})
    context.setdefault("derived", {})
    context.setdefault("notation", {})
    context.setdefault("visual_strategy", "Animate quantities as they change")
    context.setdefault("required_visuals", [])

    topic_text = f"{topic} {outline.get('title', '')}".lower()
    if "bayes" not in topic_text:
        return context

    givens = context["givens"] if isinstance(context["givens"], dict) else {}
    prevalence = _as_probability(givens.get("prevalence"), 0.01)
    sensitivity = _as_probability(givens.get("sensitivity"), 0.95)
    specificity = _as_probability(givens.get("specificity"), 0.99)
    try:
        sample_size = max(100, int(float(givens.get("sample_size", 10_000))))
    except (TypeError, ValueError):
        sample_size = 10_000

    diseased = round(sample_size * prevalence)
    healthy = sample_size - diseased
    true_positives = round(diseased * sensitivity)
    false_negatives = diseased - true_positives
    false_positives = round(healthy * (1 - specificity))
    true_negatives = healthy - false_positives
    positive_tests = true_positives + false_positives
    posterior = true_positives / positive_tests if positive_tests else 0.0

    context.update({
        "central_example": f"A medical screening test in a population of {sample_size:,} people",
        "givens": {
            "sample_size": sample_size,
            "prevalence": prevalence,
            "sensitivity": sensitivity,
            "specificity": specificity,
            "false_positive_rate": 1 - specificity,
        },
        "derived": {
            "diseased": diseased,
            "healthy": healthy,
            "true_positives": true_positives,
            "false_negatives": false_negatives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "positive_tests": positive_tests,
            "posterior_given_positive": round(posterior, 8),
            "posterior_percent": round(posterior * 100, 2),
        },
        "notation": {
            "D": "person has the disease",
            "+": "test result is positive",
            "P(D|+)": "probability of disease after a positive result",
        },
        "visual_strategy": (
            "Use a population grid, a probability tree, count bars, and an animated "
            "prior-to-posterior Bayes update; this is discrete data, not a Gaussian curve."
        ),
        "required_visuals": [
            "population_grid", "probability_tree", "probability_bars", "bayes_update"
        ],
    })
    return context


def _deterministic_outline(topic: str, duration_mins: int) -> dict:
    """Safe five-role outline used only after repeated structured-JSON failures."""
    clean_topic = " ".join(str(topic).split()).strip()
    title = clean_topic[:96].rstrip(" .") or "Math visual lesson"
    outline = {
        "title": title,
        "total_duration_mins": duration_mins,
        "chapters": [
            {
                "id": "why_motivation", "title": "Why this matters", "role": "why",
                "concepts": ["real-world motivation", "central question"], "n_beats": 5,
            },
            {
                "id": "what_definition", "title": "The core idea", "role": "what",
                "concepts": ["intuitive definition", "notation"], "n_beats": 5,
            },
            {
                "id": "how_mechanics", "title": "How it works", "role": "how",
                "concepts": ["step-by-step mechanics", "common pitfalls"], "n_beats": 5,
            },
            {
                "id": "example_worked", "title": "A worked example", "role": "example",
                "concepts": ["numerical example", "verification"], "n_beats": 5,
            },
            {
                "id": "insight_summary", "title": "The deeper insight", "role": "insight",
                "concepts": ["visual intuition", "key takeaway"], "n_beats": 5,
            },
        ],
    }
    outline["lesson_context"] = _normalise_lesson_context(topic, outline)
    return outline


# ── Phase 1: Outline ──────────────────────────────────────────────────────────

async def generate_outline(
    topic: str,
    language: str,
    duration_mins: int,
    client: LLMClient | None = None,
) -> dict:
    """
    Phase 1: call the LLM once to get a chapter outline.

    Args:
        topic:         Plain-text topic description.
        language:      Narration language code (e.g. "en", "hi").
        duration_mins: Target video length in minutes.
        client:        LLMClient instance; created from settings if not provided.

    Returns:
        Outline dict: {title, total_duration_mins, chapters: [...]}

    Raises:
        ValueError: on invalid JSON or failed schema validation.
    """
    if client is None:
        client = get_llm_client(settings)

    lang_note = (
        ""
        if language == "en"
        else f"\nIMPORTANT: Write all 'title' and 'concepts' values in {'Hindi' if language == 'hi' else language}."
    )

    # At ~10 s/beat: 5 min → 30 beats, 3 min → 18 beats, 10 min → 60 beats.
    # n_beats per chapter is overridden in _generate_chapter_beats regardless,
    # but telling the LLM the target chapter count keeps the outline coherent.
    target_beats = _target_beat_count(duration_mins)
    # Cap at 5: the system prompt defines exactly 5 roles (WHY/WHAT/HOW/EXAMPLE/INSIGHT)
    required_chapters = 5

    prompt = (
        f"Create a chapter outline for a {duration_mins}-minute video about: {topic}"
        f"{lang_note}"
        f"\n\nPacing target: exactly {target_beats} beats total including transitions. "
        f"You MUST produce exactly {required_chapters} chapters, one for each required role."
        f"\n\n{OUTLINE_JSON_FORMAT}"
    )

    log.info("Phase 1 — outline for: %.60s (%d min)", topic, duration_mins)

    last_exc: Exception | None = None
    retry_feedback = ""
    saw_outline_shape = False
    for attempt in range(_MAX_OUTLINE_RETRIES):
        try:
            raw = await client.complete(
                system=OUTLINE_SYSTEM_PROMPT,
                user=prompt + retry_feedback,
                max_tokens=settings.outline_output_tokens,
                temperature=0.2,
                label="outline",
            )
            raw = _strip_fences(raw)
            saw_outline_shape = saw_outline_shape or (
                '"chapters"' in raw
                or (
                    '"title"' in raw
                    and any(
                        marker in raw
                        for marker in ('"total_duration_mins"', '"lesson_context"')
                    )
                )
            )
            log.debug("Outline response (%d chars): %.400s", len(raw), raw)

            outline = _loads_llm_json(raw)
            if not isinstance(outline, dict):
                raise ValueError(f"Expected a JSON object, got {type(outline).__name__}")

            errors = validate_outline(outline)
            if errors:
                raise ValueError("Outline validation failed:\n" + "\n".join(errors))

            # Accept any outline with at least 3 chapters. We ask the LLM
            # for `min_chapters` in the prompt, but LLMs often undershoot.
            # Crashing on 5 vs 6 wastes all retries for no good reason.
            got_chapters = len(outline.get("chapters", []))
            if got_chapters < 3:
                raise ValueError(
                    f"Outline has {got_chapters} chapters but need at least 3"
                )

            log.info(
                "Outline: '%s', %d chapters (attempt %d)",
                outline.get("title"), got_chapters, attempt + 1,
            )
            outline["total_duration_mins"] = duration_mins
            outline["lesson_context"] = _normalise_lesson_context(topic, outline)
            return outline

        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Outline attempt %d/%d failed: %s", attempt + 1, _MAX_OUTLINE_RETRIES, exc)
            retry_feedback = (
                "\n\nCORRECTION REQUIRED: Your previous response was invalid: "
                f"{str(exc)[:240]}. Return a shorter, complete raw JSON object. "
                "Do not use markdown, comments, trailing commas, or literal line breaks "
                "inside JSON strings. Check every quote and closing bracket before responding."
            )

    if saw_outline_shape:
        log.error(
            "Outline JSON remained invalid after %d attempts; using deterministic five-role outline",
            _MAX_OUTLINE_RETRIES,
        )
        return _deterministic_outline(topic, duration_mins)
    raise ValueError(f"Outline failed after {_MAX_OUTLINE_RETRIES} attempts: {last_exc}") from last_exc


# ── Phase 2: Chapter beats ────────────────────────────────────────────────────

async def _generate_chapter_beats(
    chapter: dict,
    outline: dict,
    language: str,
    client: LLMClient,
) -> list[dict]:
    """
    Phase 2: generate beats for one chapter (with retry).

    Returns list of beat dicts on success.
    Falls back to a single text_card beat if all retries fail.
    """
    cid     = chapter.get("id",    "chapter")
    ctitle  = chapter.get("title", "Chapter")
    concepts = ", ".join(chapter.get("concepts", []))

    chapters = outline.get("chapters", [])

    # Scale beats per chapter from the target duration — the LLM's n_beats
    # suggestion is unreliable (consistently too low), and a fixed quota
    # caps every video at ~n_chapters × quota beats regardless of the
    # requested length. Separators + closing contribute ~n_chapters beats,
    # so subtract them from the target before dividing.
    idx = next((i for i, c in enumerate(chapters) if c.get("id") == cid), -1)
    n_beats = _chapter_quota(outline, max(0, idx))
    prev_ch = chapters[idx - 1] if idx > 0 else None
    next_ch = chapters[idx + 1] if idx >= 0 and idx < len(chapters) - 1 else None

    prev_note = (
        f"Previous chapter covered: {prev_ch['title']} ({', '.join(prev_ch.get('concepts', []))}). "
        if prev_ch else "This is the first chapter — open with a strong hook.\n"
    )
    next_note = (
        f"Next chapter will cover: {next_ch['title']} ({', '.join(next_ch.get('concepts', []))}). "
        if next_ch else "This is the last chapter — end with a memorable summary."
    )

    lang_note = (
        ""
        if language == "en"
        else f"\nIMPORTANT: Write all narration in {'Hindi' if language == 'hi' else language}. Keep LaTeX in English."
    )

    role = chapter.get("role", "what")  # why | what | how | example | insight
    lesson_context = json.dumps(
        outline.get("lesson_context", {}), ensure_ascii=False, sort_keys=True, indent=2
    )
    bayes_note = ""
    if "bayes" in f"{outline.get('title', '')} {concepts}".lower():
        bayes_note = (
            "\nFor this discrete medical example, never use graph_plot or graph_animate. "
            "Prefer population_grid for WHY, probability_tree for WHAT, probability_bars "
            "for HOW, and bayes_update for EXAMPLE."
        )

    prompt = (
        f"Generate exactly {n_beats} beats for the '{ctitle}' chapter "
        f"of a {outline.get('total_duration_mins', 5)}-minute video about '{outline.get('title', '')}'.\n"
        f"Chapter role: {role.upper()} — follow the '{role}' beat arc from the system prompt.\n"
        f"This chapter covers: {concepts}.\n\n"
        f"{prev_note}{next_note}{lang_note}\n\n"
        "SHARED LESSON CONTEXT (the single source of truth):\n"
        f"{lesson_context}\n"
        "Use these exact givens and derived values. Do not invent, round differently, "
        "or contradict any number, notation, example, or conclusion in this context."
        f"{bayes_note}\n\n"
        f"Use beat_ids: '{cid}_1', '{cid}_2', ...\n\n"
        f"{CHAPTER_JSON_FORMAT}"
    )

    retry_feedback = ""
    for attempt_num in range(_MAX_CHAPTER_RETRIES):
        try:
            log.info(
                "Phase 2 — chapter '%s' (%d beats, attempt %d)",
                cid, n_beats, attempt_num + 1,
            )
            raw = await client.complete(
                system=CHAPTER_SYSTEM_PROMPT,
                user=prompt + retry_feedback,
                max_tokens=settings.max_chapter_output_tokens,
                temperature=0.4,
                label=f"chapter:{cid}",
            )
            raw = _strip_fences(raw)

            parsed = _loads_llm_json(raw)
            if isinstance(parsed, dict):
                # unwrap common wrapping patterns
                for key in ("beats", "chapter_beats", "items", "data"):
                    if isinstance(parsed.get(key), list):
                        parsed = parsed[key]
                        break
                else:
                    parsed = list(parsed.values())[0] if parsed else []

            if not isinstance(parsed, list):
                raise ValueError(f"Expected a JSON array, got {type(parsed)}")

            errors = validate_beats(parsed)
            if errors:
                raise ValueError("Beat validation errors:\n" + "\n".join(errors[:5]))

            log.info("Chapter '%s': %d beats generated", cid, len(parsed))
            return parsed

        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Chapter '%s' attempt %d/%d failed: %s",
                cid, attempt_num + 1, _MAX_CHAPTER_RETRIES, exc,
            )
            retry_feedback = (
                "\n\nCORRECTION REQUIRED: Your previous response was invalid: "
                f"{str(exc)[:240]}. Return a shorter, complete raw JSON array with exactly "
                f"{n_beats} beats. Do not use markdown, comments, trailing commas, or "
                "literal line breaks inside JSON strings. Check all quotes and brackets."
            )
            if attempt_num == _MAX_CHAPTER_RETRIES - 1:
                log.error("Chapter '%s': all retries exhausted — using fallback", cid)
                return [
                    {
                        "beat_id": f"{cid}_1",
                        "narration": f"This section covers {ctitle}.",
                        "visual": {"type": "text_card", "text": ctitle},
                    }
                ]

    return []  # unreachable, but satisfies type checker


# ── Public entry point ────────────────────────────────────────────────────────

_SEPARATOR_NARRATION = {
    "en": "Now let us move on: {title}.",
    "hi": "अब अगला भाग: {title}।",
}

_CLOSING_NARRATION = {
    "en": (
        "And that wraps up our journey through {video_title} — "
        "from motivation to mechanics to real examples. Keep exploring!"
    ),
    "hi": (
        "और इस तरह {video_title} की हमारी यात्रा पूरी हुई — "
        "प्रेरणा से लेकर उदाहरणों तक। खोजते रहें!"
    ),
}


def _population_visual(context: dict) -> dict:
    derived = context["derived"]
    return {
        "type": "population_grid",
        "title": f"A population of {context['givens']['sample_size']:,} people",
        "total": context["givens"]["sample_size"],
        "groups": [
            {"label": "True positive", "count": derived["true_positives"], "color": "GREEN"},
            {"label": "False negative", "count": derived["false_negatives"], "color": "RED"},
            {"label": "False positive", "count": derived["false_positives"], "color": "YELLOW"},
            {"label": "True negative", "count": derived["true_negatives"], "color": "BLUE"},
        ],
    }


def _tree_visual(context: dict) -> dict:
    givens = context["givens"]
    return {
        "type": "probability_tree",
        "root_label": "One tested person",
        "branches": [
            {
                "label": "Disease",
                "probability": givens["prevalence"],
                "children": [
                    {"label": "Positive", "probability": givens["sensitivity"]},
                    {"label": "Negative", "probability": 1 - givens["sensitivity"]},
                ],
            },
            {
                "label": "Healthy",
                "probability": 1 - givens["prevalence"],
                "children": [
                    {"label": "Positive", "probability": givens["false_positive_rate"]},
                    {"label": "Negative", "probability": givens["specificity"]},
                ],
            },
        ],
    }


def _bars_visual(context: dict) -> dict:
    givens = context["givens"]
    posterior = context["derived"]["posterior_given_positive"]
    return {
        "type": "probability_bars",
        "title": "Prior evidence and updated belief",
        "bars": [
            {"label": "Prior P(D)", "value": givens["prevalence"], "color": "BLUE"},
            {"label": "Sensitivity", "value": givens["sensitivity"], "color": "GREEN"},
            {"label": "False-positive rate", "value": givens["false_positive_rate"], "color": "YELLOW"},
            {"label": "Posterior P(D | +)", "value": posterior, "color": "PURPLE"},
        ],
    }


def _bayes_update_visual(context: dict) -> dict:
    givens = context["givens"]
    return {
        "type": "bayes_update",
        "prior": givens["prevalence"],
        "sensitivity": givens["sensitivity"],
        "specificity": givens["specificity"],
        "sample_size": givens["sample_size"],
    }


def _beats_for_role(beats: list[dict], chapters: list[dict], role: str) -> list[dict]:
    ids = [str(ch.get("id", "")) for ch in chapters if ch.get("role") == role]
    return [
        beat for beat in beats
        if any(str(beat.get("beat_id", "")).startswith(f"{cid}_") for cid in ids)
    ]


def _postprocess_beats(
    beats: list[dict], outline: dict, topic: str, language: str
) -> list[dict]:
    """Repair common LLM visual mistakes and enforce topic-specific invariants."""
    beats = copy.deepcopy(beats)

    # Raw LaTeX in Text() renders as tiny literal markup. Route it to MathTex.
    latex_markers = (r"\frac", r"\begin", r"\sum", r"\int", r"\sqrt")
    for beat in beats:
        visual = beat.get("visual", {})
        if visual.get("type") == "text_card" and any(
            marker in str(visual.get("text", "")) for marker in latex_markers
        ):
            beat["visual"] = {
                "type": "equation_reveal",
                "latex": str(visual["text"]),
                "label": visual.get("title", ""),
            }

    # A lesson should build visually, not end every chapter with another recap.
    summary_indexes = [
        i for i, beat in enumerate(beats)
        if beat.get("visual", {}).get("type") == "summary_card"
    ]
    for index in summary_indexes[:-1]:
        points = beats[index]["visual"].get("key_points", [])
        title = str(points[0]) if points else "One idea to remember"
        beats[index]["visual"] = {"type": "title_card", "title": title}

    context = outline.get("lesson_context", {})
    is_bayes = "bayes" in f"{topic} {outline.get('title', '')}".lower()
    if not is_bayes or not isinstance(context.get("derived"), dict):
        return beats

    # Discrete screening outcomes are counts and branches, never bell curves.
    for beat in beats:
        if beat.get("visual", {}).get("type") in {"graph_plot", "graph_animate"}:
            beat["visual"] = _bars_visual(context)

    chapters = outline.get("chapters", [])
    why_beats = _beats_for_role(beats, chapters, "why")
    what_beats = _beats_for_role(beats, chapters, "what")
    how_beats = _beats_for_role(beats, chapters, "how")
    example_beats = _beats_for_role(beats, chapters, "example")

    if why_beats:
        why_beats[0]["visual"] = _population_visual(context)
    if what_beats:
        what_beats[min(1, len(what_beats) - 1)]["visual"] = _tree_visual(context)
    if how_beats:
        how_beats[0]["visual"] = _bars_visual(context)

    derived = context["derived"]
    givens = context["givens"]
    if example_beats:
        example_beats[0]["visual"] = _population_visual(context)
        if language == "en":
            example_beats[0]["narration"] = (
                f"Start with {givens['sample_size']:,} people: {derived['diseased']} have the disease "
                f"and {derived['healthy']:,} do not."
            )
    if len(example_beats) > 1:
        example_beats[1]["visual"] = {
            "type": "step_reveal",
            "latex": (
                f"{derived['diseased']} \\times {givens['sensitivity']:.2f}"
                f" = {derived['true_positives']}"
            ),
            "step_number": 1,
        }
        if language == "en":
            example_beats[1]["narration"] = (
                f"Sensitivity catches {derived['true_positives']} of the "
                f"{derived['diseased']} people who truly have the disease."
            )
    if len(example_beats) > 2:
        example_beats[2]["visual"] = {
            "type": "step_reveal",
            "latex": (
                f"{derived['healthy']} \\times {givens['false_positive_rate']:.2f}"
                f" = {derived['false_positives']}"
            ),
            "step_number": 2,
        }
        if language == "en":
            example_beats[2]["narration"] = (
                f"The one-percent false-positive rate also flags {derived['false_positives']} "
                "healthy people, creating the surprise."
            )
    if len(example_beats) > 3:
        example_beats[3]["visual"] = _bayes_update_visual(context)
        if language == "en":
            example_beats[3]["narration"] = (
                f"Among {derived['positive_tests']} positive tests, only "
                f"{derived['true_positives']} are true, so the updated probability is "
                f"{derived['posterior_percent']:.2f} percent."
            )
    if len(example_beats) > 4:
        example_beats[4]["visual"] = {
            "type": "equation_reveal",
            "latex": (
                f"P(D\\mid +)=\\frac{{{derived['true_positives']}}}"
                f"{{{derived['true_positives']}+{derived['false_positives']}}}"
                f"\\approx {derived['posterior_given_positive']:.4f}"
            ),
            "label": "The count form of Bayes' theorem",
        }

    # Short outputs can still miss a role; replace safe candidates so every
    # probability lesson has all four purpose-built animations.
    present = {beat.get("visual", {}).get("type") for beat in beats}
    required = {
        "population_grid": _population_visual,
        "probability_tree": _tree_visual,
        "probability_bars": _bars_visual,
        "bayes_update": _bayes_update_visual,
    }
    candidates = [
        beat for beat in beats
        if beat.get("visual", {}).get("type") in {"text_card", "pause", "title_card"}
        and not str(beat.get("beat_id", "")).startswith("ch")
        and beat.get("beat_id") != "closing_outro"
    ]
    for visual_type, factory in required.items():
        if visual_type not in present and candidates:
            candidates.pop(0)["visual"] = factory(context)
            present.add(visual_type)

    return beats


async def generate_scene_plan(
    topic: str,
    language: str = "en",
    duration_mins: int = 5,
) -> dict:
    """
    Full two-phase plan: outline → parallel chapter beats → flat beat list.

    Args:
        topic:        User's plain-text topic description.
        language:     Narration language code (e.g. "en", "hi").
        duration_mins: Target video length in minutes.

    Returns:
        Plan dict: {title, beats: [...]}

    Raises:
        ValueError: If the outline call fails and cannot be recovered.
    """
    client = get_llm_client(settings)

    outline = await generate_outline(topic, language, duration_mins, client=client)

    chapters = outline["chapters"]
    chapter_beats_lists: list[list[dict]] = await asyncio.gather(
        *[_generate_chapter_beats(ch, outline, language, client) for ch in chapters]
    )

    # ── Assemble beats with chapter separators ────────────────────────────────
    # Inject a title card between chapters (not before the first one — the LLM
    # already opens with a hook). These are code-controlled, not LLM-generated,
    # so they are always present and always give the viewer a moment to breathe.
    beats: list[dict] = []
    n_chapters = len(chapters)

    for i, (chapter, chapter_beats) in enumerate(zip(chapters, chapter_beats_lists)):
        if i > 0:
            # Separator: brief narration + chapter title card
            sep_template = _SEPARATOR_NARRATION.get(language, _SEPARATOR_NARRATION["en"])
            beats.append({
                "beat_id": f"ch{i + 1}_intro",
                "narration": sep_template.format(title=chapter["title"]),
                "visual": {
                    "type": "title_card",
                    "title": chapter["title"],
                    "subtitle": f"Part {i + 1} of {n_chapters}",
                },
            })
        beats.extend(chapter_beats)

    # ── Controlled outro ──────────────────────────────────────────────────────
    # Always end with a deliberate wind-down so the video never feels abrupt.
    closing_template = _CLOSING_NARRATION.get(language, _CLOSING_NARRATION["en"])
    beats.append({
        "beat_id": "closing_outro",
        "narration": closing_template.format(video_title=outline["title"]),
        "visual": {
            "type": "title_card",
            "title": "Keep exploring",
            "subtitle": outline["title"],
        },
    })

    beats = _postprocess_beats(beats, outline, topic, language)
    quality_warnings = validate_plan_quality(beats, topic, duration_mins)
    for warning in quality_warnings:
        log.warning("Plan quality: %s", warning)

    log.info(
        "Plan complete: '%s', %d chapters, %d beats total (incl. %d separators + closing)",
        outline["title"], n_chapters, len(beats), n_chapters - 1,
    )

    # Duration sanity check: at ~10 s/beat, warn when the plan can't reach
    # the requested length (e.g. chapter cap hit on long videos).
    planned_secs = len(beats) * _numeric_setting("target_beat_duration", 7.0)
    target_secs  = duration_mins * 60
    if planned_secs < target_secs * 0.8:
        log.warning(
            "Planned ~%ds of content for a %d-min target (%d beats). "
            "Consider raising max_beats_per_chapter or chapter count.",
            planned_secs, duration_mins, len(beats),
        )

    return {
        "title": outline["title"],
        "target_duration_mins": duration_mins,
        "beats": beats,
        "lesson_context": outline.get("lesson_context", {}),
        "quality_warnings": quality_warnings,
    }
