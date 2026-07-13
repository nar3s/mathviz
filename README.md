# MathViz Engine

MathViz Engine is a FastAPI service that turns a plain-language mathematics topic into a narrated, animated MP4. It uses an LLM to plan the lesson, Sarvam AI for speech, Manim for visuals, and FFmpeg to assemble the final video.

## What it does

- Builds a chapter outline and beat-level scene plan with Claude, OpenAI, or Gemini.
- Validates the generated scene schema and LaTeX before rendering.
- Generates English or Hindi narration with Sarvam AI.
- Renders independent Manim scenes in parallel and combines them with FFmpeg.
- Supports title, equation, graph, vector, matrix, theorem, summary, and text scenes.
- Stores output locally, with optional upload to Cloudflare R2.
- Exposes asynchronous job submission and status polling through a REST API.

## Pipeline

```text
Topic
  -> LLM outline and beat plan
  -> plan validation
  -> concurrent text-to-speech
  -> Manim scene generation and rendering
  -> audio/video merge
  -> final MP4
  -> optional R2 upload
```

## Quick start with Docker

Docker is the simplest setup because the base image includes Manim, LaTeX, Cairo, Pango, and FFmpeg.

1. Copy the environment template and add your API keys:

   ```bash
   cp .env.example .env
   ```

   On PowerShell, use `Copy-Item .env.example .env`.

2. At minimum, configure these values in `.env`:

   ```dotenv
   LLM_PROVIDER=claude
   LLM_MODEL=claude-opus-4-6
   LLM_API_KEY=your_llm_api_key
   SARVAM_API_KEY=your_sarvam_api_key
   ```

3. Build and run the service:

   ```bash
   docker build -t mathviz .
   docker run --rm -p 8000:8000 --env-file .env -e OUTPUT_DIR=/data -v mathviz-output:/data mathviz
   ```

4. Open the interactive API documentation at <http://localhost:8000/docs>, or check the service at <http://localhost:8000/health>.

## Local installation

Local development requires Python 3.10 or newer, FFmpeg, and the [Manim system dependencies](https://docs.manim.community/en/stable/installation.html). A LaTeX installation is required for equation scenes.

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the Python packages and create the local configuration:

```bash
pip install -r requirements.txt
cp .env.example .env
```

If `LLM_PROVIDER=openai`, also install the optional OpenAI client with `pip install openai` (or uncomment it in `requirements.txt`). Then start the API:

```bash
python main.py
```

The server listens on <http://localhost:8000> by default.

## API usage

Submit a generation job:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Explain eigenvalues and eigenvectors geometrically",
    "language": "en",
    "duration_mins": 5,
    "quality": "medium",
    "voice": "shubh"
  }'
```

The API responds immediately with a job ID:

```json
{
  "job_id": "4f71bd29c0",
  "status": "queued",
  "message": "Job queued. Poll /status/4f71bd29c0 for progress."
}
```

Poll until `status` is `completed` or `failed`:

```bash
curl http://localhost:8000/status/4f71bd29c0
```

When complete, download the path returned in `video_url`, for example:

```bash
curl -O http://localhost:8000/output/4f71bd29c0.mp4
```

On PowerShell, use `curl.exe` for these examples because `curl` may be an alias for `Invoke-WebRequest`.

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/generate` | Queue a video generation job |
| `GET` | `/status/{job_id}` | Read progress, errors, and the final video URL |
| `GET` | `/output/{filename}` | Download a locally stored MP4 |
| `GET` | `/jobs` | List jobs known to the current process |
| `GET` | `/health` | Check service health and the configured LLM |

### Generate options

| Field | Default | Values |
| --- | --- | --- |
| `topic` | required | Plain-text topic, at least 3 characters |
| `language` | `en` | `en` or `hi` |
| `duration_mins` | `5` | Target duration in minutes |
| `quality` | `medium` | `low` (480p15), `medium` (720p30), or `high` (1080p60) |
| `voice` | `shubh` | Sarvam AI voice ID |

## Configuration

Settings are read from environment variables and from a project-root `.env` file. See [`.env.example`](.env.example) for a complete template.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | Yes | `claude` | `claude`, `openai`, or `gemini` |
| `LLM_MODEL` | Yes | `claude-opus-4-6` | Model ID understood by the selected provider |
| `LLM_API_KEY` | Yes | none | API key for the selected LLM provider |
| `SARVAM_API_KEY` | Yes | none | Sarvam AI text-to-speech key |
| `SARVAM_MODEL` | No | `bulbul:v3` | Sarvam TTS model |
| `OUTPUT_DIR` | No | `./output` | Root for generated audio, scenes, caches, and videos |
| `MAX_RENDER_WORKERS` | No | `1` | Maximum concurrent Manim subprocesses per job |
| `DEFAULT_ACCENT_COLOR` | No | `#58C4DD` | Default Manim scene accent color |
| `R2_ACCOUNT_ID` | No | none | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | No | none | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | No | none | R2 API token secret |
| `R2_BUCKET_NAME` | No | none | Destination bucket |
| `R2_PUBLIC_URL` | No | none | Public base URL for uploaded videos |

R2 is enabled only when all five R2 variables are present. Otherwise, completed videos are served from the local output directory.

## Render a saved plan

To iterate on rendering without making new LLM calls, pass an existing plan JSON to the helper script:

```bash
python scripts/render_from_plan.py tests/saved_responses/eigenvalues_full_plan_claude.json --quality low
```

Use `--beats 3` to render only the first three beats, or `--job-id my_test` to choose the output name. This workflow still requires `SARVAM_API_KEY` because it regenerates narration.

## Output layout

By default, generated files are written below `output/`:

```text
output/
├── audio/       # per-beat narration
├── cache/       # reusable generated assets
├── raw/         # scene files, Manim media, and merged beats
└── final/       # completed MP4 files
```

## Tests

Install the test tools if they are not already available, then run the suite:

```bash
pip install pytest pytest-asyncio
pytest -q
```

Tests marked `slow` may require working Manim and FFmpeg installations:

```bash
pytest -q -m "not slow"
```

## Project structure

```text
main.py          FastAPI application and generation pipeline
config/          environment-backed settings
generator/       LLM clients, prompts, planning, and validation
narration/       Sarvam client and audio cache
tts/             concurrent narration generation
scenes/          reusable Manim scene implementations
renderer/        scene-file generation and Manim execution
composer/        FFmpeg merge and concatenation
storage/         optional Cloudflare R2 uploads
scripts/         command-line utilities
tests/           unit tests, fixtures, and saved plans
```

## Deployment notes

- The included Dockerfile is configured for Railway; `railway.toml` uses `/health` for health checks.
- Mount persistent storage and set `OUTPUT_DIR` to its path (for example, `/data`) if local videos must survive container restarts.
- Job metadata is stored in memory and is lost when the process restarts. Completed local videos can still be recovered through `/status/{job_id}` when the MP4 remains on persistent storage.
- Run a single API worker unless the in-memory job store is replaced with shared storage.
