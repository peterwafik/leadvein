# LeadVault — UI overhaul + campaign-first build sequence

**Date:** 2026-07-02
**Status:** honest roadmap. Deliverable 1 (design system + working guided search) is REAL and shipped.
Deliverables 2 (campaign-first flow) is a **design preview** at `/app/campaign-preview`, wired to no
engine. This doc is the sequence that turns the preview into a working flow — **in the right order,
never fake controls in front of a missing engine.**

---

## 1. What is actually built today (engine reality)

| Layer | State | Engine |
|---|---|---|
| Baseline search (marketplace) | ✅ **live** (now redesigned, plain-language) | `recipes.matching_leads` → `marketplace.search` + the quality serve-gate |
| Lead quality gate | ✅ **built + wired** | validators/tiers/`clears_gate` + `serve_filters` at search/preview/unlock |
| Targeting v2 **engine** (Plan 1) | ✅ **built** | `lead_view`, predicate registry, tri-state evaluator, two-stage matcher, `Segment` CRUD, `estimate()` |
| Targeting v2 **composer UI** (Plan 2) | ⛔ spec | — (the UI that drives the built engine; **not built**) |
| Campaign layer | ⛔ spec (locked) | `compile_campaign` → composition + profile; **not built** |
| Signal Acquisition / new providers | ⛔ deferred specs | financial / size / verified-live sources; **not built** |

**The key fact for the UI:** the Targeting v2 **engine is done**, but it has **no UI**. That gap — not
the Campaign layer — is the natural next real build.

---

## 2. The preview's 5 steps → which engine each control needs

| Preview step | Control | Engine it needs | Buildable now? |
|---|---|---|---|
| 1 · Pick campaign | campaign cards / describe | **Campaign layer** (`lv_campaign` + `compile_campaign`) | ❌ spec only |
| 2 · Guided targeting | predicate toggles/chips, availability | **Targeting Plan 1 engine (✅) + Plan 2 composer UI + coverage rollup** | ⚠️ engine ✅, **UI not built** |
| 3 · Quality bar | tier toggles, gated locks | quality gate (✅) + per-campaign profile selection | ⚠️ gate ✅, per-campaign selection needs the Campaign layer |
| 4 · Estimate | count + distributions | `targeting.estimate()` (✅) | ✅ engine ready |
| 5 · Results + Save segment | masked cards, save | `matching_by_composition` (✅) + `Segment` CRUD (✅) + masking/gate (✅) | ✅ engine ready |

The greyed "requires a licensed source" items (company size, newly-registered, verified-live email,
direct mobile, MCA/debt) map to **Signal Acquisition** — separate, sign-off-gated specs. They stay
locked in the UI until a lawful provider lands. Never stubbed.

---

## 3. The build sequence (do these in order)

### Increment A — **Targeting v2 Plan 2: the data-driven composer UI** ← wire this FIRST
The Plan-1 engine already evaluates compositions, estimates, and saves Segments. Plan 2 is the UI that
drives it. It delivers preview **Steps 2, 4, 5** for **hand-built segments** (not yet campaign-driven):
- A composer that renders predicate controls **from the registry**, showing only predicates whose
  signals are populated in current inventory (the `lv_attribute_coverage` rollup — part of Plan 2).
- Live **estimate** (count + score/freshness distributions + masked samples) via the built `estimate()`.
- **Save / load Segments** via the built `Segment` CRUD; results are masked hot cards via the built
  `matching_by_composition` + the quality gate.
- **No fake controls:** every control maps to a registered predicate with a real evaluator behind it;
  predicates without populated signals are shown disabled with an honest "needs source X" note.
- Discipline: grep-clean core, masking/quality/compliance untouched, INV-1..INV-5 hold, tests per task.

### Increment B — **Campaign layer** (build the locked spec)
On top of a live composer, build `lv_campaign` + `compile_campaign`. This delivers preview **Step 1**
(pick/describe a campaign) and **Step 3** (per-campaign quality profile) by **auto-populating the
composer** the buyer can still tweak. Seeds the two campaigns (Utilities-UK live; Restructuring
firmographic, financial fields locked). Depends on Increment A.

### Increment C — **Signal Acquisition + predicate packs** (each its own gated spec)
Unlocks the greyed items: company size/age (Companies House), verified-live email/phone (a verifier),
association/directory sources, and — behind the compliance-owner gate — financial-distress data. Each
lands as a provider that populates an attribute the existing predicates then read. No people-data or
financial scraping without a lawful basis + sign-off.

---

## 4. What ships now vs waits

- **Now (real, Deliverable 1):** the whole app is on a coherent design system; the baseline search is
  polished, plain-language, guided, with honest empty states — real leads, real quality gate, ODbL.
- **Now (preview, Deliverable 2):** the campaign-first flow as a click-through mock at
  `/app/campaign-preview`, clearly labelled "design preview, not yet live", gated signals locked.
- **Next real wire:** Increment A (Targeting Plan 2 composer) — engine exists, so it's honest to build.
- **After that:** Increment B (Campaign layer), then C (providers), each on your go.

I will **pause after showing you Deliverables 1–3** and not start Increment A until you approve the
destination. Payments stay parked.
