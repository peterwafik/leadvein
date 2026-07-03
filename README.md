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
   *Geo-filtering:* set **Country** (e.g. `GB`, `US`, `Germany`) to keep only in-country leads —
   detection uses ccTLD, phone country code and schema.org address, and the detected country is
   shown per lead. By default a lead is dropped only if it's positively a *different* country;
   tick **Strict geo** to also drop leads with no detectable country.
3. **Fields to extract** — toggle the output columns.
4. **Run** — watch the live progress bar + log; confirmed leads stream into the table. When done,
   download `.xlsx` (a `<Type> Prospects` tab) or `.csv`.

## API keys (optional)
Copy `.env.example` to `.env`. urlscan.io free search needs **no key**.
- `PUBLICWWW_KEY` — required to use the PublicWWW discovery source.
- `URLSCAN_KEY` — optional; raises urlscan rate limits.

## Admin / access control (optional)
Recipe management (creating + testing custom recipes) can be locked behind a single
admin login. It is **opt-in**:
- Leave `ADMIN_PASSWORD` blank → the app runs fully **open** (local default); anyone can
  create/test recipes.
- Set `ADMIN_PASSWORD` (and optionally `ADMIN_USER`, default `admin`) → creating/testing
  recipes requires HTTP Basic auth with those credentials. The UI prompts for them on first
  use. **Running jobs and downloading exports are never gated** — unauthenticated users are
  "run-only". Credentials are read from the environment only, never hardcoded.

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

## Data sources & licensing
- **Geographic reference:** country/region/city reference data derived from
  [GeoNames](https://www.geonames.org) (CC BY 4.0). Used only to render the area
  selector; lead coverage counts always come from actual inventory.

## Bulk OSM ingestion (Geofabrik)

The marketplace supports bulk ingestion of businesses from OpenStreetMap (OSM) via
[Geofabrik](https://geofabrik.de) extracts. This runbook documents the process, constraints,
and operational expectations.

### Before you ingest

- **Extract size:** GB extracts (e.g. United Kingdom) are roughly 1.5–2.0 GB to download.
- **Parse time:** parsing a standard extract takes tens of minutes; monitor the admin Ingestion
  progress log.
- **Disk cache:** the node-location cache uses several GB of temporary disk during parsing.
  It is **automatically deleted** after the run completes.
- **No per-lead enrichment during bulk:** bulk imports do not fetch/verify individual websites or
  perform verification enrichment. Run website enrichment separately on a filtered subset if needed.

### Import & funnel

- **Funnel visibility:** lead counts at each stage (raw → matched → stored/merged → hot) are
  **measured on the admin Ingestion page after import completes**. These numbers are never
  promised in advance; they reflect actual deduplication, quality filtering, and your region/
  category selection.
- **Re-import cadence:** bulks are imported manually. A weekly cadence is suggested; set a
  calendar reminder or cron job to ingest fresh Geofabrik snapshots.
- **Whole-planet:** out of scope. Ingest by country or region; combine smaller extracts if
  you need multi-country coverage.
- **Deduplication:** the current dedup key groups businesses by city + category. Phone-less
  businesses that share a location and category **collapse into a single record** (a known
  pilot limitation). If phone data is critical for your use case, contact the team.

### Attribution & legal

Lead records carry the source and license:
- **Attribution:** © OpenStreetMap contributors (ODbL) · extract by Geofabrik GmbH
- **License:** ODbL (Open Data Commons Open Database License). You are responsible for
  complying with the terms when republishing or commercializing the data.

### Operational triggers

Monitor these signals after each import to decide whether to upgrade infrastructure:

- **Second country ingest:** If you ingest OSM data from a second country (second bulk import),
  verify that search latency (p95) stays at or below the target (0.5s at 250k records).
- **Concurrent imports:** Running two bulk imports in parallel is not recommended; finish one
  before starting the next. If you need concurrent ingestion, contact the team.
- **Sustained latency misses:** If the admin search latency dashboard shows p95 > 1.0s
  consistently (not just during import), trigger a scaling review. The current single-table
  SQLite schema is optimized for ~250k hot leads; beyond that, migrate to Postgres and add
  indexes.

## LeadVault (compliant B2B lead marketplace)

Run the marketplace app:
```bash
.venv/Scripts/python -m uvicorn app.leadvault:app --reload
```
Open http://127.0.0.1:8000 → /login. Seeded accounts:
- Admin: `admin@leadvault.local` / `admin12345` (set `LEADVAULT_ADMIN_PW` to override)
- Demo buyer: `buyer@demo.local` / `buyer12345` (100 credits)

Flow: admin → Ingestion (pick `osm_overpass`, a city, categories) → buyer → Marketplace
(masked previews) → Unlock (credits) → Purchased Leads → Export CSV. Every lead carries its
source, license (e.g. ODbL/OpenStreetMap), and verification date; opt-out/suppression are
filtered at search, purchase, and export; all unlocks/exports are in the admin Audit Log.

Architecture: source-agnostic `app/core/` marketplace core + pluggable `app/adapters/`
(OSM/Overpass, urlscan-fingerprint) + `app/scoring/profiles/` (utility_energy is one profile).
Adding a data source = adding an adapter; adding a vertical = adding a scoring profile.

### Lead quality gate

All leads pass through a configurable quality gate at search, preview, and unlock. The gate enforces a per-buyer quality profile (default BASELINE) that requires leads to meet or exceed a minimum tier:

- **Present:** contact data exists (scraped or enriched).
- **Validated:** email passes syntax + MX + non-disposable checks; phone passes format + line-type validation; address is geocodable; website is reachable; lead profile is ≥ 40% complete.
- **Verified-live:** contact details verified against a licensed data provider (Dun & Bradstreet, ZoomInfo, etc.). Leads claiming this tier but lacking an active provider license render as "not available — requires verification/enrichment provider."

Leads below the active profile's minimum tier are held back from search results, masked in previews, and cannot be unlocked. All email validation uses syntax/MX/disposable checks only — **SMTP probes are permanently disabled** (INV-Q6) to respect bounce-back policies.

### Production / pilot deployment

Set `LEADVAULT_ENV=prod` and the app enforces hardening:
- `LEADVAULT_SECRET` MUST be set to a strong random value (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) — the app refuses to start on the dev default.
- Session cookies are issued `Secure` + `HttpOnly` + `SameSite=Lax` (serve over HTTPS / behind a TLS-terminating proxy).
- Tracebacks are never shown to clients (`debug=False`).
- The demo buyer is NOT seeded; the admin is seeded only from `LEADVAULT_ADMIN_EMAIL` + `LEADVAULT_ADMIN_PASSWORD` (rotate off the dev `admin12345` default). If unset, no admin is created and a warning is logged — create one out of band.
Run behind HTTPS, e.g. `uvicorn app.leadvault:app --host 0.0.0.0 --port 8000` fronted by a TLS proxy.

### Billing (Stripe credit packs)

Buyers can buy credit packs via Stripe Checkout. It is OFF until configured:
- Set `STRIPE_SECRET_KEY` (test mode) to enable the Buy buttons.
- Set `STRIPE_WEBHOOK_SECRET` and point a Stripe webhook at `POST /stripe/webhook` for the
  `checkout.session.completed` event. **Credits are granted only by the verified webhook** (idempotent),
  never by the success redirect. With no key set, the Billing page shows a notice and credits remain
  admin-granted. `BILLING_CURRENCY` defaults to `gbp`.

### Operations (pilot)

- **Audit log:** every credit grant, unlock, opt-out, ingestion, and purge is recorded and reviewable by an admin at `/admin/audit`.
- **Error log:** unhandled errors return a clean 500 (no traceback leaked to the client) and are logged with full traceback to stderr — and to a file if `LEADVAULT_LOG` is set (e.g. `LEADVAULT_LOG=/var/log/leadvault.log`).
- **Backup / restore (SQLite):** the database is a single file (`leadvault.db`, or `$LEADVAULT_DB`). Back it up online with the SQLite backup API (safe while running):
  - Backup: `sqlite3 leadvault.db ".backup '/backups/leadvault-$(date +%F).db'"`
  - Restore: stop the app, then `cp /backups/leadvault-YYYY-MM-DD.db leadvault.db` and restart.
  Schedule the backup via cron. (Postgres is the production target; the models are Postgres-ready.)

### Stripe webhook go-live (test mode)

The webhook signature-verification + idempotency path is proven against real HMAC signatures by
`scripts/verify_stripe_webhook.py` (run it against a running server with `STRIPE_WEBHOOK_SECRET` set).
To wire Stripe's own delivery to a deployed instance:
1. Deploy behind HTTPS with `LEADVAULT_ENV=prod`, `LEADVAULT_SECRET`, `STRIPE_SECRET_KEY` (test mode), and `STRIPE_WEBHOOK_SECRET`.
2. In the Stripe Dashboard (test mode) → Developers → Webhooks, add an endpoint `https://<your-host>/stripe/webhook` subscribed to `checkout.session.completed`; copy its signing secret into `STRIPE_WEBHOOK_SECRET`.
3. Buy a pack with a Stripe test card (4242 4242 4242 4242) → confirm the credit lands once (the buyer's ledger shows one `stripe_purchase` row). Stripe's "resend" on the event must NOT double-credit.
   - No public URL handy? Use the Stripe CLI: `stripe listen --forward-to localhost:8000/stripe/webhook` then `stripe trigger checkout.session.completed`.

### Lead quality gate — rollout & tracked follow-ups

- **Backfill required before a pilot:** leads ingested before the quality gate carry an empty
  `validation_json` and are therefore held back at search/preview/unlock (fail-closed — the safe
  direction). Re-ingest / re-stamp inventory so hot leads actually flow.
- **Schema migration (persistent DB only):** the gate added two `Lead` columns —
  `validation_json` and `completeness_score`. On a *persistent* database (Postgres, or a kept SQLite
  file) add them via an `ALTER TABLE` migration; `SQLModel.metadata.create_all` only creates missing
  tables, it does not add columns to an existing one. The pilot's throwaway SQLite DB is recreated, so
  no action there.
- **Phone region is UK-only (tracked follow-up — config, not hard-code):**
  `app/quality/validators/phone.py` parses national-format numbers with a hard-coded `region="GB"`.
  International `+E.164` numbers validate correctly regardless — confirmed: `+44 20 7946 0958`,
  `+1 202 555 0143`, `+33 1 42 68 53 00` all validate; a US number in national format `202 555 0143`
  (no `+`) does not. So international inventory is NOT silently dropped, only **national-format non-GB**
  numbers. Before any non-UK ingest, make the region configurable (per source/country).
