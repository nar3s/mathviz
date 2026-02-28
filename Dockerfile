# ── Base image ────────────────────────────────────────────────────────────────
# manimcommunity/manim:stable ships Python, ManimCE, LaTeX (texlive-full),
# Cairo, Pango, FFmpeg, and dvisvgm — everything we need pre-installed.
FROM manimcommunity/manim:stable

# Switch to root so we can pip-install into the system site-packages.
USER root

WORKDIR /app

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

# Railway injects $PORT; fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
