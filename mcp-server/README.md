# MiiAiVideo MCP Server

Wraps makima.cloud's AI Video API (`/api/aivideo/*`) as MCP tools:
`list_models`, `generate_video`, `generate_image`, `check_status`,
`wait_for_result`. Every tool is just an authenticated HTTP call to the
Flask backend you already run — this service holds only the shared API key, no
generation logic, and no state of its own.

## 1. Set the shared key on makima.cloud (do this first)

1. Open `https://makima.cloud/ai-video/app-secrets` (log in with the
   normal /ai-video password like always).
2. Find **"MCP Server API Key"** under *Admin Passwords*.
3. Generate a long random string and save it there — anything works, e.g.
   open any password generator app and use a 40+ character result. Copy
   it somewhere safe; you'll paste the exact same value into Railway in
   step 3 below.

This key is completely separate from your normal /ai-video login
password. Nothing else uses it.

## 2. Deploy this folder as a NEW Railway service

Your `MONE` GitHub repo already has this `mcp-server/` folder in it. In
Railway:

1. Open your existing project (the one with the `web` service — makima.cloud).
2. Tap **"+ New"** → **"GitHub Repo"** → pick the same `MONE` repo again.
   (Yes, the same repo — Railway lets you run two services from one repo,
   each pointed at a different folder.)
3. Once it's created, open that new service → **Settings**:
   - **Root Directory**: set to `mcp-server`
   - **Start Command**: leave as-is (it'll pick up the `Procfile` in this
     folder automatically — `python server.py`)
4. Open **Variables** on this new service and add:
   - `MII_MCP_API_KEY` = the exact same value you saved in step 1
   - `MII_BASE_URL` = `https://makima.cloud` (only needed if your domain
     is ever different from this)
5. Deploy. Once it's live, Railway gives this service its own public URL
   — something like `https://mii-mcp-production.up.railway.app`. Copy
   that URL.

## 3. Connect it in Claude

The server speaks Streamable HTTP at `<that Railway URL>/mcp`. Add it as
a custom connector wherever Claude lets you add a remote MCP server URL
(Claude.ai → Settings → Connectors → Add custom connector, or the
equivalent in Claude Code/Desktop) — paste the `/mcp` URL there.

The MCP endpoint requires `Authorization: Bearer <MII_MCP_API_KEY>` on
every request. Use a client that supports custom authorization headers; a
URL-only connector will receive HTTP 401. OAuth is not implemented.
Do not put the key in the URL.

## What each tool does

- **list_models** — every family/variant MiiAiVideo has configured right
  now, with resolution/duration/aspect-ratio limits for each. Call this
  first if you're not sure what values are valid.
- **generate_video** — text-to-video only for now (no reference
  images/video/audio, no first/last frame yet — those can be added later
  if useful).
- **generate_image** — text-to-image.
- **check_status** — poll a task_id once.
- **wait_for_result** — polls automatically every 5s up to a timeout
  (capped at 280s) and returns once the job finishes, so Claude doesn't
  have to call check_status in a loop by hand.

## Known gap

BudgetPixel's own image models (the `flux2` family you'll see listed in
`list_models`'s image section) aren't actually wired up in the
`/api/aivideo/generate` backend yet — that endpoint only recognizes
`flux2` for capability *display*, not generation. `generate_image`'s
default (`family="nanobanana"`) avoids this and works today; picking
`family="flux2"` from the list_models output will currently fail. Worth
fixing on the main app in a future session if you want that model
working end-to-end.
