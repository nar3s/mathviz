# ── Base image ────────────────────────────────────────────────────────────────
# manimcommunity/manim:stable ships Python, ManimCE, LaTeX (texlive-full),
# Cairo, Pango, FFmpeg, and dvisvgm — everything we need pre-installed.
FROM manimcommunity/manim:stable

# Switch to root so we can pip-install into the system site-packages.
USER root

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# ffmpeg is not guaranteed to be in PATH on all manim base image tags.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY . .

# ── Output directory ──────────────────────────────────────────────────────────
# On Railway: mount a persistent volume at /data and set OUTPUT_DIR=/data.
# Locally / without a volume: /data is ephemeral but still works for testing.
RUN mkdir -p /data

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Use explicit venv path — avoids any PATH/activation issues in the container.
# Railway injects $PORT; falls back to 8000 for local `docker run`.
CMD ["/app/start.sh"]
