# Aetheria Core V23.1 — India-First Living World

V23.1 is the consolidated Aetheria baseline built from the stable V16 visual language and the deterministic intelligence capabilities developed through V17–V21.

## Product model
- India-first international news intelligence: Indian developments are given a stronger editorial path without suppressing global coverage.
- Top News remains the first content surface. The Stack contains the 10 latest verified events.
- Aetheria Now / India Lens / Impact / Latest / Early Signals / Next / Desks form one editorial flow, not a dashboard of widgets.
- Local deterministic Aetheria Intelligence Engine: event clustering, corroboration, reliability, conflict detection, evidence synthesis, summarisation, India relevance, impact paths, contextual related stories and behavioural calibration.
- No external LLM/GPT dependency. No fake AI output.
- Multilingual discovery paths cover Hindi plus Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati and Punjabi through verified publisher RSS and GDELT language discovery.
- Market Pulse surfaces latest observed index, FX-reference and bullion values with source state; unavailable data stays unavailable.
- Story analysis is evidence-grounded and tied to the event: why it matters, India/life relevance and what to watch next.

## Source registry
The registry contains 184 configured sources, including 93 India-targeted publisher feeds/discovery sources. India-targeted RSS entries from ABP Live, OneIndia Hindi, Business Standard Hindi and Live Hindustan are maintained from their public RSS directories; the remainder of the global registry is retained for comprehensive world coverage.

## Runtime
- Python standard library server.
- SQLite with cached in-memory snapshot for fast reads.
- 32 worker source ingestion by default.
- 2 second scan/snapshot cadence.
- 184-source registry with per-source limits and conditional HTTP caching.
- No browser auto-open. Server prints HTTP READY / LAN READY after the port is bound.

## Main APIs
`/api/bootstrap` · `/api/search` · `/api/suggest` · `/api/event/<id>` · `/api/future` · `/api/replay` · `/api/knowledge-gap/<id>` · `/api/intelligence/status` · `/api/market` · `/api/diagnostics` · `/api/sources` · `/api/perf` · `/api/state`

## Run locally
```bat
cd /d D:\News\aetheria_core_v23_1
py server.py
```
Open `http://127.0.0.1:8000`.

## 24x7 path
See `DEPLOYMENT_24X7.md`. The immediate zero-cost Windows option is Task Scheduler starting Aetheria at system startup. For public cloud operation, keep ingestion scheduled/event-driven and move the persistence/API layer off local SQLite; GitHub Actions standard runners are free for public repositories, while Cloudflare Workers are suitable as a thin edge layer rather than as the RSS crawler.


## V23.1 product changes
- V16 visual language retained; reading surfaces are solid and glass effects are disabled.
- Dedicated Flash lane is separate from the main story flow.
- Entertainment is a first-class desk/category.
- India Now is a strict India/local relevance lane; global coverage remains broad.
- Dynamic RSS catalog discovery refreshes publisher feed URLs from official RSS directory pages and persists discovered feeds.
- Local context is configurable with AETHERIA_CITY and AETHERIA_STATE.
- Markets card uses live observed indices/FX/bullion adapters; unavailable values remain unavailable.
- Search state uses sequence-safe requests and input preservation.
- Aetheria Read hints are derived from event signals and source evidence; no GPT/OpenAI dependency.
- `/api/ready` reports whether a usable snapshot is available.


## V23.1 finalization
- V16 visual language is retained with solid reading surfaces and accent-only gradients.
- Flash/Breaking is isolated in its own rail and excluded from the normal Latest lane.
- Story Stack is a real 10-story editorial stack using the homepage editorial score; Latest remains chronological.
- India Now is a strict India/local lane, while World remains globally comprehensive.
- Entertainment & Culture is a standalone desk; Sports is separate.
- Dynamic RSS catalog discovery now also covers Live Hindustan and refreshes official publisher catalogs without requiring hardcoded article data.
- Market Pulse uses market quotes when available and labels lower-frequency reference data honestly.
- Search preserves the input value and uses sequence-safe suggestions/search requests with Indic fallback.
- Aetheria Read / Evidence / Life & Local relevance are derived by the local deterministic engine; there is no GPT/OpenAI dependency.
- `/api/deployment` exposes deployment capability metadata.

## V23.1 finalization
- Flash/Breaking has its own first-priority rail directly below the header.
- India Now is capped to a compact, strict India/local lane; market pulse lives inside the same top zone.
- Stack remains a real 10-story editorial stack; Latest remains chronological.
- Entertainment & Culture is a first-class desk and category.
- Aetheria Read includes observed life/decision relevance without a third-party LLM.
- Dynamic Indian RSS catalog discovery is retained and expanded; GDELT language discovery remains the broad multilingual safety net.


## V23.1 final product contract
- Flash/Breaking is a separate first-priority rail; flash events are excluded from the normal Latest lane.
- Top News Stack contains ten real events when ten verified events are available and remains compact.
- India Now is a strict India/local lane with market pulse embedded in the same top zone.
- India-first ranking blends India relevance, local relevance, movement, freshness and global significance instead of forcing every story to be India-only.
- Entertainment & Culture is a first-class category and desk.
- All story explanations are generated by the local deterministic Aetheria engine from observed source/event data.
- No GPT, OpenAI, fake fallback stories, or hardcoded live values.
