# LeadVault — the data-coverage reality (UI vs data), and how broad UK coverage actually happens

**Date:** 2026-07-02. Written because "cover every UK city" is two different costs — a cheap UI cost and
a real data cost — and conflating them hides a dependency.

---

## 1. The dependency, stated plainly

**Leads exist only for areas we have ingested from OSM.** "Every UK city" is **not a UI toggle** — each
city is an **admin ingestion job**. A dropdown can never contain leads that were never pulled.

The UI is now built to be **honest about this**: the city and category options come from
`_inventory_options()` — the distinct cities and categories **actually in inventory** — and they **grow
automatically** as you ingest. Today that's what's really there:
- **Cities (10):** Bath, Berkeley Springs, Boston, Brighton, Bristol, Cambridge, Norwich, Oxford,
  Solitude, York. *(The odd ones — "Berkeley Springs", "Solitude" — are real OSM `addr:city` tags; OSM's
  city tagging is inconsistent. See §5.)*
- **Categories (19):** bakery, bar, barber_shop, butcher, cafe, car_wash, convenience_store,
  dental_clinic, dry_cleaner, fitness_studio, florist, hotel, laundromat, nail_salon, pharmacy, pub,
  restaurant, supermarket, takeaway.

So the dropdown reflects **true coverage** — never a hardcoded promise.

---

## 2. The economics of one ingestion job (measured, not guessed)

- **Overpass caps ~100 elements per query** (`out center 100`). One query per city ≈ up to **100 raw**
  businesses. (For a city with >100 matching businesses you split the query by category to go deeper.)
- **Hot yield ≈ 25% blended** — but wildly variable by area (measured on the pilot):
  Oxford 43% · Norwich 36% · Cambridge 29% · Brighton 25% · Bristol 14% · York 11% · Bath 12%.
- So **~100 raw → ~11–43 hot** depending on the area. Rule of thumb: **~4 raw per 1 hot**.
- **Overpass throttles.** After bursts we hit `406 / 429 / 504`. Pulls must be **spaced with backoff**;
  in the pilot, 7 cities took a few minutes with retries and one (Brighton) 504'd mid-run.

**Target → raw → jobs:**
| Hot leads you want | Raw needed (~4:1) | City-pulls (~100 ea) |
|---|---|---|
| ~200 (a pilot) | ~800 | ~8 cities |
| ~500 | ~2,000 | ~20 cities |
| ~1,000 | ~4,000 | ~40 city-pulls |

---

## 3. The realistic path to broad UK coverage

- **Per-region admin ingestion jobs:** a list of UK towns, one (or a few category-split) query each,
  run **politely spaced** (~5–30s apart + retry-on-throttle). ~50 towns ≈ **15–45 min** of spaced pulls;
  the whole populated UK is an **overnight batch**, not an instant.
- **To remove the throttling ceiling for real volume:** run a **self-hosted Overpass instance** (or a
  paid Overpass endpoint). Then the UK can be pulled without `429`s. That's an **infra decision**, cheap
  relative to licensed data.
- **This is admin work, not buyer UI.** The buyer never "turns on" a city; an operator ingests it, and
  it then appears in the data-driven lists.

---

## 4. The two levers — what "all the options" actually costs

| Lever | What it buys | Cost |
|---|---|---|
| **UI (data-driven options)** | Growing city/category/predicate lists that reflect real inventory | **cheap, mostly done** — shipped for the search; Plan 2 generalizes it. No data. |
| **Ingestion breadth** | More cities/areas available at all | **operator time** (+ optional self-hosted Overpass for volume). Free-ish, slow. |
| **Hot-yield per pull** | Escape the ~4:1 ratio + thin-coverage areas | **licensed contact-coverage source** (deferred Signal Acquisition) — the real spend, gated behind demand. |

The thin-coverage areas (York/Bath ~11%) are a **data limit, not a pull limit**: pulling them 10× more
still yields few hot leads, because OSM simply lacks published phones there. Only a contact source fixes
that — and that's the spend to justify *after* the pilot shows demand.

---

## 5. Honest data-quality note (OSM `addr:city`)

OSM's `addr:city` tag is inconsistent — some businesses tag a suburb, a historic parish, or (rarely) a
wrong value, which is why the live city list shows a few oddities. The **Targeting v2 composer** can
normalize this (geo predicates on `city`/`region` with cleanup, or radius-around-a-point which sidesteps
city tags entirely). Flagging it so the messy list isn't mistaken for a bug — it's real, unnormalized
OSM data surfacing honestly.

---

## 6. Requirements this locks in for Targeting v2 Plan 2 (the composer)

When wired (on your approval), the composer must:
1. **Be data-driven** — every option (cities, categories, predicates) comes from the registry + the
   `lv_attribute_coverage` rollup of what's actually populated in inventory; lists grow as you ingest;
   no hardcoded dropdowns. (Already the pattern for the shipped search; Plan 2 generalizes it.)
2. **Guided by default, advanced on demand** — campaign-first picks smart defaults (pick campaign →
   area → go, few controls). An **"Advanced" view** exposes the full option set (every predicate, every
   present city/category, quality tiers) for manual control. **Both** — never dump every control on one
   screen, never hide the full set from power users.
3. Keep the honesty spine: masking, quality gate, ODbL, Validated-tier labelling, grep-clean core.

**Payments parked. Composer wiring waits for your approval.**
