# MII image generation capability matrix

Audit date: 2026-09-03. The registry is split by provider endpoint; fields are
never copied between models. `—` means the endpoint does not receive that
control. Defaults are used only for missing/invalid input.

## BudgetPixel

| Family / tier | Endpoint | Ratio (default) | Detail control | Count | References | Other output fields |
|---|---|---|---|---|---|---|
| FLUX 2 Klein | `/images/flux-2-klein` | 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 21:9, 9:21, 5:4, 4:5, match input (1:1) | megapixel 0.5/1/2/4 (1) | 1–4 | 3 | optional integer seed |
| FLUX 2 Pro | `/images/flux-2-pro` | same FLUX 2 set (1:1) | megapixel 1/2/4 (1) | 1–4 | 3 | optional integer seed |
| FLUX 2 Dev | `/images/flux-2-dev` | same FLUX 2 set (1:1) | megapixel 1/2/4 (1) | 1–4 | 3 | optional integer seed |
| Qwen Image | `/images/qwen-image` | 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3 (1:1) | — | 1–4 | — | optional integer seed |
| Seedream 5 Lite | `/images/seedream-5.0-lite` | 1:1, 3:4, 4:3, 9:16, 16:9 (1:1) | resolution 1K/2K | 1–4 | — | — |
| Seedream 5 Pro | `/images/seedream-5.0-pro` | 1:1, 3:4, 4:3, 9:16, 16:9 (1:1) | resolution 1K/2K | 1–4 | — | — |
| Kling Image V3 | `/images/kling-v3` | 1:1, 16:9, 9:16, 4:3, 3:4 (1:1) | — | 1–4 | — | — |
| Kling Image Omni | `/images/kling-v3-omni` | 1:1, 16:9, 9:16, 4:3, 3:4 (1:1) | — | 1–4 | 10 | — |
| GPT Image 2 Low/Standard/High | `/images/gpt-image-2` | 13 documented ratios (1:1) | resolution 1K/2K/4K; quality low/medium/high follows tier | 1–4 | 9 | PNG/JPEG |

FLUX 2 `match_input_image` is only valid when at least one reference exists.
All BudgetPixel image output arrays are position-sorted and exact-URL deduped.

## Existing Segmind adapters

| Model | Endpoint | Contract exposed by MII |
|---|---|---|
| Nano Banana Pro Fast/Standard/Ultra | `nano-banana-pro` | ratio; output resolution 1K/2K/4K by tier; up to 14 input images |
| Seedream 5 Pro | `seedream-5-pro` | ratio; size 1K/2K; PNG; up to 10 `image_input` references |
| FLUX Schnell | `fast-flux-schnell` | ratio; fixed 4 steps; no references |
| FLUX Dev | `flux-dev` | ratio; one sample; PNG quality 95; no references |
| FLUX Pro | `flux-1.1-pro-ultra` | ratio; PNG; no references |
| Imagen 4 | `imagen-4` | five ratios and optional negative prompt; no references |
| Qwen Image | `qwen-image` | seven ratios; PNG; optional negative prompt; no references |

The adapters do not send video-only duration, audio, video references, or
resolution fields to image endpoints unless explicitly named above. Main
result bytes are uploaded without canvas conversion, resizing, recompression,
or transcoding. PNG, JPEG, WebP and GIF are recognized by magic bytes and get
matching storage extensions.
