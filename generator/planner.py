"""
Two-phase scene planner — uses any LLM provider to produce a beat-level plan.

Phase 1 — Outline (one call, ~300 tokens out):
    Topic → chapter structure {title, chapters: [{id, title, concepts, n_beats}]}

Phase 2 — Beats (parallel calls per chapter, ~400 tokens each):
    Chapter context → list of beats [{beat_id, narration, visual: {...}}]

MAX_BEATS_PER_CHAPTER = 5 keeps each call's output bounded.
Each chapter call retries up to 3 times on failure.
"""

from __future__ import annotations

import asyncio
import json
import logging

from config.settings import settings
from generator.llm_client import LLMClient, get_llm_client
from generator.prompts import (
    CHAPTER_JSON_FORMAT,
    CHAPTER_SYSTEM_PROMPT,
    OUTLINE_JSON_FORMAT,
    OUTLINE_SYSTEM_PROMPT,
)
from generator.validator import validate_beats, validate_outline

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

    # At ~15 s/beat: 5 min → 20 beats, 3 min → 12 beats, 10 min → 40 beats.
    # n_beats per chapter is overridden in _generate_chapter_beats regardless,
    # but telling the LLM the target chapter count keeps the outline coherent.
    target_beats  = max(12, round(duration_mins * 60 / 15))
    min_chapters  = min(6, max(3, round(target_beats / settings.max_beats_per_chapter)))

    prompt = (
        f"Create a chapter outline for a {duration_mins}-minute video about: {topic}"
        f"{lang_note}"
        f"\n\nPacing target: ~{target_beats} beats total ({duration_mins} min ÷ 15 s/beat). "
        f"You MUST produce exactly {min_chapters} chapters."
        f"\n\n{OUTLINE_JSON_FORMAT}"
    )

    log.info("Phase 1 — outline for: %.60s (%d min)", topic, duration_mins)

    last_exc: Exception | None = None
    for attempt in range(_MAX_OUTLINE_RETRIES):
        try:
            raw = await client.complete(
                system=OUTLINE_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=settings.outline_output_tokens,
                temperature=0.6,
                label="outline",
            )
            raw = _strip_fences(raw)
            log.debug("Outline response (%d chars): %.400s", len(raw), raw)

            outline = json.loads(raw)

            errors = validate_outline(outline)
            if errors:
                raise ValueError("Outline validation failed:\n" + "\n".join(errors))

            # Enforce minimum chapter count — LLMs often generate fewer chapters
            # than instructed, leaving total beats too low for the target duration.
            got_chapters = len(outline.get("chapters", []))
            if got_chapters < min_chapters:
                raise ValueError(
                    f"Outline has {got_chapters} chapters but need at least "
                    f"{min_chapters} for a {duration_mins}-min video"
                )

            log.info(
                "Outline: '%s', %d chapters (attempt %d)",
                outline.get("title"), got_chapters, attempt + 1,
            )
            return outline

        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Outline attempt %d/%d failed: %s", attempt + 1, _MAX_OUTLINE_RETRIES, exc)

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
    # Always use max_beats_per_chapter — the LLM's n_beats suggestion is
    # unreliable (consistently too low). Duration targets require every
    # chapter to contribute its full quota.
    n_beats  = settings.max_beats_per_chapter
    concepts = ", ".join(chapter.get("concepts", []))

    chapters = outline.get("chapters", [])
    idx = next((i for i, c in enumerate(chapters) if c.get("id") == cid), -1)
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

    prompt = (
        f"Generate exactly {n_beats} beats for the '{ctitle}' chapter "
        f"of a {outline.get('total_duration_mins', 5)}-minute video about '{outline.get('title', '')}'.\n"
        f"Chapter role: {role.upper()} — follow the '{role}' beat arc from the system prompt.\n"
        f"This chapter covers: {concepts}.\n\n"
        f"{prev_note}{next_note}{lang_note}\n\n"
        f"Use beat_ids: '{cid}_1', '{cid}_2', ...\n\n"
        f"{CHAPTER_JSON_FORMAT}"
    )

    for attempt_num in range(_MAX_CHAPTER_RETRIES):
        try:
            log.info(
                "Phase 2 — chapter '%s' (%d beats, attempt %d)",
                cid, n_beats, attempt_num + 1,
            )
            raw = await client.complete(
                system=CHAPTER_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=settings.max_chapter_output_tokens,
                temperature=0.7,
                label=f"chapter:{cid}",
            )
            raw = _strip_fences(raw)

            parsed = json.loads(raw)
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
    "en": "Let us now move to the next part: {title}. Take a moment to reflect on what we just covered before we continue.",
    "hi": "अब हम अगले भाग पर जाते हैं: {title}। आगे बढ़ने से पहले एक पल रुकें और सोचें।",
}

_CLOSING_NARRATION = {
    "en": (
        "And that is our complete journey through {video_title}. "
        "We started by understanding why this matters, then built the formal "
        "definition, walked through the mechanics step by step, worked a "
        "concrete example with real numbers, and finally uncovered the deeper "
        "geometric intuition behind it all. Keep exploring — the best is yet to come."
    ),
    "hi": (
        "और इस तरह हमारी {video_title} की पूरी यात्रा समाप्त होती है। "
        "हमने समझा कि यह क्यों मायने रखता है, फिर औपचारिक परिभाषा बनाई, "
        "चरण दर चरण यांत्रिकी को समझा, वास्तविक संख्याओं के साथ एक उदाहरण हल किया, "
        "और अंत में इसके पीछे की गहरी ज्यामितीय अंतर्दृष्टि को उजागर किया। "
        "खोजते रहें — सबसे अच्छा अभी आना बाकी है।"
    ),
}


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

    # ── Closing summary beat ──────────────────────────────────────────────────
    # Always end with a deliberate wind-down so the video never feels abrupt.
    chapter_titles = [ch.get("title", "") for ch in chapters]
    closing_template = _CLOSING_NARRATION.get(language, _CLOSING_NARRATION["en"])
    beats.append({
        "beat_id": "closing_summary",
        "narration": closing_template.format(video_title=outline["title"]),
        "visual": {
            "type": "summary_card",
            "key_points": chapter_titles,
        },
    })

    log.info(
        "Plan complete: '%s', %d chapters, %d beats total (incl. %d separators + closing)",
        outline["title"], n_chapters, len(beats), n_chapters - 1,
    )
    return {"title": outline["title"], "beats": beats}
