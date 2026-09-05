# AI Video and Home audit — 2026-09-05

Scope: repository file inventory; Python syntax scan; Home pet integration; AI Video template, pet modules, generation/status/result/upload/download routes, provider registry, archive persistence and existing test suites. This is not a full security or production verification of every line.

## Fixed

- Home no longer imports the pet bootstrap or stylesheet, so its autonomous engine and sprite are not loaded.
- AI Video pet was appended to pageAiVideo rather than the canvas or panel. Its absolute bottom position overlapped the generator. It now anchors to the existing panel wrapper, with its bottom 6px above the wrapper. This follows expanded/collapsed panel height through CSS, without observers or polling.
- Removed pet paint containment that clipped status bubbles, and aligned bubbles inward from the left edge. Pointer events remain transparent; generation controls retain their behavior.

## Backend findings requiring separate integration work

- app.py aivideo_generate routes only seedance25 and wan30 to BudgetPixel. Other families first require a Segmind key. The BudgetPixel image registry contains flux2, qwenbp, seedream5 and klingimage, but these families have no corresponding dispatch branch in that route. GPT Image still takes the Segmind branch. Registry support therefore does not establish end-to-end integration.
- The route truncates image_urls to nine entries before provider validation. Increasing frontend reference limits alone cannot provide support above nine; provider limits and dispatch need coordinated verification.
- Generation/status/result/upload/download routes inspected retain authentication checks. Download checks the source URL and rate limit. These checks do not constitute a full security assessment.

## Validation and limits

- Python compileall and pet JavaScript module syntax checks passed.
- unittest discovery: 31 tests passed; 9 test modules could not import due to missing requests/Flask dependencies. Dependency installation was blocked by network approval cancellation. These are environment errors, not established application failures.
- Three existing AI Video pet checks and Home import removal check passed.
- No paid generation, production bot toggle, credentials update, or provider switch was performed. Mobile/desktop rendering and production deployment remain unverified.
