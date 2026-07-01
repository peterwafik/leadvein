# LeadVault — Per-Campaign Lead Quality Gate (Design Spec)

**Date:** 2026-07-01
**Status:** SPEC ONLY — for review. **Do NOT build yet.** Payments are PARKED; this is the priority for
the test phase, to be built before anything payment-related.
**Extends:** `2026-06-30-targeting-segmentation-design-v2.md` (Targeting v2) and
`2026-07-01-campaign-layer-design.md` (Campaign layer). Reuses their machinery (normalized view, tri-state
rule, masking/suppression/opt-out/audit spine, scoring-profile pattern). No parallel engine.
**Scope:** a per-campaign **Lead Quality Gate** — a lead is only surfaced/previewable/unlockable if it
**clears the campaign's declared quality gate**. Incomplete or unverified leads are **held back, not
sold**. Quality is **tiered and honest** (Present / Validated / Verified-live), using the existing
tri-state rule (unknown ≠ verified). No stubbed, inferred, or placeholder contacts, ever.

---

## 1. Goal

"Hot lead" becomes a **system-enforced** property, not a hope. Each Campaign declares its **required
fields + the tier each must reach**; the pipeline validates what it lawfully can, stamps an honest tier
per field, and the gate holds back any lead that doesn't meet the campaign's bar — at search, masked
preview, and unlock. Different campaigns demand different sets (Utilities-UK ≠ Restructuring).

---

## 2. Tiers (honest, tri-state)

Per field, an **achieved tier** — strictly ordered `absent < present < validated < verified_live`:

- **Present** — the field exists and is non-empty on the record.
- **Validated** — it passed an **automated** check we can run ourselves (details §4). Validation is a
  fact about form/plausibility/reachability, NOT a guarantee the mailbox/line is live.
- **Verified-live** — confirmed actually working/monitored. **Only** from a licensed verification
  provider or human confirmation (§7). We cannot produce this today.

**Tri-state honesty (INV-1 inherited):** an unchecked or absent field is **unknown**, never silently
"validated." A field's achieved tier is only what we can prove. A gate requiring a tier we can't reach
for a field ⇒ that lead **does not clear** (held back) AND the field renders **"requires
verification/enrichment provider — not yet available"** — never a fake value.

---

## 3. Where the gate hooks in

1. **Ingestion (validate + stamp).** After enrich, a **validation pass** runs the automated checks we
   can do (§4) and stamps a per-field `validation` blob + a generic completeness/validation score on the
   lead. Campaign-independent (email is validated-or-not regardless of who queries).
2. **Read-time gate (per campaign).** `clears_gate(lead_view, quality_profile) -> bool` checks each of
   the profile's required fields has `achieved_tier >= required_tier`. Only cleared leads are:
   - **surfaced** in `marketplace.search` / Segment search (held-back leads never appear),
   - **previewable** (`estimate`/masked cards only show cleared leads),
   - **unlockable** (defense-in-depth: `unlock_lead` re-checks the lead clears the campaign profile in
     context; a held-back lead cannot be bought even by direct id).
3. The **compliance spine is unchanged** — masking, suppression/opt-out, retention, audit all still
   apply; the quality gate is an ADDITIONAL held-back filter layered on top, server-enforced.

---

## 4. Field validation — what "Validated" means, and what's NOW vs GATED

**Legend:** **NOW** = we can do it with free/offline tooling today · **GATED** = needs a licensed
provider (§7) · we NEVER SMTP-probe mailboxes (unreliable, reputation-risky, intrusive) — mailbox-level
deliverability is Verified-live only.

| Field | Present (today) | Validated (what we CAN check now) | Verified-live (GATED) |
|---|---|---|---|
| **Business email** (`public_email`) | OSM `email`/`contact:email` — **published role inbox** | **NOW:** RFC syntax + **MX record exists** (dnspython, already installed) + **not a disposable domain** (free blocklist) + role-prefix flag (INV-2). = "well-formed, domain accepts mail, not throwaway." NOT "inbox is live." | mailbox exists + monitored — **provider** (NeverBounce/ZeroBounce/Kickbox/Bouncer) |
| **Business phone** (`phone`) | OSM `phone`/`contact:phone` — **published line** | **NOW:** valid format per country + **line-type where the numbering plan reveals it** (`phonenumbers`, Google libphonenumber — offline metadata). = "valid, plausibly mobile/landline." NOT "line is live." | line active/reachable + carrier/HLR — **provider** (Twilio Lookup / Vonage Number Insight / Telesign) |
| **Direct mobile** (decision-maker) | — **not available** (OSM never has personal mobiles) | — not derivable | **GATED + people-data gate** — provider (Cognism/Lusha/Kaspr/Apollo) under the §11 personal-data gate |
| **Address** (`address_*`, lat/lon) | OSM address tags (coverage varies) | **NOW:** normalize + **geocode-match** (OSM node already carries lat/lon; else Nominatim, ODbL, rate-limited) + postcode-format per country. = "locatable." NOT "occupied/deliverable." | postal deliverability/occupancy — **provider** (Loqate/GBG, Melissa, Smarty) |
| **Website** (`website_url`) | OSM `website` | **NOW:** **reachable + SSL** (already stamped by enrich: `intent.website_reachable`, `intent.ssl`). | uptime-monitored — provider/monitor |
| **Business profile** (name, category, location, hours) | OSM name/category/city/opening_hours | **NOW:** present-and-consistent (category ∈ taxonomy, location resolves, hours parse). | — |
| **Company size / age** | — not available | — not derivable now | **GATED** — Companies House (UK, free/official for registered cos) or firmographic provider (D&B/Clearbit) |
| **Freshness** | `date_discovered` | **NOW:** `date_last_verified` recency band. | continuous re-verification — provider/monitor |

**NEW deps for the NOW Validated tier:** `phonenumbers` (Apache-2.0, offline). `dnspython` (already
installed) for MX. `email`/regex (stdlib) for syntax. Nominatim reuse (HTTP, like Overpass) for geocode.
**No paid provider, no SMTP probing.**

---

## 5. Per-campaign Lead Quality Profile (data/profile, not core)

A **Quality Profile** declares the required fields + tier + weights — reusing the scoring-profile pattern
(pluggable, data-driven; lives in `app/quality/profiles/` or attached to a Campaign row, NEVER in core):

```
QualityProfile:
  key, label,
  required: { <field>: <min_tier> },        # e.g. {"phone":"validated","email":"validated",
                                             #       "address":"validated","business_profile":"present"}
  weights:  { <field>: <int> },              # for the completeness+validation quality score
  # "hot" = every required field's achieved_tier >= its min_tier
```

- `clears_gate(lead_view, profile) -> bool`: all required fields meet their tier (tri-state: unknown/
  absent ⇒ does NOT meet ⇒ held back).
- `quality_score(lead_view, profile) -> int`: weighted completeness+validation, for ranking within the
  cleared set (feeds/extends the existing `completeness`/`contactability` subscores).
- A **Campaign** references a `quality_profile_key`; the campaign's compiled Segment carries it. A
  hand-built Segment can attach one, defaulting to a baseline profile
  (`business_contact.present + business_profile.present`).

**Adding a campaign's quality bar = adding data/a profile, never touching `app/core`.**

---

## 6. Data model

- **Lead validation stamp** (at ingest): a `validation_json` blob on `Lead` (or folded into `attributes`)
  exposing per-field tiers to the normalized view as dotted paths:
  ```
  validation = {
    "email":  {"tier":"validated","syntax":true,"mx":true,"disposable":false,"role":true},
    "phone":  {"tier":"validated","format_ok":true,"line_type":"mobile"},
    "address":{"tier":"validated","geocoded":true},
    "website":{"tier":"validated","reachable":true,"ssl":true},
    "business_profile":{"tier":"present"}
  }
  ```
  `lead_view` surfaces `validation.email.tier`, etc. `verified_live` only ever appears if a §7 provider
  stamped it. Absent field ⇒ path absent ⇒ unknown (tri-state).
- **Quality score** persisted per lead for a default profile; recomputed per campaign at read-time.
- **QualityProfile**: `app/quality/profiles/` (code, no vertical strings) + a `quality_profile_key` on
  the `Campaign`/`Segment` (data).

---

## 7. The gated "Verified-live" + direct-mobile slot (clean, unbuilt)

Verified-live tiers and personal direct-mobile are populated ONLY by a licensed provider, added as a
**gated Signal Acquisition / verification source** (Targeting v2 §12), under the SAME compliance gate as
any source: source/license/`lawful_basis` metadata, opt-out/suppression coverage, buyer compliance
acknowledgement, and — for personal data (direct mobiles, sole-trader data) — the people-data gate
(v2 §11) + compliance-owner sign-off. Until licensed:
- Verified-live tiers are never reached; gates requiring them surface zero leads (honest).
- Direct-mobile and monitored-inbox fields render **"requires verification/enrichment provider — not yet
  available."** No stub, no inference.

Provider slots (named for your decision, none built): **phone** → Twilio Lookup / Vonage / Telesign;
**email** → NeverBounce / ZeroBounce / Kickbox / Bouncer; **direct dials (personal, gated)** → Cognism /
Lusha / Kaspr / Apollo; **address** → Loqate / Melissa / Smarty; **firmographic size/age** → Companies
House (UK, free) / D&B / Clearbit.

---

## 8. Honesty boundary (non-negotiable) & compliance guarantees

- **No faking.** Fields we can't fill/verify are never stubbed, inferred, or guessed — they render the
  "not yet available" notice. Validation results are facts we can prove, honestly tiered.
- **No SMTP mailbox probing** for the NOW tier (unreliable, reputation-risky). Mailbox deliverability is
  Verified-live (provider) only.
- **Grep-clean core:** validators + quality profiles + gate machinery live under `app/quality/` and
  `app/campaigns/`; core keeps only generic pieces (the tri-state rule, masking, spine). No
  quality/vertical/provider strings in `app/core`.
- **Masking/suppression/opt-out/audit unchanged.** The gate only narrows what's surfaced; everything
  downstream is the existing server-enforced spine. Audit records gate outcomes at campaign search.

---

## 9. The two seeded campaigns' quality profiles (illustrative)

- **Utilities (UK):** `required = { business_profile: present, address: validated,
  business_contact: validated }` where `business_contact` = phone **or** role-email at Validated. **Fully
  shippable now** — every required tier is reachable with the NOW validators. Direct-mobile is NOT
  required (would gate to zero). Result: hot = a real UK business, in-area, locatable, with a
  format-valid published phone or MX-valid role email.
- **Business Restructuring:** `required = { business_profile: present, address: validated,
  business_contact: validated, firmographic.independent: present }`; **size band + MCA/debt/lender are
  declared but at `verified_live`/GATED** → not required today (or the campaign surfaces zero until a
  licensed source lands), never faked. Runs on firmographic + validated-contact today.

---

## 10. Module layout (extends prior specs)

```
app/quality/
  validators/  email.py phone.py address.py website.py profile.py   # NOW checks (free/offline)
  tiers.py         # tier ordering + achieved-tier resolution from the validation blob (generic)
  gate.py          # clears_gate(view, profile) + quality_score(view, profile) (generic)
  profiles/        # QualityProfile definitions (pluggable, like scoring profiles)
  runtime.py       # register quality profiles
app/ingestion/pipeline.py   # + validation pass (stamp validation_json + score) after enrich
app/core/db.py              # + Lead.validation_json (+ quality_score)
app/campaigns/…             # Campaign.quality_profile_key (data)
app/core/marketplace.py + purchasing.py   # apply clears_gate at search/preview/unlock (spine unchanged)
app/core/… (targeting)      # UNCHANGED generic engine; no quality/provider strings
```

---

## 11. Invariants & test obligations (extend prior specs)

- **INV-Q1 (held-back, not sold):** a lead missing a required field, or below the required tier, does
  NOT appear in search/estimate and CANNOT be unlocked under that campaign. **Test:** a lead with an
  unvalidated/absent required field is absent from search and `unlock_lead` refuses it.
- **INV-Q2 (no fabrication):** fields we can't fill/verify are never stamped with a value; they read the
  "not yet available" notice; no `verified_live` tier exists without a §7 provider. **Test:** with no
  provider, no lead carries `verified_live`; direct-mobile is empty + flagged, never a placeholder.
- **INV-Q3 (honest Validated tier):** email `validated` requires syntax+MX+not-disposable (no mailbox
  claim); phone `validated` requires format+line-type metadata (no live claim). **Test:** an MX-less or
  disposable-domain email is NOT `validated`; a malformed number is NOT `validated`; a valid UK mobile is
  `validated` with `line_type=mobile`.
- **INV-Q4 (tri-state tiers):** absent field ⇒ unknown ⇒ does not meet any required tier. **Test.**
- **INV-Q5 (grep-clean core):** no quality/provider strings in `app/core`. **Test:** grep gate.
- **INV-Q6 (never SMTP-probe; honest "Validated" over false "Verified" — PERMANENT):** the platform MUST
  NEVER perform SMTP mailbox probing — or any equivalent intrusive liveness hack — to manufacture a
  "Verified" tier. Not now, not later, not as a shortcut, not even if it looks free. Mailbox/line
  liveness is **Verified-live ONLY** via a licensed provider or human confirmation. An honest "Validated"
  always beats a fabricated "Verified." This is a standing rule and survives context resets. **Test:** the
  email validator opens NO SMTP connection; no code path stamps `verified_live` from a self-run probe.
- Inherits INV-1..INV-10 from the prior specs (tri-state, role-email allowlist, masking, grep, campaign).

---

## 12. Build sequencing

- Payments PARKED. Build order: pilot infra as needed → **Targeting v2 engine (Plan 1)** → **Campaign
  layer** → **Lead Quality Gate** (this spec). The gate depends on the Targeting/Campaign machinery, so it
  builds on top of them.
- **Quality-gate plan (single, focused):** validators (`email`/`phone`/`address`/`website`/`profile`) +
  `tiers` + `gate` + a baseline + the two campaign quality profiles + the ingestion validation pass +
  `Lead.validation_json`/`quality_score` + wiring `clears_gate` into search/preview/unlock + INV-Q1..Q5
  tests. Add deps: `phonenumbers`.
- **Deferred (separate, gated specs):** each Verified-live/enrichment provider (§7) — its own
  lawful-basis review + sign-off before any code; personal direct-mobile providers behind the people-data
  gate.

---

## 13. Acceptance criteria (for the eventual build, not now)

1. Ingestion stamps an honest per-field validation tier + score using only NOW validators; no SMTP
   probing; grep-clean core (INV-Q5).
2. `clears_gate` holds back leads below a campaign's required fields/tiers at search, preview, and unlock
   (INV-Q1); the compliance spine is unchanged.
3. No field is ever stubbed/inferred; unreachable tiers/fields render "requires verification/enrichment
   provider — not yet available" (INV-Q2); Validated tier is honestly scoped (INV-Q3); tri-state holds
   (INV-Q4).
4. Utilities-UK ships fully hot on current sources; Restructuring ships firmographic + validated-contact,
   with financial/size fields gated and never faked.
5. Per-campaign quality profiles are pluggable data/profiles; a new bar = data, no `app/core` change.
```
