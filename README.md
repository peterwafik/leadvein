# Lead Scraper

Find businesses running a specific web technology (via fingerprint **Recipes**),
verify it, scrape **publicly published** contact details, and export to Excel/CSV.
A UI-driven generalization of a single-purpose GloriaFood finder.

## Requirements
- Python 3.11 (on Windows, invoked as `py -3.11`)
- No Node, no Docker — the frontend is a single static page (Tailwind via CDN).

## Setup
```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```
(On macOS/Linux the interpreter is `.venv/bin/python`.)

## Run
```bash
.venv/Scripts/python -m uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## How to use
1. **What to find** — pick a Category → Type (e.g. *Online Ordering / Restaurants → GloriaFood*).
   The recipe's fingerprints are shown read-only. "+ Custom recipe" lets you define your own
   (it runs a small live test before saving).
2. **Where / filters** — discovery source (urlscan.io free by default, or PublicWWW with a key),
   optional country/keyword, max results, politeness delay + concurrency, and an "only confirmed"
   toggle. Expand **Manual domains** to bypass discovery and verify a hand-picked host list.
3. **Fields to extract** — toggle the output columns.
4. **Run** — watch the live progress bar + log; confirmed leads stream into the table. When done,
   download `.xlsx` (a `<Type> Prospects` tab) or `.csv`.

## API keys (optional)
Copy `.env.example` to `.env`. urlscan.io free search needs **no key**.
- `PUBLICWWW_KEY` — required to use the PublicWWW discovery source.
- `URLSCAN_KEY` — optional; raises urlscan rate limits.

## Tests
```bash
.venv/Scripts/python -m pytest -q
```

## How it works
- **Engine** (`app/engine/`, pure Python): `discover` (urlscan/PublicWWW) → `fetch` + `analyse`
  (fingerprint verify, name, filtered emails/phones, recipe ID extractors, socials) → `export`
  (xlsx/csv/append). `runner.run_job` orchestrates with per-host robots checks, a global rate
  limiter, and a concurrency cap, emitting `progress`/`lead`/`done` events.
- **API** (`app/main.py`, FastAPI): recipes CRUD + test, job start, SSE progress stream, and
  downloads. Jobs run as background asyncio work; recipes persist in SQLite (`leadscraper.db`).
- **UI** (`app/static/`): one static page consuming the API over `fetch` + `EventSource`.

## Compliance
You are responsible for complying with urlscan/PublicWWW Terms of Service and applicable law
(e.g. GDPR / CAN-SPAM) when contacting leads. The tool collects only publicly published business
contact info. Every lead row has a **Status** column (default "Not contacted") so the sheet
doubles as an outreach tracker and supports opt-out handling.
