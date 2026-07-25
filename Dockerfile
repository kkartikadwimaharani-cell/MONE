FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd -m -u 1000 appuser
COPY --chown=appuser:appuser . .
# WORKDIR is created while still root, before the COPY --chown above runs —
# that only sets ownership of the copied *contents*, not the /app directory
# itself. Without this, appuser can't create new files there (SQLite DB
# files and static/aivideo_uploads/ are both created at runtime, not present
# at build time), so the container would work at build/test time but fail
# the first time it tries to write anything.
RUN chown appuser:appuser /app
USER appuser

CMD ["python", "start.py"]
