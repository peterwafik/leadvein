# US / Multi-Country Expansion — Honest Plan (DECISION DOC, NOT A BUILD)

**Date:** 2026-07-02
**Status:** 📋 **Decision material.** Nothing here is built or scheduled. US is **not available** in the
product and must not be treated as built until you decide from this doc. The **UK utilities demand test
remains the next real gate**; US is a separate market-entry choice that should follow real UK demand, not
precede it.

---

## 1. What "country-agnostic" already bought you (shipped)

The refactor removed the UK-hardcoding so the US *can* slot in cleanly later — **capability only, no US
data**:
- **Phone-validation region is configurable** — derived from the lead's `country` (env-overridable
  default `GB`). A US number now validates under `US` instead of failing as `GB`.
- **First-class multi-value geo predicates** — `geo.country_any` / `geo.region_any` (region = **US
  state**) / `geo.city_any`. State is already a first-class targeting field.
- **Ingestion stamps country from the pull context** — a US-area pull would stamp `US` even where OSM
  lacks the tag.

**This is the plumbing, not a launch.** No US area has been ingested; there is no US campaign, no US
option in the UI, and no measured US yield.

---

## 2. The straight truth about a US launch today

If someone flipped on a "US states" dropdown right now, it would return **zero usable leads** and you'd be
flying blind, because:
- **Yield is unmeasured for the US.** The ~4:1 raw→hot ratio (25% blended, 11–43% by city) is a **UK OSM**
  measurement. US OSM business coverage — and especially **published-phone density** — is different and
  **unknown**. It must be measured, not assumed.
- **The "hot" signal is UK-calibrated.** The quality gate's tiers, the phone line-type logic, and the
  scoring were all validated on UK data. US phone formats validate now, but the *bar* ("a validated
  published phone = hot") needs re-checking against real US inventory.
- **The only campaign is UK utilities.** There is no US campaign or US quality profile.

So the honest position: **the architecture is ready; the market is not measured; and compliance is
materially different (below).** A US dropdown before those three are done would be exactly the
"dropdown that returns zero validated leads" you said you don't want.

---

## 3. Compliance — the part that actually gates the US (the important part)

US cold B2B outreach is **more regulated than the UK**, and phone (your hot channel) is the riskiest part.
Treat this like the financial-data gate: **a documented review + sign-off before any US ingest or sale**,
not an afterthought.
- **TCPA (Telephone Consumer Protection Act):** governs calls/texts, esp. to **mobile** numbers and
  autodialed/prerecorded calls; **statutory damages ($500–$1,500 per violation)**. B2B has narrower
  carve-outs than many assume; SMS and mobile calling are high-risk.
- **National DNC registry + state DNC lists:** the tool would need DNC scrubbing for phone outreach; some
  states (e.g. **Florida, Oklahoma, Washington** "mini-TCPAs") add stricter rules and their own damages.
- **CAN-SPAM** for email (opt-out, honest headers) — lighter than PECR/GDPR but still binding.
- **State privacy laws** (CCPA/CPRA in California, plus a growing patchwork) — relevant when a
  **sole-trader** is the business (the individual is personal data), same principle as the UK people-data
  gate.
- **Line-type matters:** mobile vs fixed-line changes the TCPA risk profile — the validator already
  detects line type, which becomes a **compliance input**, not just a quality signal, in the US.

**Implication:** a US launch needs a real compliance owner sign-off covering TCPA/DNC/state law + a
DNC-scrub step in the serve/unlock path, **before** US leads are sold. This is a gate, not a checkbox.

---

## 4. What a real US launch would actually require (the work, if you decide yes)

In honest order — each step informs whether the next is worth it:
1. **Measure US OSM yield (a US "survival" run).** Pull a few representative US metros (e.g. Austin,
   Columbus, a rural county), run the *existing* gate, and report raw→hot, phone-coverage %, and per-area
   variance — the same decision-grade output we produced for the UK. **Answers: is there enough
   contactable inventory to bother?** (Uses the shipped `AdapterQuery.country` + region validator; still
   an operator ingest job, subject to Overpass throttling.)
2. **Compliance review + gate (§3).** TCPA/DNC/state analysis + a DNC-scrub in the serve path + compliance
   sign-off. **Gates whether US phone leads can be sold at all.** Likely the long pole.
3. **A US campaign + quality profile.** e.g. "Utilities (US)" (or a chosen US vertical) compiling to
   `geo.country_any{US}` + `geo.region_any{states}` + contact, with a US quality profile (validated US
   phone, line-type-aware for TCPA). Data only — no core change, per the campaign architecture.
4. **A single-metro US pilot.** Measure real contact rates + buyer demand in one US market before broad
   coverage — mirroring the UK utilities pilot discipline.

**Cost shape:** step 1 is operator time (+ Overpass/self-host); step 2 is legal/compliance effort (the
real gate); steps 3–4 are small once 1–2 clear. Broad US state coverage is then an **ingestion-breadth**
cost (per-metro pulls), same lever as the UK — and higher **hot-yield** still depends on a licensed
contact source, which for the US is its own vendor + compliance question.

---

## 5. What stays true regardless

- **US is not built and not available** until you decide from this doc. No US data, no US options, no US
  campaign exist today.
- **The UK utilities demand test is the current gate.** US should follow *proven UK demand* — spending
  legal + ingestion effort on the US before the UK pilot shows buyers want the product would be
  out of order.
- Deciding "yes" on the US is a **market-entry choice** (yield + compliance + demand), yours to make —
  not a feature toggle. This doc is so you can make it with real costs in front of you.

**No build follows this doc automatically. Payments parked.**
