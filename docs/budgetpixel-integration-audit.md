# BudgetPixel integration audit

This document records the mandatory pre-implementation audit performed on
2026-09-02. It deliberately does **not** define an API contract: no official
BudgetPixel or Derabox API documentation is present in this repository, and
the documentation hosts could not be reached from the implementation
environment. Inventing endpoints, authentication headers, payload fields,
model IDs, upload responses, or public URL formats would be unsafe.

## Current architecture

- `app.py` contains the existing Flask routes, provider dispatch, upload
  handling, authentication/CSRF checks, and the in-process `AIVIDEO_TASKS`
  task registry.
- `templates/ai-video.html` owns the existing model registry and capability
  UI, uploads, generation queue, polling, retry, task restore, result preview,
  History, and Archive interactions.
- `aivideo_archive.py` persists task snapshots and History/Archive metadata in
  SQLite. The browser uses local storage as a fast History cache and syncs it
  to this server-side store.
- `secrets_store.py` provides encrypted-at-rest application secrets with an
  environment-variable fallback.
- Dropbox is the current reference upload transport and the permanent result
  store. It is also used by Motion Control, reference cleanup, archive
  promotion/deletion, storage reporting, and debug tooling.

## Existing generation flow

1. The browser builds a model-specific payload and posts it to
   `POST /api/aivideo/generate`.
2. The route validates and maps that payload to a Segmind endpoint.
3. Mii creates its own task ID in `AIVIDEO_TASKS` and persists a snapshot.
4. `_run_segmind_task` performs provider work in a background thread and
   updates the existing task.
5. The browser polls `GET /api/aivideo/task/<task_id>` (with the existing
   status/result aliases).
6. A completed result uses the existing preview, queue, History, and Archive
   paths. Result media is promoted to Dropbox for durable storage.

## Minimal implementation boundary

Once authoritative API contracts are available, the minimal compatible
change should be limited to:

- an isolated `budgetpixel_provider.py` containing the authoritative model
  registry, server-side validation, payload builder, submit/poll logic,
  result parsing, and sanitized provider errors;
- an isolated `derabox_storage.py` containing the documented upload/auth
  contract, bounded retry/timeouts, and public/direct URL verification;
- a small provider dispatch in the existing generate and upload routes;
- a BudgetPixel worker that updates the existing `AIVIDEO_TASKS` record and
  stores a distinct `provider_job_id`;
- capability-driven additions to the existing `modelFamilies` and
  `applyModelCapabilities()` UI paths.

The existing Segmind worker, Dropbox helpers, polling routes, task database,
History, Archive, authentication, CSRF protection, and result UI must remain
the defaults and must not be replaced.

## Required authoritative information

Implementation must not start until the following are available from official
BudgetPixel and Derabox documentation or an exported OpenAPI schema:

- BudgetPixel API base URL, authentication header, submit endpoint, status
  endpoint, response/job states, error schema, and result schema;
- exact production model IDs and per-model capabilities for Seedance 2.5,
  WAN 3.0, WAN 3.0 Prime, and any other model intended for production;
- exact field names and allowed combinations for start/end frames, reference
  images/videos/audio, video-to-video, duration, resolution, aspect ratio,
  generated audio, and negative prompts;
- server-side reference count and total-duration limits;
- Derabox upload endpoint, authentication method, multipart/request schema,
  response schema, deletion/expiry behavior, and documented public/direct URL
  guarantee suitable for server-to-server provider downloads.

## Security constraints

- `BUDGETPIXEL_API_KEY` is registered only in the backend encrypted-secret
  architecture and must never be rendered into HTML or returned by the secret
  metadata endpoint.
- Derabox credentials must use the same backend-only pattern after their exact
  official names and authentication contract are known.
- Arbitrary client-provided remote URLs must not be accepted. BudgetPixel
  reference URLs should originate from the controlled Derabox upload result.
- Existing MIME/extension/size checks, authentication, CSRF, rate limiting,
  URL allowlisting, and sanitized logging must not be weakened.

## Verification status

The repository search found no existing BudgetPixel or Derabox implementation.
Network attempts to the named service domains were rejected by the execution
environment proxy with HTTP 403, and the configured web-search service returned
HTTP 401. Therefore no model capability or API transport claim is treated as
verified, and no paid generation was attempted.
