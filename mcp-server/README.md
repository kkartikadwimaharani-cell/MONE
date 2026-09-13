# MII AI STUDIO MCP

The production MCP server is part of the main MONE Flask service. Do not deploy a second Railway service for the primary connector.

- Owner dashboard: `https://makima.cloud/ai-video/mcp`
- MCP endpoint: `https://makima.cloud/mcp`
- Transport: stateless Streamable HTTP JSON
- Authentication: OAuth authorization code with PKCE S256, or a named Bearer key created by the owner

## Connect

Open the owner dashboard, sign in to the private AI Video workspace, and copy the MCP endpoint into a client that supports Streamable HTTP. Prefer OAuth/DCR. Approve the requesting client on `makima.cloud`.

For Codex CLI:

```sh
codex mcp add mii-ai-studio --url https://makima.cloud/mcp
codex mcp login mii-ai-studio
```

For a client that only supports an Authorization header, create a named key on the dashboard and send `Authorization: Bearer <key>`. Keys are shown once and stored only as hashes. Never place a credential in the URL. Revoking the grant invalidates access.

## Production tools

The same-origin server publishes 13 tools. Their canonical prefix is `mii_ai_studio_`; the older `miiaivideo_` prefix remains accepted only as a compatibility alias.

- `list_models`
- `get_model_capabilities`
- `upload_reference`
- `generate_video`
- `generate_image`
- `generate_audio`
- `generate_music`
- `generate_sfx`
- `video_to_music`
- `video_to_sfx`
- `motion_control`
- `check_status`
- `clear_debug`

Generation tools spend account credits only when called. `upload_reference`, model discovery, capability lookup, and status reads do not generate media. The embedded result card follows one task through the signed widget-status endpoint, so clients must not repeatedly create status cards or poll `check_status` in a loop.

The reviewed local catalogue currently contains 116 contracts: 43 video, 63 image, 8 audio, and 2 motion. This means the server has a validated local handler and schema for each entry. It does **not** mean unlimited or permanently online: provider credits, rate limits, account access, catalogue changes, and upstream outages still apply. `list_models` reports whether the provider key is configured without spending credits.

## Reference limits

The MCP accepts up to 15 image URLs, 5 video URLs, and 5 audio URLs at the transport level. Each model's smaller limit is enforced from `get_model_capabilities`. Upload reference images one at a time as PNG, JPEG, or WEBP up to 5 MB, then pass the returned HTTPS URLs in the original order.

## Persistence on Railway

OAuth grants, key hashes, encrypted app secrets, task history, archives, and analytics must live on a Railway volume. Mount a volume and set:

```env
MII_DATA_DIR=/data
MII_MCP_DB=/data/mcp_access.sqlite3
MII_AIVIDEO_DB=/data/aivideo_archive.db
MII_ANALYTICS_DB=/data/analytics.db
```

Use the actual volume mount path if it is not `/data`. The application also recognizes `RAILWAY_VOLUME_MOUNT_PATH`. Without durable storage, a redeploy can invalidate OAuth connections and lose SQLite-backed history even though generated media remains on Dropbox.

Keep `FLASK_SECRET_KEY` stable. Configure `MAKIMA_ADMIN_PASSWORD`; there is no built-in fallback password. `MII_PUBLIC_URL` defaults to `https://makima.cloud` and must be an HTTPS origin without a path.

## Legacy directory

`mcp-server/server.py` is an old standalone proxy and is not the production connector. Its historical family/variant interface does not represent the current 116-model catalogue. Keep it offline unless it is deliberately migrated to the current `model_slug` contract. The authoritative implementation is `mii_mcp.py` registered by `app.py`.

## Validation

Run the root test suite before merging:

```sh
python -m unittest discover -s tests -v
```

The tests must verify all 13 tool definitions, OAuth PKCE and refresh rotation, reference limits, audio-model routing, the signed preview status channel, authentication boundaries, and the catalogue count without making paid provider calls. A passing mocked suite does not prove provider credit or live upstream availability.
