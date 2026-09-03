# MII image generation capability matrix

Audit date: 2026-09-03. `budgetpixel_provider.IMAGE_CAPABILITIES` is the single
source of truth. The authenticated `/api/aivideo/image-capabilities` endpoint
and server-rendered fallback both serialize that registry; neither exposes an
API key. Missing fields receive the tier default, while explicitly invalid
values return `INVALID_INPUT` (HTTP 422).

| Tier | Aspect ratios | Detail | Images | References | Advanced / format |
|---|---|---|---|---|---|
| FLUX 2 Klein | 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 21:9, 9:21, 5:4, 4:5, Match Reference | `megapixel`: 0.5, 1, 2, 4 | 1–4 | `reference_images`, max 3 | optional seed |
| FLUX 2 Pro | 1:1, 4:3, 3:4, 9:16, 16:9, 2:3, 3:2 | `size`: 0.5MP, 1MP, 2MP, 4MP | 1–4 | singular `image`, max 1 | optional seed |
| FLUX 2 Dev | 1:1, 4:3, 3:4, 9:16, 16:9, 2:3, 3:2 | — | 1–4 | `reference_images`, max 4 | optional seed |
| Qwen Image | 1:1, 16:9, 9:16, 21:9, 9:21, 4:3, 3:4, 3:2, 2:3 | — | 1–4 | — | optional seed |
| Seedream 5 Lite | 1:1, 4:3, 3:4, 16:9, 9:16, 2:3, 3:2, 21:9, 9:21 | `size`: 2K, 3K | 1–4 | `reference_images`, max 9 | sequential disabled/auto; auto max 1–14 |
| Seedream 5 Pro | same Seedream ratios | `size`: 1K, 2K | 1–4 | `reference_images`, max 9 | — |
| Kling Image V3 | 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 21:9 | `size`: 1K, 2K | 1–4 | singular `image`, max 1 | negative prompt for text-to-image only |
| Kling Image V3 Omni | same Kling ratios | `size`: 1K, 2K, 4K | 1–4 | `reference_images`, max 9 | — |
| GPT Image 2 Low/Standard/High | 1:1, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 3:2, 2:3, 21:9, 9:21, 2:1, 1:2 | `resolution`: 1K, 2K, 4K | 1–4 | `reference_images`, max 9 | quality low/medium/high; PNG/JPEG |

## Representative provider payloads

```json
{"prompt":"…","aspect_ratio":"1:1","megapixel":1,"num_images":1,"reference_images":["https://…"],"seed":42}
{"prompt":"…","aspect_ratio":"4:3","size":"1MP","num_images":1,"image":"https://…","seed":42}
{"prompt":"…","aspect_ratio":"3:2","num_images":1,"reference_images":["https://…"]}
{"prompt":"…","aspect_ratio":"21:9","num_images":1,"seed":42}
{"prompt":"…","aspect_ratio":"16:9","size":"3K","num_images":1,"reference_images":["https://…"],"sequential_image_generation":"auto","max_images":8}
{"prompt":"…","aspect_ratio":"16:9","size":"2K","num_images":1,"reference_images":["https://…"]}
{"prompt":"…","aspect_ratio":"1:1","size":"2K","num_images":1,"negative_prompt":"…"}
{"prompt":"…","aspect_ratio":"21:9","size":"4K","num_images":1,"reference_images":["https://…"]}
{"prompt":"…","aspect_ratio":"1:1","resolution":"4K","quality":"high","num_images":1,"output_format":"png","reference_images":["https://…"]}
```

The image prompt is passed unchanged; MII Quality Filter remains video-only.
Image output arrays remain position-sorted and URL-deduplicated. Original PNG,
JPEG, WebP, and GIF bytes are detected by magic bytes and archived without
canvas conversion, resizing, recompression, or transcoding.
