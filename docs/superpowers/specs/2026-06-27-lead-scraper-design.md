# Lead Scraper — MVP Vertical Slice Design

**Date:** 2026-06-27
**Status:** Approved (brainstorming)
**Scope:** MVP vertical slice of the "Lead Scraper" technology-fingerprint lead finder.

---

## 1. Goal

A web app that lets a non-technical user find businesses running a specific
technology/platform on their website, confirm it, scrape **publicly published**
contact details, and export to `.xlsx` / `.csv`.

It generalizes a single-purpose GloriaFood finder into a UI-driven tool where the
*what to find* is configured through reusable **Recipe** objects instead of code edits.

This document covers the **MVP vertical slice**: one full end-to-end path (GloriaFood
via the free urlscan.io source) plus the Custom recipe builder + Test action needed for
the acceptance test. Later iterations expand the Jobs history, recipe logos, and polish.

---

## 2. Stack (zero build step)

Chosen for: runs on this Windows machine today (Python 3.11 via `py` launcher), no
Node, no Docker.

- **Backend:** Python 3.11, FastAPI + Uvicorn.
- **Engine:** `requests`, `beautifulsoup4` + `lxml`, `openpyxl`.
- **Persistence:** SQLModel + SQLite (single file `leadscraper.db`).
- **Jobs:** background `asyncio` tasks (MVP). Progress streamed via Server-Sent Events.
- **Frontend:** single static page served by FastAPI — Tailwind via CDN + vanilla JS
  (`fetch` + `EventSource`). No bundler.
- **Run:** `py -3.11 -m uvicorn app.main:app --reload`.

---

## 3. Core concept — the Recipe

A Recipe is the generalized form of the hardcoded GloriaFood logic:

```jsonc
{
  "id": "gloriafood",
  "category": "Online Ordering / Restaurants",
  "type": "GloriaFood",
  "discovery": {
    "publicwww_query": "\"fbgcdn.com/embedder\"",
    "urlscan_query": "domain:fbgcdn.com"
  },
  "verify_fingerprints": ["fbgcdn.com", "ewm2.js", "data-glf-cuid", "data-glf-ruid", "gloriafood"],
  "id_extractors": {
    "ruid": "data-glf-ruid=[\"']([0-9a-fA-F-]+)[\"']",
    "cuid": "data-glf-cuid=[\"']([0-9a-fA-F-]+)[\"']"
  },
  "exclude_hosts": ["gloriafood", "fbgcdn", "foodbooking"]
}
```

### Built-in recipe library (seeded on first startup)

Grouped Category → Type. GloriaFood is ported faithfully; the rest are seeded with
correct fingerprints so the dropdowns are populated and runnable.

| Category | Types (fingerprint hint) |
|---|---|
| Online Ordering / Restaurants | GloriaFood (`fbgcdn.com`), ChowNow (`chownow.com`), Flipdish (`flipdish.com`) |
| E-commerce | Shopify (`cdn.shopify.com`), WooCommerce (`woocommerce`), BigCommerce (`bigcommerce.com`), Magento (`mage/`/`magento`) |
| Website Builders | Wix (`wixstatic.com`/`wix.com`), Squarespace (`squarespace.com`), Webflow (`webflow.com`), GoDaddy (`img1.wsimg.com`) |
| Booking / Scheduling | Calendly (`assets.calendly.com`), Acuity (`acuityscheduling.com`), Cal.com (`cal.com`), Mindbody (`mindbodyonline.com`) |
| Marketing / Chat | HubSpot (`js.hs-scripts.com`), Intercom (`widget.intercom.io`), Drift (`js.driftt.com`), Tawk.to (`embed.tawk.to`) |
| Payments | Stripe Checkout (`js.stripe.com`), PayPal Buttons (`paypal.com/sdk`) |
| Custom | user-defined |

### Custom recipe builder (UI form)
- Category (pick or free text) + Type name.
- Discovery query for urlscan and/or PublicWWW.
- One or more verify fingerprints (substring match).
- Optional ID extractors (label + regex with one capture group).
- Optional exclude-hosts list.
- **Test recipe** button: runs discovery with a tiny limit (5) and reports whether the
  fingerprints actually match on the fetched candidates, before saving.

---

## 4. Module layout

```
app/
  engine/
    recipes.py     # Recipe dataclass + BUILTIN_RECIPES seed library
    discover.py    # discover_urlscan, discover_publicwww, host dedup/normalize
    enrich.py      # norm_url, fetch, analyse (verify + extract)
    export.py      # write_xlsx, write_csv, append_xlsx
    runner.py      # JobRunner: discover -> politeness/concurrency -> enrich; emits events
    politeness.py  # robots.txt cache, per-host rate limiter, global delay/concurrency
  db.py            # SQLModel models: Recipe, Job, Lead; engine + session
  schemas.py       # Pydantic request/response models for the API
  main.py          # FastAPI app + routes + SSE + static mount + startup seed
  static/
    index.html     # 4-step wizard + results grid + disclaimer
    app.js         # wizard logic, SSE consumption, table, downloads
    styles.css     # small supplements to Tailwind CDN
README.md
requirements.txt
.env.example       # PUBLICWWW_KEY, URLSCAN_KEY
```

Each unit has one purpose and a clear interface:
- `discover.py` → `discover(recipe, source, limit, keyword, key) -> list[str]` (hostnames).
- `enrich.py` → `analyse(recipe, url, html) -> LeadData`; `fetch(url) -> (final_url, html)`.
- `export.py` → pure functions over a list of column-keyed dict rows.
- `runner.py` → async generator of events; does not know about HTTP or the DB schema
  beyond persisting via injected callbacks.

---

## 5. Engine behavior (ported faithfully)

### Discovery
- **urlscan.io (free default):** `GET https://urlscan.io/api/v1/search/?q=<query>&size=100`,
  paginate via `search_after` from the last result's `sort`, honor HTTP 429 with backoff,
  optional `API-Key` header if `URLSCAN_KEY` set. Extract page hostnames.
- **PublicWWW:** `GET https://publicwww.com/websites/<query>/?export=urls&key=<PUBLICWWW_KEY>`,
  one host per line. Requires key.
- Post-process: lowercase, strip `www.`, dedup, drop any host containing an `exclude_hosts`
  token. Optional keyword appended to query and/or used to filter verified pages by on-page
  text. Cap at `max_results`.

### Verify / enrich
- `fetch`: GET homepage with timeout + descriptive UA; on failure retry with trailing `/`.
- `analyse`: lowercase-scan HTML for any `verify_fingerprints` → `on_platform` (Y/N) +
  `matched` (which fingerprint). BeautifulSoup parse:
  - **name:** `<title>`, fallback `og:site_name` then `og:title`.
  - **emails:** `mailto:` links + regex over text, deduped, drop image extensions
    (`.png/.jpg/.gif/.svg/.webp`) and tracking/vendor domains (`fbgcdn`, `sentry`,
    `wixpress`, `cloudflare`, etc.).
  - **phones:** `tel:` links first, else regex over page text.
  - **ids:** each recipe `id_extractors` regex (one capture group).
  - **socials:** facebook / instagram / linkedin / x|twitter links.
  - **address/country:** best-effort from schema.org JSON-LD and TLD heuristic.

### Politeness & compliance
- Respect `robots.txt` (cached per host); skip disallowed paths.
- Per-host rate limit + global request delay (default 1.0s) + concurrency cap (default 5,
  max 10). Timeouts; never retry-storm.
- Descriptive `User-Agent` including contact info.
- Collect only publicly published business contact info.
- UI disclaimer: user is responsible for source ToS (urlscan, PublicWWW) and applicable
  law (GDPR/CAN-SPAM). `Status` column (default "Not contacted") supports opt-out tracking.

---

## 6. Data model

- **Recipe**(`id`, `category`, `type`, `logo`, `discovery_json`, `fingerprints_json`,
  `extractors_json`, `exclude_hosts_json`, `is_builtin`)
- **Job**(`id`, `recipe_id`, `source`, `filters_json`, `columns_json`, `status`,
  `created_at`, `totals_json`)
- **Lead**(`id`, `job_id`, `name`, `website`, `on_platform`, `matched`, `email`,
  `emails_all`, `phone`, `phones_all`, `ids_json`, `address`, `country`, `socials_json`,
  `source_query`, `found_at`, `status`, `notes`)

---

## 7. REST API

- `GET /api/recipes` — list (built-in + custom), grouped by category.
- `POST /api/recipes` — create custom recipe.
- `POST /api/recipes/test` — discover with limit 5, fetch + report fingerprint matches.
- `POST /api/jobs` — start a run; body = recipe id + filters + selected columns → `{job_id}`.
- `GET /api/jobs/{id}/stream` — SSE: `progress`, `lead`, `done` events.
- `GET /api/jobs/{id}/results.xlsx` and `.csv` — download.
- `POST /api/jobs/{id}/append` — upload existing tracker `.xlsx`, append preserving its
  column order, return the merged file.
- `GET /` — serves the single-page UI.

### SSE event shapes
- `progress`: `{checked, total, confirmed, current_host, log}`
- `lead`: full lead row (column-keyed).
- `done`: `{checked, confirmed, totals}`.

---

## 8. Frontend (single page)

Left: 4-step wizard (accordion/stepper).
1. **What to find** — Category → Type dropdowns (dependent); shows chosen recipe's
   fingerprints read-only; "Custom recipe" opens the builder.
2. **Where / filters** — source (urlscan free default / PublicWWW needs key), country
   (optional), vertical keyword (optional), max results (slider, default 200, cap 1000),
   request delay (default 1.0s), concurrency (default 5, cap 10), "only export confirmed"
   toggle (default ON).
3. **Fields to extract** — checklist of output columns (default all on).
4. **Run** — Run button; progress bar + monospace autoscroll log; results stream into a
   sortable/filterable table with a colored Confirmed chip; on completion show summary +
   Download .xlsx/.csv + Append-to-tracker.

Style: light theme, single accent (emerald), generous whitespace, rounded cards, subtle
borders, Inter/system font, mobile-responsive (config collapses above table). Accessible:
labels on every field, keyboard-navigable, visible focus.

A persistent disclaimer line about ToS/GDPR/CAN-SPAM responsibility is shown near Run.

---

## 9. Excel export format

Write into a tab named `<Type> Prospects` (e.g. `GloriaFood Prospects`), header row from
the user's selected columns, one row per lead. Append-to-tracker preserves the uploaded
file's existing column order. CSV mirror always offered.

---

## 10. MVP scope boundary

**In this slice:**
- GloriaFood end-to-end via urlscan free.
- Seeded built-in recipes (correct fingerprints) so dropdowns populate and run.
- 4-step Search wizard, SSE progress + streaming table, xlsx/csv download, append-to-tracker.
- Custom recipe builder + Test recipe.
- Selectable output columns.

**Deferred (minimal/stub now, expand later):**
- Rich Jobs/History page — jobs are persisted so re-download works, but no dedicated
  history screen yet.
- Per-recipe logos.
- Settings page reduced to an API-keys panel (keys also read from `.env`).

---

## 11. Risks / notes

- urlscan free search returns *recently scanned* pages; result volume per fingerprint
  varies. "0 results" must be a clear empty state, not a silent failure.
- No real `gloriafood_finder.py` exists in the workspace; GloriaFood logic is implemented
  to the spec's documented behavior (fingerprints, extractors, discovery, append layout).

---

## 12. Acceptance test

With no API key: pick Category "Online Ordering / Restaurants" → Type "GloriaFood", source
"urlscan (free)", limit 50, run it, watch live progress, see confirmed leads with
emails/phones in the table, download `.xlsx`. Then create a Custom recipe for Calendly
(fingerprint `assets.calendly.com`), test it, and run it — all without editing code.
