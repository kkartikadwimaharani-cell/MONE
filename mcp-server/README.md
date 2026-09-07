# MIIAIVIDEO MCP

The primary connector now runs inside the existing MONE web service.
No second Railway service is required for this integration.

- Owner dashboard: `https://makima.cloud/ai-video/mcp`
- Remote MCP URL: `https://makima.cloud/mcp`
- Transport: stateless Streamable HTTP with JSON responses.
- Authentication: OAuth authorization code + PKCE S256, or a per-agent Bearer key.

## Connect

Open the owner dashboard and sign in with the AI Video password. Copy the MCP
URL into a client supporting Streamable HTTP and OAuth. Dynamic client
registration is supported; choose OAuth/DCR if the client offers a choice.
Approve the requesting agent on makima.cloud. Availability of custom MCP
connectors depends on the client, account, and workspace settings.

For Codex CLI:

```sh
codex mcp add miiaivideo --url https://makima.cloud/mcp
codex mcp login miiaivideo
```

For clients with an API-key/header field, create a named key on the dashboard
and send `Authorization: Bearer <key>`. Keys are shown once, valid for one year,
and stored only as hashes. Never append credentials to the URL. Revoke keys
and OAuth grants from the dashboard. Revocation invalidates access immediately.
A browser session alone cannot call MCP, and MCP credentials cannot manage
App Secrets or other administrative settings.

## Tools

- `miiaivideo_list_models`: supported backend models, variants and controls.
- `miiaivideo_generate_video`: video generation, including supported references/frames.
- `miiaivideo_generate_image`: image generation and supported image references.
- `miiaivideo_generate_audio`: audio generation and supported references.
- `miiaivideo_motion_control`: source-video editing through existing validation.
- `miiaivideo_check_status`: task status and output URL.

Generation calls spend provider credits. Validation rejects unsupported
controls before submission. Calls use the existing application's generation
functions, queues, and history. Provider availability and upstream errors are
reported as tool errors; local tests do not prove that a provider account has
credit or that every upstream service is online. Motion validation may take
longer than a client's default tool timeout for large videos.

The model catalog currently exposes both configured MIIAIVIDEO provider paths.
BudgetPixel image families are `flux2` (KLEIN/PRO/DEV), `qwenbp`, `seedream5`
(LITE/PRO), `klingimage` (V3/OMNI), and `gptimagebp` (LOW/STANDARD/HIGH).
The `bp` suffix separates a BudgetPixel-backed family from a same-named
Segmind-backed family and prevents requests from silently reaching the wrong
provider.

## Deployment and persistence

Deploy the current `main` branch using the web service's existing root
`Procfile` (`python start.py`). Root dependencies are unchanged. The dashboard
and `/mcp` route belong to `app.py` + `mii_mcp.py`.

Keep `FLASK_SECRET_KEY` stable for browser sessions. Keep the existing AI Video
password and provider keys configured. `MII_PUBLIC_URL` defaults to
`https://makima.cloud`; use an HTTPS origin without a path for a different host.
OAuth records and key hashes use `data/mcp_access.sqlite3` by default. Mount
that directory on durable storage or set `MII_MCP_DB` to a database path on a
Railway volume. Without persistent storage, redeploying can require reconnecting
agents. Backups of this database contain hashes, not raw keys or tokens.

The old standalone `server.py` in this directory remains a legacy deployment
option using `MII_MCP_API_KEY`. It is not the new same-domain connector and does
not provide the dashboard or OAuth flow. Existing legacy services are not
modified or shut down automatically.

## Validation

Install the root requirements and this directory's requirements for tests:

```sh
python -m unittest discover -s tests -v
```

The integration suite verifies all six tools and each advertised model variant
with provider workers mocked, dashboard/diagnostics rendering, key revocation,
OAuth PKCE/code replay/refresh rotation, metadata discovery, and interoperability
with the official MCP Python client. Real ChatGPT/Claude account connections
and paid provider generations still require live integration checks.

Protocol references:
- https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- https://developers.openai.com/plugins/build/auth
- https://learn.chatgpt.com/docs/extend/mcp?surface=cli
