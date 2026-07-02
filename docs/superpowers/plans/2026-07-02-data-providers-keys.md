# Data Providers — Keys to Get, Free Limits, ToS, Coverage (HONEST REPORT)

**Date:** 2026-07-02. **Status:** action list for the operator + honesty record. Limits are **as of my
knowledge and change often — verify current terms on each provider's pricing/ToS page before relying on
them.** Nothing here claims "every business." No provider is scraped; all are API-key based.

---

## 1. Get these keys (priority order), put each in `.env`, never in chat

| # | Provider | `.env` var | Free tier (verify!) | Regions | What it supplies | Notes |
|---|---|---|---|---|---|---|
| 1 | **Companies House** | `LEADVAULT_COMPANIES_HOUSE_KEY` | **Free, unlimited** (~600 req / 5 min) | UK | Company existence, registered address, **SIC industry, incorporation date, status** | Official UK gov registry. Biggest lever beyond OSM for UK coverage + firmographics. **Company fields only — NOT director personal data.** No phones/emails. |
| 2 | **Hunter.io** | `LEADVAULT_HUNTER_KEY` | ~25 domain searches + 50 verifications / mo | UK+US+global | **Role-based** business emails by domain, email verification | We keep **only role-based** emails (info@/sales@…, INV-2 allowlist); personal emails discarded. Small cap → credit budgeting matters. |
| 3 | **Foursquare Places** | `LEADVAULT_FOURSQUARE_KEY` | Monthly free credit | US + global | POI business (name, address, category, some phone/website) | Storage terms more permissive than Google/Yelp. Best free-ish **US business coverage**. |
| 4 | **People Data Labs** | `LEADVAULT_PDL_KEY` | ~100 enrichments / mo | Strong US, global | Company (+ person) enrichment | Person data → people-data gate; take **company + role-contact** only. Verify storage/resale rights. |
| 5 | Apollo.io | `LEADVAULT_APOLLO_KEY` | Limited credits | US-heavy | Contacts (person-heavy) | 🚩 **Verify free-tier API export rights + GDPR** before enabling. Person-contact-heavy. |

**Zero keys = fine.** With no keys set, every external adapter is **disabled** (Stripe disabled-mode
pattern) and the app runs on OSM alone. Each source **lights up** the moment you add its key.

## 2. 🚩 Do NOT build on these (ToS forbids it) — flagged, not wired

- **Google Places** — ToS **prohibits caching/storing** most Place fields; you cannot lawfully build a
  stored lead DB from it.
- **Yelp Fusion** — storage/caching restricted + display requirements.
- **LinkedIn** — no scraping; no compliant API for lead building.
These are represented (if ever added) with `terms_status="restricted"` and refuse to run.

## 3. Where the paid line is (what eventually costs money at volume)

- **Companies House:** stays free (rate-limited). No paid line for the data itself.
- **Hunter:** ~$34+/mo past the tiny free tier (500+ searches).
- **Foursquare:** usage-based past the monthly free credit.
- **PDL / Apollo:** credit packs / ~$49–$99+/mo past free credits.
- **The real money at scale** is contact enrichment volume (Hunter/PDL/Apollo) and any **US firmographic
  source** (no free national US registry exists). UK firmographics stay free via Companies House.

## 4. Realistic coverage (no "every business")

- **UK:** Companies House ≈ comprehensive for **registered companies** (~5M), but **misses unregistered
  sole traders**; OSM adds POI-level SMBs. Contact (phone/email) coverage stays partial.
- **US:** **no free national registry** → coverage leans on Foursquare POI + PDL + OSM = **materially
  thinner than UK** until a paid US source. Be honest with buyers about US coverage.
- **Contact data decays:** industry reality ~50% accuracy, ~22.5%/yr decay. Enrichment improves the odds;
  it never guarantees a live contact. The quality gate still decides "hot" — an enriched-but-unvalidated
  phone is not "hot" until it clears validation.

## 5. US compliance gate (REQUIRED before any US outreach data is marketable)

US phone outreach is governed by **TCPA** + the **national DNC registry** + **state DNC / mini-TCPAs**
(FL/OK/WA…), with statutory damages. Therefore:
- US-region leads are stamped a **compliance flag: "requires DNC-scrub + TCPA-consent gate before
  outreach."**
- **US outreach data is NOT enabled** until a DNC-scrub step + TCPA-consent handling are built and signed
  off (spec'd in `2026-07-02-us-expansion.md`). Until then US-sourced contact leads are held from sale.
- This mirrors the financial-data gate: a lawful-basis + sign-off gate, enforced, not advisory.

## 6. How the capability keeps the honesty spine

- **Waterfall, not overwrite:** OSM is the free base; source adapters fill **missing businesses**;
  enrichment adapters fill **missing/unverified** phones/role-emails only. Better existing data is never
  overwritten by worse.
- **Per-field provenance + license:** every field records which adapter supplied it + under what license,
  so ODbL (OSM) and each provider's terms are attributed per field.
- **Gate unchanged:** masking, the quality gate (INV-Q1), suppression/opt-out, ODbL, and audit apply to
  externally-sourced leads **exactly** as to OSM leads. An enriched phone is "hot" only after it clears
  validation under the lead's country region.
- **No fabrication:** adapters return real API values or nothing; no inferred/placeholder contacts. Role-
  email allowlist filters out personal data; Companies House officer PII is not ingested.
- **Rate + credit budget:** each adapter respects its provider's rate limit and free-tier cap, tracks
  usage, and **stops before overrunning** — no surprise bills. Admin shows remaining free credits.

---

**This is capability + honesty, not a US launch and not "every business."** Get the keys worth it to you
(start with Companies House — free), and the UK utilities demand test still stands as the real gate.
