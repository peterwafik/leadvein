# Campaign Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]`.

> 🛑 **HARD STOP after this plan.** Build the Campaign layer, whole-branch review, then **STOP**. Do NOT
> propose or begin any next phase (Signal Acquisition, licensed sources, billing). The next decision is
> the user's: a **real utilities-UK demand test in front of testers**. That gate is theirs, not ours to
> fill. **Payments PARKED.**

**Goal:** A company picks a campaign (Utilities-UK / Business Restructuring / start-from-scratch) → the
tool compiles it into a v2 composition + a per-campaign quality profile, auto-populating the composer we
built; the buyer can tweak (guided→advanced) and save as a Segment. Restructuring's financial/size fields
render "requires licensed source" — never faked.

**Architecture:** A campaign is DATA (a `lv_campaign` row) outside `app/core`. `compile_campaign` emits an
ordinary v2 composition + notices; the composer + gate-enforced `estimate()` do the rest unchanged. A
per-campaign `QualityProfile` is threaded to the gate via an **opaque `ctx`** through core's serve-filter
path — the quality filter applies it **on top of** the always-on baseline (narrows only; INV-Q1 never
weakened). No parallel engine; no campaign/vertical/financial strings in core.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`), FastAPI/SQLModel, Jinja + Tailwind (shipped design
system), pytest. Reuses: predicate registry, `matching_by_composition`, `estimate()`, `Segment` CRUD
(`origin_key`), quality `QualityProfile`/`clears_gate`/serve-gate, scoring `utility_energy`, `audit`.

## Global Constraints (copied verbatim from the locked spec `2026-07-01-campaign-layer-design.md`)
- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do
  NOT commit `*.db`. Pilot server may hold `leadvault.db` — do NOT `rm` it; suite uses an isolated temp DB.
- **A campaign is DATA, not code.** `Campaign` model + `compile_campaign` + CRUD + seed live under
  `app/campaigns/`; vertical/financial strings live in `app/campaigns/seed.py`. Adding a campaign = adding
  data, never touching `app/core`.
- **INV-9 / grep-clean core (stricter than v2):**
  `grep -rinE "campaign|utilit|restructur|mca|lender|amount_owed|vertical" app/core/` → empty. Core sees
  only the compiled composition/Segment/ctx. Buyer/admin tokens travel as DATA in the campaign JSON.
- **INV-6 (no fabrication):** with no licensed source, a filter on a gated field
  (`has_mca`/`amount_owed`/`lender`/`size_band`) matches ZERO leads (tri-state unknown), its negation
  surfaces none, no lead carries/displays a placeholder/inferred value; UI shows "requires licensed
  source." Gated predicates are NEVER placed in the read-time composition.
- **INV-7 (campaign = composition, spine unchanged):** a campaign-compiled Segment has identical
  masking/suppression/opt-out/audit to a hand-built one; suppressed/opted-out leads stay blocked at
  search/preview/unlock/export.
- **INV-8 (cross-category):** the Utilities composition contains NO category predicate; matches leads
  spanning ≥2 categories.
- **INV-Q1 (unchanged, never weakened):** the baseline hot-gate is always enforced everywhere
  (estimate/search/unlock); a per-campaign quality profile can only NARROW on top of it, never widen.
- **INV-10 (audit):** campaign create/select/search are audited.
- Inherits **INV-1..INV-5** (tri-state absent⇒unknown⇒non-match incl. under negation; role-email
  allowlist; masking; grep; pushdown soundness). Masking / suppression / opt-out / ODbL / retention /
  compliance-ack UNCHANGED. TDD; frequent commits.

**Predicate mapping (spec name → real registered predicate):** `geo.country`→`geo.country`;
`geo.area`→`geo.city` (buyer `{area}` = a city, the pilot's granularity; no new predicate);
`firmographic.business_type`→`category.any` (group "firmographic", reads `category_keys`);
`contactability.has_business_contact`→exists (reads `phone`,`public_email`). `firmographic.independent`
and query-time `campaign_weighted` re-ranking are **DEFERRED** (see Self-Review) — not built here.

---

## File Structure
```
app/campaigns/models.py    # Campaign (lv_campaign) — OUTSIDE core
app/campaigns/crud.py      # create/update/list_active/get_by_key/get
app/campaigns/seed.py      # the 2 seeded campaigns (vertical/financial strings live HERE)
app/campaigns/compile.py   # compile_campaign(campaign, buyer_params) -> CompiledCampaign (generic)
app/quality/profiles/utilities.py   # UTILITIES QualityProfile (requires validated phone) — DATA
app/core/serve_filters.py  # passes_serve_filters(..., ctx=None) — opaque ctx (generic)
app/core/targeting/estimate.py      # estimate(..., ctx=None) threads ctx
app/quality/serve_gate.py  # quality filter: baseline always + ctx["quality_profile"] overlay (narrow-only)
app/web/routes_buyer.py + templates/composer.html + templates/campaigns.html  # selector -> compile -> populate
app/leadvault.py           # import campaigns models before init_db; seed; register utilities profile
tests/test_campaign_*.py
```

---

### Task 1: Campaign model + CRUD + seed + startup wiring + grep gate

**Files:** Create `app/campaigns/__init__.py`, `models.py`, `crud.py`, `seed.py`; Modify `app/leadvault.py`;
Test `tests/test_campaign_model.py`, `tests/test_campaign_grepclean.py`.

**Interfaces — Produces:** `Campaign` (`lv_campaign`: `id, key` unique+indexed, `name, description,
active` bool, `composition_template_json, preferred_json, scoring_profile_key, quality_profile_key,
gated_signals_json, param_schema_json` all str, `created_at`). CRUD: `create_campaign(session, *, key,
name, description, composition_template, preferred=None, scoring_profile_key="", quality_profile_key="",
gated_signals=None, param_schema=None, active=True) -> Campaign`; `list_active(session) -> list[Campaign]`;
`get_by_key(session, key) -> Campaign|None`; `get(session, id)`; `update_campaign(...)`.
`seed_campaigns(session) -> int` (idempotent upsert by key; returns count).

- [ ] **Step 1: Failing test** (`tests/test_campaign_model.py`)
```python
from sqlmodel import Session
from app.core.db import init_db
from app.campaigns.crud import list_active, get_by_key
from app.campaigns.seed import seed_campaigns

def test_seed_two_campaigns_idempotent():
    e = init_db("sqlite://")
    with Session(e) as s:
        assert seed_campaigns(s) == 2
        seed_campaigns(s)                       # idempotent
        assert len(list_active(s)) == 2
        util = get_by_key(s, "utilities_uk")
        assert util and util.quality_profile_key == "utilities"
        import json
        # Utilities composition template is cross-category (INV-8): no category predicate
        comp = json.loads(util.composition_template)
        assert not any("category" in n["predicate"] for n in comp["nodes"])
        rest = get_by_key(s, "business_restructuring")
        # Restructuring declares gated financial+size signals, never in the composition
        gs = json.loads(rest.gated_signals)
        assert set(gs) >= {"attributes.has_mca","attributes.amount_owed","attributes.lender","attributes.size_band"}
        rcomp = json.loads(rest.composition_template)
        assert not any(p in json.dumps(rcomp) for p in ["has_mca","amount_owed","lender","size_band"])
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.**
  `models.py` — `Campaign(SQLModel, table=True)` `__tablename__="lv_campaign"` with the fields above
  (json fields as `str` with `default="[]"`/`"{}"`; expose read-through `@property composition_template`
  etc. that just return the raw json string — OR name the columns `composition_template` directly). Keep
  it simple: name the string columns `composition_template`, `preferred`, `gated_signals`, `param_schema`
  and store JSON text.
  `crud.py` — the signatures above; `create_campaign` json-encodes list/dict params.
  `seed.py` — `seed_campaigns` upserts the TWO campaigns (all vertical/financial strings live in THIS
  file):
  - **utilities_uk:** name "Utilities (UK)", quality_profile_key "utilities", scoring_profile_key
    "utility_energy", gated_signals `[]`, param_schema `{"area":{"type":"city","label":"Area","help":"A UK town or city"}}`,
    composition_template =
    `{"op":"AND","nodes":[{"predicate":"geo.country","params":{"value":"GB"}},{"predicate":"geo.city","params":{"value":"{area}"}},{"predicate":"contactability.has_business_contact","params":{}}]}`.
  - **business_restructuring:** name "Business Restructuring", quality_profile_key "baseline",
    scoring_profile_key "", gated_signals `["attributes.size_band","attributes.has_mca","attributes.amount_owed","attributes.lender"]`,
    param_schema `{"area":{...},"sectors":{"type":"list","label":"Business types"}}`, composition_template =
    `{"op":"AND","nodes":[{"predicate":"category.any","params":{"in":["{sectors}"]}},{"predicate":"geo.city","params":{"value":"{area}"}},{"predicate":"contactability.has_business_contact","params":{}}]}`.
  `app/leadvault.py` — `import app.campaigns.models  # noqa` BEFORE `init_db(...)` (so the table is
  created), and after init_db + engine set, call `seed_campaigns(session)` in the same startup block that
  seeds other data (open a Session on `engine`).
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: grep gate** (`tests/test_campaign_grepclean.py`, mirror `tests/test_composer_grepclean.py`):
  assert `campaign|utilit|restructur|mca|lender|amount_owed|vertical` finds nothing in `app/core/**/*.py`.
- [ ] **Step 6: Full suite + commit** `feat(campaigns): Campaign model + CRUD + seed 2 campaigns (data, outside core) + grep gate`

---

### Task 2: Per-campaign quality profile threaded through the gate (opaque ctx)

**Files:** Modify `app/core/serve_filters.py`, `app/core/targeting/estimate.py`, `app/quality/serve_gate.py`;
Create `app/quality/profiles/utilities.py`; Modify `app/quality/runtime.py` (register it), `app/leadvault.py`;
Test `tests/test_campaign_quality_thread.py`.

**Interfaces — Produces:** `passes_serve_filters(session, buyer_account_id, lead, ctx=None)` passes the
opaque `ctx` to each registered filter (`fn(session, ba, lead, ctx=None)`). `estimate(session,
buyer_account_id, composition, sample=9, ctx=None)` threads `ctx`. The quality serve filter applies the
baseline profile ALWAYS, then — if `ctx` carries `{"quality_profile": <QualityProfile>}` — also requires
that profile (narrows only). `UTILITIES = QualityProfile(key="utilities", required={"profile":"present","phone":"validated"}, ...)`.

- [ ] **Step 1: Failing test** (`tests/test_campaign_quality_thread.py`)
```python
import json
from sqlmodel import Session
from app.core.db import init_db, Lead, _now
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.quality.runtime import register_quality_runtime
from app.core.targeting.coverage import recompute_coverage
from app.core.targeting.estimate import estimate
from app.quality.profiles.registry import get as get_profile
from tests.quality_helpers import hot_validation_json, phone_validated_json, email_only_validated_json

def _lead(s, name, val):
    l = Lead(business_name=name, category_keys_json=json.dumps(["cafe"]), city="Oxford", phone="1",
             score_total=80, date_last_verified=_now(), price_credits=3, validation_json=val)
    s.add(l); s.commit(); s.refresh(l); sync_lead_categories(s, l); return l

def test_campaign_profile_narrows_on_top_of_baseline():
    registry.clear(); register_targeting_runtime(); register_quality_runtime()
    e = init_db("sqlite://")
    with Session(e) as s:
        _lead(s, "PhoneHot", phone_validated_json())        # clears baseline AND utilities (phone validated)
        _lead(s, "EmailOnly", email_only_validated_json())  # clears baseline (email validated) but NOT utilities
        recompute_coverage(s)
        comp = {"op":"AND","nodes":[{"predicate":"geo.city","params":{"value":"Oxford"}}]}
        base = estimate(s, 1, comp)                          # ctx=None -> baseline only
        util = estimate(s, 1, comp, ctx={"quality_profile": get_profile("utilities")})
        assert base["count"] == 2                            # both clear baseline
        assert util["count"] == 1                            # utilities requires validated phone -> EmailOnly dropped
```
(If `phone_validated_json` / `email_only_validated_json` helpers don't exist in `tests/quality_helpers.py`,
add them next to `hot_validation_json`: same blob but the email-only one has the phone tier below
"validated" / absent, and the phone one has `phone: validated`. Match the real validation-blob shape the
gate reads — inspect `app/quality/gate.py` + `hot_validation_json` first.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.**
  - `app/core/serve_filters.py`: add `ctx=None` param to `passes_serve_filters`; call each filter as
    `fn(session, buyer_account_id, lead, ctx)`. Keep it generic — `ctx` is an opaque dict; core knows
    nothing of its contents (no "quality"/"profile"/"campaign" string enters core).
  - Update EVERY registered serve filter to accept `ctx=None` (grep the repo for `register_serve_filter`
    and for the filter functions — suppression/opt-out/expiry/quality — add `ctx=None` to each signature;
    they ignore it except quality).
  - `app/core/targeting/estimate.py`: add `ctx=None` to `estimate(...)` and pass it to
    `passes_serve_filters(session, buyer_account_id, l, ctx)`.
  - `app/quality/serve_gate.py`: `quality_serve_filter(session, ba, lead, ctx=None)`:
    `view = lead_view(lead); if not clears_gate(view, _active): return False` (baseline floor — always);
    `prof = (ctx or {}).get("quality_profile"); if prof is not None and not clears_gate(view, prof): return False`;
    `return True`.
  - `app/quality/profiles/utilities.py`: `UTILITIES = QualityProfile(key="utilities", label="Utilities (validated phone)", required={"profile":"present","phone":"validated"}, weights={})`. (Confirm the `required` keys the gate understands from `baseline.py` + `gate.py`; use the phone tier the gate reads.)
  - `app/quality/runtime.py`: register `UTILITIES` in the profile registry alongside baseline.
  - `app/leadvault.py`: ensure `register_quality_runtime()` registers utilities (already called at startup).
- [ ] **Step 4: Run — PASS.** Then the FULL suite (all prior INV-Q1 tests must still pass unchanged —
  ctx-default=None means baseline-only everywhere it isn't threaded).
- [ ] **Step 5: grep gate** — `grep -rinE "quality|profile|campaign" app/core/serve_filters.py app/core/targeting/estimate.py` → empty (ctx must be generic).
- [ ] **Step 6: Commit** `feat(quality): thread per-campaign quality profile via opaque ctx (baseline always enforced; narrows only)`

---

### Task 3: compile_campaign (composition + gated notices)

**Files:** Create `app/campaigns/compile.py`; Test `tests/test_campaign_compile.py`.

**Interfaces — Produces:** `compile_campaign(campaign, buyer_params: dict) -> dict` =
`{"composition": <v2 composition>, "scoring_profile_key": str, "quality_profile_key": str, "preferred":
list, "gated_notices": [{"path":str, "reason":"requires licensed source"}]}`. Substitutes `{param}`
placeholders in the template from `buyer_params` (string params in-place; a `["{sectors}"]` list slot is
replaced by the buyer's list). Gated paths → notices; NEVER added to the composition.

- [ ] **Step 1: Failing test**
```python
import json
from sqlmodel import Session
from app.core.db import init_db
from app.campaigns.seed import seed_campaigns
from app.campaigns.crud import get_by_key
from app.campaigns.compile import compile_campaign

def test_compile_utilities_and_restructuring():
    e = init_db("sqlite://")
    with Session(e) as s:
        seed_campaigns(s)
        out = compile_campaign(get_by_key(s, "utilities_uk"), {"area": "Oxford"})
        nodes = out["composition"]["nodes"]
        assert {"predicate":"geo.country","params":{"value":"GB"}} in nodes
        assert {"predicate":"geo.city","params":{"value":"Oxford"}} in nodes
        assert out["quality_profile_key"] == "utilities"
        assert out["gated_notices"] == []
        assert not any("category" in n["predicate"] for n in nodes)     # INV-8

        r = compile_campaign(get_by_key(s, "business_restructuring"),
                             {"area": "Oxford", "sectors": ["cafe","restaurant"]})
        rn = r["composition"]["nodes"]
        assert {"predicate":"category.any","params":{"in":["cafe","restaurant"]}} in rn
        paths = {g["path"] for g in r["gated_notices"]}
        assert {"attributes.has_mca","attributes.amount_owed","attributes.lender","attributes.size_band"} <= paths
        assert all(g["reason"] == "requires licensed source" for g in r["gated_notices"])
        blob = json.dumps(r["composition"])                              # INV-6: no gated field in composition
        assert not any(x in blob for x in ["has_mca","amount_owed","lender","size_band"])
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `compile.py` — parse `composition_template`, deep-substitute placeholders
  (`"{area}"`→`buyer_params["area"]`; a list containing `"{sectors}"`→`buyer_params["sectors"]`), drop any
  node whose params still contain an unfilled placeholder for an OPTIONAL param, build `gated_notices`
  from `gated_signals` (reason constant "requires licensed source"), return the dict. Generic — no
  per-campaign strings; reads only the row + params.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `feat(campaigns): compile_campaign -> v2 composition + gated notices (INV-6/INV-8)`

---

### Task 4: Campaign selector UI + routes + audit

**Files:** Modify `app/web/routes_buyer.py`, `app/web/templates/composer.html`; Create
`app/web/templates/campaigns.html`; Modify `app/web/templates/base.html` (nav). Test
`tests/test_campaign_routes.py`.

**Interfaces — Produces:**
- `GET /app/campaigns` → `campaigns.html` listing `list_active(session)` as real cards (Utilities-UK
  "Ready today"; Restructuring "Firmographic today, financial gated") → each links
  `/app/composer?campaign=<key>`.
- `GET /app/composer?campaign=<key>` (extend the existing composer route): if `campaign` present, load the
  campaign + `param_schema` so the composer shows the campaign's param inputs (area, sectors) and a
  "compiled from campaign X" banner; audit `campaign.select`. (No compile yet until params filled.)
- `POST /app/composer/apply-campaign` (buyer + csrf, JSON) `{key, params}` → `compile_campaign` →
  returns `{composition, quality_profile_key, gated_notices}` as JSON; audit `campaign.select` with the
  campaign key + a composition hash. The composer JS loads the composition (reuse the segment-preset
  rehydration), records `quality_profile_key` (hidden), and renders `gated_notices` as **"requires
  licensed source"** rows — visually DISTINCT from the coverage-0% "not available in current inventory"
  rows.
- Composer **estimate** endpoint (`POST /app/composer/estimate`): accept optional `quality_profile_key` in
  the body; if present, resolve via the quality profile registry and pass `ctx={"quality_profile": prof}`
  to `estimate(...)`. (Unknown key → ignore, baseline only — never 500.)
- Composer **save** endpoint (`POST /app/composer/save`): accept optional `origin_key` (the campaign key)
  and pass to `create_segment(..., origin_key=origin_key or "")`.

- [ ] **Step 1: Failing test** (`tests/test_campaign_routes.py`): logged-in buyer (csrf per `tests/test_csrf.py`):
  (a) `GET /app/campaigns` 200 and contains both campaign names; (b) `POST /app/composer/apply-campaign`
  `{"key":"utilities_uk","params":{"area":"Oxford"}}` → 200, JSON has `composition` with geo.city Oxford +
  `quality_profile_key=="utilities"` + `gated_notices==[]`; (c) an audit row `campaign.select` exists after
  (b); (d) `POST /app/composer/save` with `origin_key="utilities_uk"` creates a Segment whose `origin_key`
  is persisted.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** the routes + templates. `campaigns.html` uses the design system (base +
  components; cards mirroring the campaign_preview visual but REAL). Repoint the buyer nav "Campaigns"
  entry to `/app/campaigns` (drop the "Preview" badge; keep `/app/campaign-preview` reachable only if
  trivial, else remove its nav entry). composer.html: campaign param panel + apply button (fetch
  apply-campaign → rehydrate) + gated-notice rows + hidden `quality_profile_key`/`origin_key` fed into the
  estimate + save calls.
- [ ] **Step 4: Run — PASS + parse-check templates + full suite.**
- [ ] **Step 5: Commit** `feat(campaigns): selector UI + apply-campaign/estimate-profile/save-origin routes + campaign.select audit`

---

### Task 5: campaign.search audit + INV-6/7/8/10 consolidated tests + grep gate + review prep

**Files:** Modify `app/web/routes_buyer.py` (audit `campaign.search`); Test
`tests/test_campaign_invariants.py`.

- [ ] **Step 1: Audit `campaign.search`** — when a composer estimate/search runs with a non-empty
  `origin_key` (a campaign-derived segment drove it), write an `audit(..., "campaign.search", "Segment",
  ..., {...})`. (Thread `origin_key` from the loaded segment/campaign through the estimate call, or audit
  on the search that uses a saved Segment carrying `origin_key`.)
- [ ] **Step 2: INV tests** (`tests/test_campaign_invariants.py`):
  - **INV-6:** compile a composition that includes a hypothetical gated `financial.has_mca` leaf (declared
    but with NO source populating `attributes.has_mca`) → `estimate` count is 0 (tri-state unknown), and
    its negation surfaces no un-sourced lead; assert no lead view carries a non-null `attributes.has_mca`.
    (Prove no fabrication.)
  - **INV-7:** a campaign-compiled Segment and a hand-built identical composition yield the SAME estimate
    count + samples; a suppressed lead matched by the campaign composition is blocked (absent from
    estimate). Parity + compliance-block.
  - **INV-8:** the seeded Utilities composition has no `category` predicate and, on a seed of leads across
    ≥2 categories in one city, matches leads from ≥2 categories.
  - **INV-10:** `campaign.select` and `campaign.search` produce audit rows.
- [ ] **Step 3: grep gate** — `grep -rinE "campaign|utilit|restructur|mca|lender|amount_owed|vertical" app/core/` → empty (add/extend `tests/test_campaign_grepclean.py` to assert it if not already).
- [ ] **Step 4: Full suite + parse-check + grep — all green. Commit** `feat(campaigns): campaign.search audit + INV-6/7/8/10 tests + grep gate`

---

## Self-Review
**Spec coverage (locked spec §1-§13):** campaign-as-data + CRUD + seed (T1, §2); `compile_campaign`→
composition+notices (T3, §3); selector UI populating the composer, buyer-tweakable, gated notices as
"requires licensed source" (T4, §4/§7); per-campaign quality profile through the gate, baseline always
(T2 — the user's explicit ask, beyond the spec's scoring-only profile, done INV-Q1-safe); `origin_key`
provenance (T4, §3); audit create(seed)/select/search (T4/T5, §5); Utilities end-to-end cross-category
(T1/T3/T5, §6/INV-8); Restructuring firmographic with financial+size gated/never-fabricated (T1/T3/T5,
§7/INV-6); grep-clean core (T1/T5, INV-9); spine unchanged (T5, INV-7).

**Deferred — flag to the user (NOT built here), consistent with "no fake controls":**
- `firmographic.independent` (derive from `attributes.brand`): brand data is ~0% in the pilot and, under
  tri-state (absent⇒unknown⇒non-match), an independence predicate can assert almost nothing — building it
  yields a permanently-greyed control. Declared conceptually; not built. Restructuring runs on
  `category.any`+`geo.city`+`contactability` today.
- Query-time `campaign_weighted` re-ranking + `preferred` boosts: leads already carry `score_total`
  (Utilities' `utility_energy` fit was applied at ingest). Per-query re-scoring is a separate increment;
  `scoring_profile_key` is stored for provenance. Not built here — avoids dead code.
- `attributes.size_band` + `has_mca`/`amount_owed`/`lender`: GATED — declared in `gated_signals`, surfaced
  as "requires licensed source", never compiled, never fabricated (INV-6). Correctly deferred to a future
  signed-off Signal Acquisition spec.

**Placeholder scan:** backend + tests carry full code; the two UI touchpoints (T4 templates) are given by
contract (routes, JSON shapes, rehydration reuse, distinct gated-notice styling) against the shipped
design system + the composer exemplar. **Type consistency:** composition shape `{op,nodes:[{predicate,
params,negate?}]}` matches the evaluator/estimate; `ctx={"quality_profile": QualityProfile}` matches the
gate's `clears_gate(view, profile)`; `create_segment(..., origin_key=...)` matches the existing signature.

**🛑 After this plan: HARD STOP. Hand the user a working campaign-first flow to drive in front of testers.
Do NOT propose the next build phase. Payments parked.**
