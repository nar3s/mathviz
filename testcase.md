# MathViz Test Plan — All Failure Cases

> **Goal:** Identify and test every possible failure mode in the MathViz pipeline  
> **Method:** No LLM calls — use hardcoded/mock beat JSONs to isolate each layer  
> **Priority:** P0 = video breaks, P1 = sync drifts, P2 = visual glitch, P3 = cosmetic

---

## Pipeline Overview

```
Topic → [LLM: Outline] → [LLM: Beats] → [Validation] → [TTS] → [Manim Render] → [Stitch] → Video
```

Each section below maps to a pipeline stage.

---

## 1. LLM Output — Outline Phase

### 1.1 Malformed JSON (P0)

| #     | Case                             | Mock Input                              | Expected Behavior                |
| ----- | -------------------------------- | --------------------------------------- | -------------------------------- |
| 1.1.1 | Truncated JSON (token limit hit) | `{"title": "Fourier`                    | Retry or clear error, no crash   |
| 1.1.2 | Markdown-wrapped JSON            | ` ```json\n{...}\n``` `                 | Strip fences, parse successfully |
| 1.1.3 | Trailing comma in array          | `"chapters": [{...},]`                  | Handle or sanitize               |
| 1.1.4 | Explanation text before JSON     | `Here's the outline:\n{...}`            | Strip preamble, parse JSON       |
| 1.1.5 | Empty response                   | `""`                                    | Clear error message              |
| 1.1.6 | Valid JSON but wrong shape       | `{"slides": [...]}` (no `chapters` key) | Validation error, not crash      |

### 1.2 Schema Violations (P0)

| #     | Case                           | Mock Input                            | Expected              |
| ----- | ------------------------------ | ------------------------------------- | --------------------- |
| 1.2.1 | Missing `chapters` array       | `{"title": "..."}`                    | Validation error      |
| 1.2.2 | `n_beats` is string not number | `"n_beats": "3"`                      | Coerce or error       |
| 1.2.3 | `n_beats: 0` for a chapter     | `"n_beats": 0`                        | Skip chapter or error |
| 1.2.4 | Chapter missing `id`           | `{"title": "...", "concepts": [...]}` | Error with context    |
| 1.2.5 | Duplicate chapter IDs          | Two chapters with `id: "intro"`       | Detect and error      |
| 1.2.6 | `n_beats` negative             | `"n_beats": -2`                       | Validation error      |
| 1.2.7 | Extremely large `n_beats`      | `"n_beats": 100`                      | Cap or warn           |

---

## 2. LLM Output — Beats Phase

### 2.1 Structural Failures (P0)

| #     | Case                            | Mock Input                              | Expected                    |
| ----- | ------------------------------- | --------------------------------------- | --------------------------- |
| 2.1.1 | Returns object instead of array | `{"beats": [...]}`                      | Unwrap or error             |
| 2.1.2 | Truncated mid-beat              | `[{"beat_id": "intro_1", "narr`         | Retry or error              |
| 2.1.3 | Beat count mismatch             | Outline says 4 beats, LLM returns 6     | Warn, use what's returned   |
| 2.1.4 | Empty beats array               | `[]`                                    | Error: no beats for chapter |
| 2.1.5 | Beats not in array              | Single beat object, not wrapped in `[]` | Wrap and proceed or error   |

### 2.2 Unknown/Invalid Visual Types (P0)

| #     | Case                           | Mock Visual                            | Expected                  |
| ----- | ------------------------------ | -------------------------------------- | ------------------------- |
| 2.2.1 | Completely invented type       | `"type": "animation"`                  | Fallback to text_card     |
| 2.2.2 | Close misspelling              | `"type": "equation_reval"`             | No fuzzy match — fallback |
| 2.2.3 | Type is null                   | `"type": null`                         | Fallback                  |
| 2.2.4 | Type is empty string           | `"type": ""`                           | Fallback                  |
| 2.2.5 | Missing `type` field entirely  | `"visual": {"latex": "x^2"}`           | Fallback                  |
| 2.2.6 | Extra unknown type from Gemini | `"type": "diagram"`, `"type": "chart"` | Fallback                  |

### 2.3 Missing Required Fields per Visual Type (P0)

| #      | Visual Type          | Missing Field                       | Mock                                                  | Expected                      |
| ------ | -------------------- | ----------------------------------- | ----------------------------------------------------- | ----------------------------- |
| 2.3.1  | `equation_reveal`    | `latex`                             | `{"type": "equation_reveal"}`                         | Fallback or error             |
| 2.3.2  | `equation_transform` | `from_latex`                        | `{"type": "equation_transform", "to_latex": "..."}`   | Fallback                      |
| 2.3.3  | `equation_transform` | `to_latex`                          | `{"type": "equation_transform", "from_latex": "..."}` | Fallback                      |
| 2.3.4  | `graph_plot`         | `functions`                         | `{"type": "graph_plot", "x_range": [...]}`            | Fallback                      |
| 2.3.5  | `graph_plot`         | `x_range`                           | `{"type": "graph_plot", "functions": [...]}`          | Use default range or fallback |
| 2.3.6  | `highlight`          | `target`                            | `{"type": "highlight", "color": "yellow"}`            | Fallback                      |
| 2.3.7  | `highlight`          | `color`                             | `{"type": "highlight", "target": "x^2"}`              | Use default color or fallback |
| 2.3.8  | `vector_show`        | `vectors`                           | `{"type": "vector_show"}`                             | Fallback                      |
| 2.3.9  | `vector_transform`   | `matrix`                            | `{"type": "vector_transform", "vectors": [...]}`      | Fallback                      |
| 2.3.10 | `graph_animate`      | `function_expr`                     | `{"type": "graph_animate", "parameter": "a"}`         | Fallback                      |
| 2.3.11 | `matrix_display`     | `matrix_values`                     | `{"type": "matrix_display"}`                          | Fallback                      |
| 2.3.12 | `summary_card`       | `key_points`                        | `{"type": "summary_card"}`                            | Fallback                      |
| 2.3.13 | `theorem_card`       | `theorem_name` or `statement_latex` | Partial fields                                        | Fallback                      |
| 2.3.14 | `step_reveal`        | `latex` or `step_number`            | Partial fields                                        | Fallback                      |

### 2.4 Wrong Field Names (Gemini's Creative Renaming) (P0)

| #     | Expected                  | Gemini Might Return                    | Mock                                            | Expected                       |
| ----- | ------------------------- | -------------------------------------- | ----------------------------------------------- | ------------------------------ |
| 2.4.1 | `latex`                   | `formula`, `equation`, `math`          | `{"type": "equation_reveal", "formula": "x^2"}` | Not found → fallback           |
| 2.4.2 | `from_latex` / `to_latex` | `from` / `to`, `start` / `end`         | Wrong keys                                      | Fallback                       |
| 2.4.3 | `functions`               | `plots`, `curves`, `lines`             | Wrong key on graph_plot                         | Fallback                       |
| 2.4.4 | `expr` (in function obj)  | `expression`, `formula`, `fn`          | Nested wrong key                                | Fallback                       |
| 2.4.5 | `x_range`                 | `x_axis`, `domain`, `xlim`             | Wrong key                                       | Use default or fallback        |
| 2.4.6 | `coords` (in vector)      | `coordinates`, `xy`, `point`           | Wrong key                                       | Fallback                       |
| 2.4.7 | `key_points`              | `points`, `bullets`, `items`           | Wrong key on summary                            | Fallback                       |
| 2.4.8 | `matrix_values`           | `matrix`, `values`, `data`             | Wrong key                                       | Fallback                       |
| 2.4.9 | `narration`               | `text`, `speech`, `dialogue`, `script` | Beat-level wrong key                            | No audio for beat → sync break |

### 2.5 Wrong Field Types (P1)

| #     | Field         | Expected         | Got               | Mock                       | Expected          |
| ----- | ------------- | ---------------- | ----------------- | -------------------------- | ----------------- |
| 2.5.1 | `x_range`     | `[min, max]`     | `"-5 to 5"`       | String instead of array    | Parse or fallback |
| 2.5.2 | `functions`   | Array of objects | Single object     | Not wrapped                | Wrap or fallback  |
| 2.5.3 | `vectors`     | Array of objects | Array of arrays   | `[[1,2],[3,4]]`            | Adapt or fallback |
| 2.5.4 | `matrix`      | 2D array         | Flat array        | `[1,2,3,4]`                | Reshape or error  |
| 2.5.5 | `step_number` | Number           | String `"1"`      | Coerce                     |
| 2.5.6 | `key_points`  | Array of strings | Single string     | Wrap in array              |
| 2.5.7 | `color`       | String           | Array or hex code | `[255,0,0]` or `"#FF0000"` | Normalize         |

---

## 3. LaTeX Failures (P0/P1)

| #    | Case                       | Mock                                        | Expected                         |
| ---- | -------------------------- | ------------------------------------------- | -------------------------------- |
| 3.1  | Invalid LaTeX syntax       | `"\\frac{}{}"` (empty frac)                 | Manim error — catch and fallback |
| 3.2  | Single-escaped backslashes | `"\frac{a}{b}"` instead of `"\\frac{a}{b}"` | Fix escaping or error            |
| 3.3  | Triple/quad escaped        | `"\\\\\\\\frac{a}{b}"`                      | Over-escaped — normalize         |
| 3.4  | Unmatched braces           | `"\\frac{a{b}"`                             | Manim crash — catch              |
| 3.5  | Unicode instead of LaTeX   | `"λ"` instead of `"\\lambda"`               | May or may not render            |
| 3.6  | Very long equation         | 500+ char LaTeX string                      | Overflow slide bounds            |
| 3.7  | LaTeX in narration field   | `"The formula \\frac{a}{b} shows..."`       | TTS reads raw LaTeX aloud        |
| 3.8  | Empty latex string         | `"latex": ""`                               | Blank visual — catch             |
| 3.9  | Unsupported LaTeX packages | `\\usepackage{tikz}` in string              | Manim can't handle — error       |
| 3.10 | Mixed text and math mode   | `"For all $x > 0$"`                         | May break MathTex                |

---

## 4. TTS (Sarvam AI) Failures (P0)

| #    | Case                          | Mock Narration                     | Expected                          |
| ---- | ----------------------------- | ---------------------------------- | --------------------------------- |
| 4.1  | Empty narration string        | `"narration": ""`                  | Skip beat or use silence          |
| 4.2  | Narration is null             | `"narration": null`                | Handle gracefully                 |
| 4.3  | Narration missing entirely    | Beat has no `narration` key        | Use silence, don't break sync     |
| 4.4  | Very long narration (>30 sec) | 5+ sentences in one beat           | Audio way longer than visual      |
| 4.5  | Very short narration          | `"narration": "Yes."`              | 0.5s audio, visual plays too fast |
| 4.6  | Raw LaTeX in narration        | `"The \\frac{a}{b} is..."`         | TTS says "backslash frac"         |
| 4.7  | Special characters            | Narration with `$`, `{`, `}`, `\\` | TTS garbles or errors             |
| 4.8  | Non-English text              | Hindi/mixed language narration     | Sarvam handles but verify         |
| 4.9  | TTS API timeout/failure       | —                                  | Retry or skip with silence        |
| 4.10 | TTS returns 0-byte audio      | API returns empty audio file       | Detect and handle                 |

---

## 5. Manim Rendering Failures (P0)

| #    | Case                                 | Mock Beat                                       | Expected                        |
| ---- | ------------------------------------ | ----------------------------------------------- | ------------------------------- |
| 5.1  | Unknown visual type reaches renderer | `"type": "hologram"`                            | Fallback card, not crash        |
| 5.2  | graph_plot with invalid expr         | `"expr": "x***2"` (syntax error)                | Catch eval error, show fallback |
| 5.3  | graph_plot with dangerous expr       | `"expr": "__import__('os').system('rm -rf /')"` | Sandboxed — reject              |
| 5.4  | Division by zero in expr             | `"expr": "1/x"` at x=0                          | Handle discontinuity            |
| 5.5  | graph_plot range is inverted         | `"x_range": [10, -10]`                          | Swap or error                   |
| 5.6  | graph_plot range is zero             | `"x_range": [5, 5]`                             | Error — no range to plot        |
| 5.7  | Vector with [0,0] coords             | Zero vector                                     | Renders but invisible — warn    |
| 5.8  | Matrix with 0 determinant            | Singular matrix in transform                    | Valid but may collapse vectors  |
| 5.9  | Extremely large numbers              | Coords `[10000, 50000]`                         | Off-screen or scale issues      |
| 5.10 | Negative dimensions in matrix        | `[[-1, 0], [0, -1]]`                            | Valid — reflection, but verify  |
| 5.11 | Non-square matrix in transform       | `[[1,2,3],[4,5,6]]`                             | Error if code assumes 2×2       |
| 5.12 | Animation duration is 0              | Beat with 0s audio                              | Manim can't animate in 0s       |
| 5.13 | Too many objects on screen           | 20+ vectors, 10+ functions                      | Performance / visual clutter    |

---

## 6. Audio-Visual Sync Failures (P0)

| #   | Case                           | Scenario                           | Expected                                        |
| --- | ------------------------------ | ---------------------------------- | ----------------------------------------------- |
| 6.1 | Audio longer than animation    | 15s narration, 3s animation        | Visual ends, audio keeps playing over next beat |
| 6.2 | Animation longer than audio    | 3s narration, 15s animation        | Silence gap, then next beat's audio starts late |
| 6.3 | Silent beat (no audio)         | TTS failed for one beat            | Visual plays in silence, next beats shift       |
| 6.4 | Missing visual (render failed) | One beat's Manim errors out        | Audio plays over blank, everything shifts by 1  |
| 6.5 | Cumulative drift               | Each beat off by 0.5s              | By beat 15, audio is 7.5s ahead/behind          |
| 6.6 | Variable TTS speed             | Some narrations spoken faster      | Planned timing ≠ actual timing                  |
| 6.7 | Beat ordering wrong            | Beats returned out of order by LLM | beat_3 plays before beat_2                      |

---

## 7. Stitching / Final Video (P1)

| #   | Case                         | Scenario                              | Expected                                |
| --- | ---------------------------- | ------------------------------------- | --------------------------------------- |
| 7.1 | One chapter fails completely | All beats in chapter 3 error          | Skip chapter or insert error card       |
| 7.2 | No beats succeed             | Every beat fails                      | Return error, don't produce empty video |
| 7.3 | Audio codec mismatch         | TTS returns mp3, stitcher expects wav | Convert or error                        |
| 7.4 | Resolution mismatch          | Some scenes 1080p, some 720p          | Normalize before stitching              |
| 7.5 | Very long video (>20 min)    | 50+ beats                             | Memory / render time issues             |
| 7.6 | Single beat video            | Only 1 beat total                     | Should still produce valid video        |
| 7.7 | FFmpeg failure               | Stitching command errors              | Clear error, cleanup temp files         |

---

## 8. Edge Case Topics (P2)

These topics stress-test specific visual types and LaTeX complexity:

| #    | Topic                        | Stress Point                                      |
| ---- | ---------------------------- | ------------------------------------------------- |
| 8.1  | Fourier Transform            | Heavy graph_plot + graph_animate, long LaTeX      |
| 8.2  | Linear Algebra (eigenvalues) | vector_transform + matrix_display + complex LaTeX |
| 8.3  | Simple arithmetic (1+1=2)    | Minimal beats — tests small output handling       |
| 8.4  | Topology (abstract)          | No obvious visual type — forces LLM to improvise  |
| 8.5  | Integration by parts         | Deep equation_transform chains                    |
| 8.6  | Probability (Bayes theorem)  | Mix of theorem_card + equation + text             |
| 8.7  | Complex numbers              | 2D plane + vectors + equations combined           |
| 8.8  | Limits and continuity        | graph_animate with parameter approach             |
| 8.9  | Set theory                   | Mostly text/symbols, few visuals                  |
| 8.10 | Differential equations       | Multi-step transforms + graph solutions           |

---

## 9. Model-Specific Behavior (P1)

| #   | Case                        | Opus | Gemini                     | Sonnet     |
| --- | --------------------------- | ---- | -------------------------- | ---------- |
| 9.1 | Follows field names exactly | ✅   | ❌ Renames fields          | ✅ Usually |
| 9.2 | Respects visual type enum   | ✅   | ❌ Invents new types       | ✅         |
| 9.3 | Correct LaTeX escaping      | ✅   | ⚠️ Sometimes under-escapes | ✅         |
| 9.4 | Beat count matches n_beats  | ✅   | ⚠️ Sometimes off by 1-2    | ✅         |
| 9.5 | Narration is TTS-friendly   | ✅   | ⚠️ May include symbols     | ✅         |
| 9.6 | JSON always valid           | ✅   | ⚠️ With response_mime_type | ✅         |

---

## Test Execution Strategy

### Phase 1: Mock JSON Tests (No LLM, No TTS, No Manim)

- Create mock beat JSONs for every case in sections 2.2–2.5
- Run through your validation layer
- **Pass criteria:** Every invalid input either errors cleanly or falls back gracefully

### Phase 2: Renderer Isolation Tests (No LLM, No TTS)

- Feed valid mock beats with edge-case visuals (sections 3, 5) into Manim
- **Pass criteria:** Every beat produces a video segment or a fallback card, never crashes

### Phase 3: Sync Tests (No LLM)

- Use mock beats with pre-recorded TTS audio of varying lengths
- **Pass criteria:** Audio and visual align for every beat, no cumulative drift

### Phase 4: Integration Tests (With LLM)

- Run each topic from section 8 through the full pipeline with each model
- **Pass criteria:** Watchable video with no blank slides or desync

### Phase 5: Chaos Tests

- Randomly corrupt 1-3 beats per job (bad type, missing field, bad LaTeX)
- **Pass criteria:** Pipeline recovers — produces video with fallback cards, never crashes

---

## Fixtures Needed

````
tests/
  fixtures/
    outline/
      valid_simple.json          # 3 chapters, basic topic
      valid_complex.json         # 6 chapters, Fourier-level
      truncated.json             # Cut off mid-string
      markdown_wrapped.json      # ```json ... ```
      wrong_schema.json          # Missing chapters key
      empty.json                 # Empty string
    beats/
      valid_all_types.json       # One beat per visual type
      unknown_types.json         # Invented visual types
      missing_fields.json        # Required fields missing
      renamed_fields.json        # Gemini-style field renaming
      wrong_field_types.json     # String instead of array, etc.
      bad_latex.json             # Various LaTeX failures
      empty_narration.json       # Missing/empty narration
      long_narration.json        # 5+ sentence narration
      single_beat.json           # Just one beat
      many_beats.json            # 20+ beats
````
