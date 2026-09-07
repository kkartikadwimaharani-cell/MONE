"""
MiiAiVideo MCP Server
======================

Wraps makima.cloud's AI Video generation API (Seedance 2.0/2.5, Wan 3.0,
Nano Banana Pro, GPT Image 2, Seedream, Flux, Veo, Imagen, Qwen, Seed Audio
— whatever /api/aivideo/capabilities currently reports) as MCP tools, so
Claude can kick off and check on generations directly.

This server does NOT reimplement any generation logic — every tool is a
thin authenticated HTTP call to the existing Flask backend. All the actual
work (Segmind/BudgetPixel calls, secrets, task tracking) still happens
server-side on makima.cloud, exactly like it does for the browser UI.

Deploy this as its OWN Railway service (separate from the `web` service —
see README.md), pointed at this folder. It talks to makima.cloud over
plain HTTPS + a Bearer API key, so it has no shared state or shared
process with the main app at all.

Auth: set MII_MCP_API_KEY here to the SAME value you set for the
"MCP Server API Key" secret at https://makima.cloud/ai-video/app-secrets.
That's the only credential this server needs — it never sees or needs the
human /ai-video login password.
"""

import base64
import os
import hmac
import time
from pathlib import Path
from urllib.parse import quote
from starlette.responses import JSONResponse

import requests
from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

MII_BASE_URL = os.environ.get("MII_BASE_URL", "https://makima.cloud").rstrip("/")
MII_MCP_API_KEY = os.environ.get("MII_MCP_API_KEY", "")

if not MII_MCP_API_KEY:
    # Fail loudly at startup rather than letting every tool call fail with
    # a confusing 401 one at a time — this key is the only thing this
    # server needs and there's no sane default for it.
    raise RuntimeError(
        "MII_MCP_API_KEY belum diset. Set env var ini ke NILAI YANG SAMA "
        "dengan 'MCP Server API Key' di https://makima.cloud/ai-video/app-secrets "
        "(generate string acak baru kalau belum ada)."
    )

_ICON_PATH = Path(__file__).parent / "icon.jpg"
_icons = []
if _ICON_PATH.exists():
    _icon_data_uri = "data:image/jpeg;base64," + base64.standard_b64encode(_ICON_PATH.read_bytes()).decode()
    _icons = [Icon(src=_icon_data_uri, mimeType="image/jpeg", sizes=["1536x1536"])]

mcp = FastMCP(
    "MiiAiVideo",
    host="0.0.0.0",
    instructions=(
        "Tools for generating AI video/image via MII's makima.cloud AI Video "
        "tool. Call list_models first to see which family/variant combos are "
        "currently configured and what resolutions/durations/aspect ratios "
        "each supports, then generate_video or generate_image to start a "
        "job, then wait_for_result (or repeated check_status calls) to get "
        "the finished output URL. Generation is asynchronous — it can take "
        "anywhere from ~20 seconds (image) to several minutes (long video)."
    ),
    website_url="https://makima.cloud/ai-video",
    icons=_icons,
)


def _headers():
    return {"Authorization": f"Bearer {MII_MCP_API_KEY}"}


def _get(path):
    try:
        r = requests.get(MII_BASE_URL + path, headers=_headers(), timeout=30)
    except requests.RequestException as e:
        return {"error": f"Gagal menghubungi {MII_BASE_URL}: {e}"}
    return _as_json(r)


def _post(path, body):
    try:
        r = requests.post(MII_BASE_URL + path, headers=_headers(), json=body, timeout=30)
    except requests.RequestException as e:
        return {"error": f"Gagal menghubungi {MII_BASE_URL}: {e}"}
    return _as_json(r)


def _as_json(r):
    try:
        data = r.json()
    except ValueError:
        return {"error": f"Server mengembalikan respons non-JSON (HTTP {r.status_code})"}
    if r.status_code == 401:
        return {"error": "MII_MCP_API_KEY salah atau belum di-set di makima.cloud (/ai-video/app-secrets)."}
    if not isinstance(data, dict):
        return {"error": f"Server mengembalikan format JSON tidak valid (HTTP {r.status_code})"}
    if "id" in data and "task_id" not in data:
        data["task_id"] = data["id"]
    if r.status_code >= 400 and "error" not in data:
        data["error"] = f"HTTP {r.status_code}"
    return data


@mcp.tool()
def list_models() -> dict:
    """List every AI Video/Image model family+variant MiiAiVideo currently
    has configured, with each one's supported resolutions, durations, and
    aspect ratios. Always call this before generate_video or
    generate_image if you're unsure which family/variant values are valid
    — passing an unconfigured combo fails with a clear error, but calling
    this first avoids the extra round trip."""
    return _get("/api/aivideo/capabilities")


@mcp.tool()
def generate_video(
    prompt: str,
    family: str = "seedance25",
    variant: str = "STANDARD",
    resolution: str = "",
    duration: int = 0,
    aspect_ratio: str = "",
    mute_audio: bool = False,
) -> dict:
    """Start a text-to-video generation job. Returns immediately with a
    task_id — pass that to wait_for_result (or check_status) to get the
    finished video URL. Text-to-video only for now: no reference
    image/video/audio inputs or first/last-frame control yet.

    family/variant must be a valid "family:VARIANT" pair from
    list_models()'s video section (e.g. family="seedance25",
    variant="STANDARD", or family="seedance", variant="MINI"/"FAST"/"PRO").
    Leave resolution/duration/aspect_ratio empty to use that model's
    default."""
    body = {"prompt": prompt, "family": family, "model": variant, "mute_audio": mute_audio}
    if resolution:
        body["resolution"] = resolution
    if duration:
        body["duration"] = duration
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    return _post("/api/aivideo/generate", body)


@mcp.tool()
def generate_image(
    prompt: str,
    family: str = "nanobanana",
    variant: str = "STANDARD",
    aspect_ratio: str = "",
    negative_prompt: str = "",
) -> dict:
    """Start a text-to-image generation job. Returns a task_id — pass that
    to wait_for_result (or check_status) to get the finished image URL.

    family/variant must be a valid pair from list_models() (e.g.
    family="nanobanana" for Nano Banana Pro, "gptimage" for GPT Image 2,
    "seedream", "flux", "imagen", or "qwen" — variant options differ per
    family, check the model's own docs/UI if unsure)."""
    body = {"prompt": prompt, "family": family, "model": variant}
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    return _post("/api/aivideo/generate", body)


@mcp.tool()
def check_status(task_id: str) -> dict:
    """Check one generation task's current status. Returns status
    (pending/processing/completed/failed) and progress (0-100); once
    status is "completed", the response includes the finished output URL."""
    return _get(f"/api/aivideo/status/{quote(task_id, safe='')}")


@mcp.tool()
def wait_for_result(task_id: str, timeout_seconds: int = 180) -> dict:
    """Block and poll check_status every 5 seconds until the task finishes
    (completed/failed) or timeout_seconds elapses, then return the final
    status payload — saves you from manually calling check_status in a
    loop. timeout_seconds is capped at 280 (just under most MCP clients'
    default request timeout); for longer videos, fall back to a few
    separate check_status calls a minute or two apart instead."""
    timeout_seconds = max(5, min(int(timeout_seconds), 280))
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        last = _get(f"/api/aivideo/status/{quote(task_id, safe='')}")
        if last.get("error") or last.get("status") in ("completed", "failed"):
            return last
        time.sleep(5)
    last["timed_out"] = True
    return last


class BearerAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            expected = ("Bearer " + MII_MCP_API_KEY).encode("utf-8")
            if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
                response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = port
    import uvicorn

    uvicorn.run(BearerAuthMiddleware(mcp.streamable_http_app()), host="0.0.0.0", port=port)
