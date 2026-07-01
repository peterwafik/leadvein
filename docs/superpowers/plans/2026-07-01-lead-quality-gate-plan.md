# Lead Quality Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> ⛔ **PAUSE AFTER WRITING — do NOT execute until the user reviews this plan.** Payments stay parked.
> Builds on the finished Targeting v2 engine (`01181b1..36c4900`). Spec:
> `docs/superpowers/specs/2026-07-01-lead-quality-gate-design.md`.

**Goal:** Only genuine, complete, campaign-matched **hot** leads are surfaced/previewable/unlockable. A
lead below a quality profile's required fields/tiers is **held back** at search, preview, AND unlock —
server-enforced. Quality is honestly tiered (Present/Validated/Verified-live), tri-state, never
fabricated, and NEVER SMTP-probed.

**Architecture:** Validators + tiers + gate + profiles live in `app/quality/` (grep-clean core). The
ingestion pipeline stamps an honest per-field validation blob + quality score. A **generic serve-filter
registry** in `app/core/` (no "quality" string) lets `app/quality` register a gate that
`marketplace.search`, the targeting `estimate`, and `purchasing.unlock_lead` all consult — so the gate is
enforced on all three paths without core naming quality. Masking/suppression/opt-out/retention/audit
unchanged.

**Tech Stack:** Python 3.11 (`.venv/Scripts/python`); FastAPI/SQLModel; `dnspython` (installed, MX),
`phonenumbers` (new); pytest. Reuses `app.core.targeting.view.lead_view`, `mask_preview`,
`marketplace.search`, `purchasing.unlock_lead`, ingestion `pipeline.ingest`.

## Global Constraints

- Interpreter `.venv/Scripts/python`; tests `.venv/Scripts/python -m pytest`. Bash for git; no `cd`. Do
  NOT commit `*.db`. Before a full-suite run: `rm -f leadvault.db leadscraper.db`.
- **INV-Q1 (held-back-not-sold):** a lead missing a required field OR holding an unknown-tier value is
  NOT surfaced at **search**, NOT in **preview/estimate**, and CANNOT be **unlocked** — all three,
  server-enforced. Failing-first test on all three paths REQUIRED.
- **INV-Q2 (no fabrication):** with no licensed provider, gated fields (`has_mca`/`amount_owed`/`lender`/
  `size_band`) are never stamped; a filter on them is tri-state unknown ⇒ non-match; no `verified_live`
  tier is ever produced by a self-run check. Test REQUIRED.
- **INV-Q3 (honest Validated):** email `validated` = syntax + MX + non-disposable (no mailbox claim);
  phone `validated` = valid format + line-type (no live claim). Test REQUIRED.
- **INV-Q4 (tri-state tiers):** absent field ⇒ unknown ⇒ meets no required tier (incl. under negation).
- **INV-Q5 (grep-clean core):** no `quality|energy|utility|osm|overpass|campaign|provider|mca|lender`
  strings in `app/core`. Concrete quality logic lives in `app/quality`. The serve-filter hook in core is
  generic. Test REQUIRED (grep gate).
- **INV-Q6 (NEVER SMTP-probe — PERMANENT):** no code path opens an SMTP connection or otherwise probes a
  mailbox to manufacture a "Verified" tier — not now, not ever. Verified-live only via a licensed
  provider/human. Test REQUIRED (email validator source contains no `smtplib`/`SMTP`; validation does no
  network beyond the injectable MX lookup).
- Honest "Validated" over false "Verified" is a standing rule. Fields we can't fill/verify render "not
  available — requires verification/enrichment provider," never stubbed.

---

## File Structure

```
app/quality/
  __init__.py
  validators/  __init__.py email.py phone.py address.py website.py profile.py freshness.py
  tiers.py       # TIER_ORDER + achieved_tier(field_blob)  (generic, in app/quality)
  stamp.py       # build_validation(ctx) -> blob + quality_score(blob, weights)
  gate.py        # clears_gate(view, profile) + profile_score(view, profile)
  profiles/  __init__.py base.py baseline.py registry.py
  serve_gate.py  # registers a serve filter that runs clears_gate against the active profile
  runtime.py     # register_quality_runtime()
app/core/serve_filters.py   # GENERIC registry: register_serve_filter / passes_serve_filters (no "quality")
app/core/db.py              # + Lead.validation_json, Lead.quality_score
app/core/targeting/view.py  # expose "validation" (reads validation_json)
app/ingestion/pipeline.py   # stamp validation + quality_score at ingest
app/core/marketplace.py     # search consults passes_serve_filters
app/core/targeting/estimate.py  # estimate consults passes_serve_filters
app/core/purchasing.py      # unlock_lead refuses a held-back lead (raise LeadHeldBack)
app/leadvault.py            # register_quality_runtime() at startup
requirements.txt            # + phonenumbers
```

---

### Task 1: Email validator (INV-Q3 + INV-Q6) + `phonenumbers` dep

**Files:** Create `app/quality/__init__.py`, `app/quality/validators/__init__.py`,
`app/quality/validators/email.py`; Modify `requirements.txt`; Test `tests/test_quality_validators.py`.

**Interfaces — Produces:** `validate_email(email, *, mx_lookup=_default_mx) -> dict` returning
`{"present": bool, "validated": bool, "syntax": bool, "mx": bool, "disposable": bool}`; `DISPOSABLE` set;
`_default_mx(domain) -> bool` (dnspython MX lookup, network — injectable/mocked in tests).

- [ ] **Step 1: Append `phonenumbers` to `requirements.txt`** (own line): `phonenumbers==8.13.45`
- [ ] **Step 2: Write the failing tests** (`tests/test_quality_validators.py`)
```python
import inspect


def test_email_validated_requires_syntax_mx_nondisposable():
    from app.quality.validators.email import validate_email
    ok = validate_email("info@acme.com", mx_lookup=lambda d: True)
    assert ok["present"] and ok["validated"] and ok["syntax"] and ok["mx"]
    no_mx = validate_email("info@acme.com", mx_lookup=lambda d: False)
    assert no_mx["present"] and not no_mx["validated"] and not no_mx["mx"]     # no MX -> not validated
    bad = validate_email("not-an-email", mx_lookup=lambda d: True)
    assert not bad["validated"] and not bad["syntax"]
    disp = validate_email("info@mailinator.com", mx_lookup=lambda d: True)
    assert disp["disposable"] and not disp["validated"]                        # disposable -> not validated
    empty = validate_email("", mx_lookup=lambda d: True)
    assert not empty["present"] and not empty["validated"]


def test_email_validator_never_smtp_probes():   # INV-Q6
    import app.quality.validators.email as E
    src = inspect.getsource(E)
    assert "smtplib" not in src and "SMTP" not in src and "sendmail" not in src
```
- [ ] **Step 3: Run — FAIL.**
- [ ] **Step 4: Implement `app/quality/validators/email.py`**
```python
from __future__ import annotations

import re

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# small offline blocklist of common disposable-mail domains (extend as needed)
DISPOSABLE = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
              "yopmail.com", "trashmail.com", "getnada.com", "sharklasers.com",
              "dispostable.com", "maildrop.cc"}


def _default_mx(domain: str) -> bool:
    # DNS MX lookup only. NEVER connects to a mail server (no SMTP probe) — INV-Q6.
    try:
        import dns.resolver
        return len(dns.resolver.resolve(domain, "MX")) > 0
    except Exception:
        return False


def validate_email(email: str, *, mx_lookup=_default_mx) -> dict:
    email = (email or "").strip().lower()
    if not email:
        return {"present": False, "validated": False, "syntax": False,
                "mx": False, "disposable": False}
    syntax = bool(_SYNTAX.match(email))
    domain = email.split("@", 1)[1] if "@" in email else ""
    disposable = domain in DISPOSABLE
    mx = bool(mx_lookup(domain)) if (syntax and domain and not disposable) else False
    return {"present": True, "validated": syntax and mx and not disposable,
            "syntax": syntax, "mx": mx, "disposable": disposable}
```
- [ ] **Step 5: Install dep + run — PASS.** `.venv/Scripts/python -m pip install -r requirements.txt`
  then `.venv/Scripts/python -m pytest tests/test_quality_validators.py -q`.
- [ ] **Step 6: Commit** — `git add app/quality/__init__.py app/quality/validators requirements.txt tests/test_quality_validators.py` then commit `-m "feat(quality): email validator (syntax+MX+non-disposable; INV-Q3/Q6 no SMTP) + phonenumbers dep"`

---

### Task 2: Phone / address / website / profile / freshness validators

**Files:** Create `app/quality/validators/{phone,address,website,profile,freshness}.py`; Test add to
`tests/test_quality_validators.py`.

**Interfaces — Produces (each returns a per-field dict with at least `present`, `validated`):**
- `validate_phone(phone, *, region="GB") -> {present, validated, line_type}` (offline; libphonenumber)
- `validate_address(line1, city, postal_code, country, lat, lon) -> {present, validated, geocoded}` (offline: geocoded = lat & lon present)
- `validate_website(intent: dict) -> {present, validated}` (validated = `intent.get("website_reachable")`)
- `validate_profile(name, category_keys, city, opening_hours, website_url) -> {present, validated}` (validated = name & category & location present)
- `validate_freshness(date_last_verified, *, fresh_days=90) -> {present, validated}` (validated = verified within `fresh_days`)

- [ ] **Step 1: Add failing tests**
```python
def test_phone_validated_format_and_line_type():
    from app.quality.validators.phone import validate_phone
    m = validate_phone("+44 7911 123456")            # UK mobile
    assert m["present"] and m["validated"] and m["line_type"] == "mobile"
    bad = validate_phone("12")
    assert not bad["validated"]
    assert validate_phone("")["present"] is False


def test_address_validated_requires_geocode():
    from app.quality.validators.address import validate_address
    ok = validate_address("1 High St", "London", "SW1A 1AA", "GB", 51.5, -0.1)
    assert ok["present"] and ok["validated"] and ok["geocoded"]
    nogeo = validate_address("1 High St", "London", "SW1A 1AA", "GB", None, None)
    assert nogeo["present"] and not nogeo["validated"]     # no coords -> not validated


def test_website_and_profile_and_freshness():
    from app.quality.validators.website import validate_website
    from app.quality.validators.profile import validate_profile
    from app.quality.validators.freshness import validate_freshness
    from datetime import datetime, timezone, timedelta
    assert validate_website({"website_reachable": True})["validated"] is True
    assert validate_website({})["validated"] is False
    assert validate_profile("Acme", ["cafe"], "London", "Mo-Su", "https://a.com")["validated"] is True
    assert validate_profile("", [], "", "", "")["validated"] is False
    fresh = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert validate_freshness(fresh)["validated"] is True
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    assert validate_freshness(old)["validated"] is False
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**
`phone.py`:
```python
from __future__ import annotations
import phonenumbers

_TYPE = {phonenumbers.PhoneNumberType.MOBILE: "mobile",
         phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
         phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile"}


def validate_phone(phone: str, *, region: str = "GB") -> dict:
    phone = (phone or "").strip()
    if not phone:
        return {"present": False, "validated": False, "line_type": "unknown"}
    try:
        num = phonenumbers.parse(phone, region)
        valid = phonenumbers.is_valid_number(num)
        line = _TYPE.get(phonenumbers.number_type(num), "unknown")
    except Exception:
        valid, line = False, "unknown"
    # line_type is numbering-plan metadata, NOT a liveness claim.
    return {"present": True, "validated": bool(valid), "line_type": line}
```
`address.py`:
```python
from __future__ import annotations


def validate_address(line1="", city="", postal_code="", country="", lat=None, lon=None) -> dict:
    present = bool(line1 or city)
    geocoded = lat is not None and lon is not None   # offline: OSM node coords; NOT deliverability
    return {"present": present, "validated": present and geocoded, "geocoded": geocoded}
```
`website.py`:
```python
from __future__ import annotations


def validate_website(intent: dict) -> dict:
    reachable = bool((intent or {}).get("website_reachable"))
    return {"present": reachable or bool((intent or {}).get("last_scanned")),
            "validated": reachable}
```
`profile.py`:
```python
from __future__ import annotations


def validate_profile(name="", category_keys=None, city="", opening_hours="", website_url="") -> dict:
    cats = category_keys or []
    present = bool(name)
    validated = bool(name) and bool(cats) and bool(city)
    return {"present": present, "validated": validated}
```
`freshness.py`:
```python
from __future__ import annotations
from datetime import datetime, timezone


def validate_freshness(date_last_verified, *, fresh_days: int = 90) -> dict:
    if not date_last_verified:
        return {"present": False, "validated": False}
    try:
        dt = datetime.fromisoformat(date_last_verified)
    except ValueError:
        return {"present": False, "validated": False}
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    return {"present": True, "validated": days <= fresh_days}
```
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `git add app/quality/validators tests/test_quality_validators.py` then `-m "feat(quality): phone/address/website/profile/freshness validators (offline, honest)"`

---

### Task 3: Tiers + validation stamp at ingest (+ view exposes validation)

**Files:** Create `app/quality/tiers.py`, `app/quality/stamp.py`; Modify `app/core/db.py` (+
`validation_json`, `quality_score`), `app/core/targeting/view.py` (expose `validation`),
`app/ingestion/pipeline.py` (stamp); Test `tests/test_quality_stamp.py`.

**Interfaces — Produces:** `TIER_ORDER = ["absent","present","validated","verified_live"]`;
`achieved_tier(field_blob: dict) -> str`; `meets(achieved: str, required: str) -> bool`;
`build_validation(fields: dict, *, mx_lookup=None) -> dict` (per-field blobs, each with a `tier`);
`quality_score(validation: dict, weights: dict) -> int`. Lead gains `validation_json: str = "{}"` and
`quality_score: int = 0`.

- [ ] **Step 1: Failing tests** (`tests/test_quality_stamp.py`)
```python
import json
from app.quality.tiers import achieved_tier, meets, TIER_ORDER


def test_tier_order_and_meets():
    assert TIER_ORDER.index("validated") > TIER_ORDER.index("present")
    assert achieved_tier({"present": True, "validated": True}) == "validated"
    assert achieved_tier({"present": True, "validated": False}) == "present"
    assert achieved_tier({"present": False}) == "absent"
    assert achieved_tier({"present": True, "validated": True, "verified_live": True}) == "verified_live"
    assert meets("validated", "present") and not meets("present", "validated")
    assert not meets("absent", "present")


def test_build_validation_stamps_honest_tiers_and_no_gated_fields():
    from app.quality.stamp import build_validation
    fields = {"email": "info@acme.com", "phone": "+44 7911 123456",
              "address": {"line1": "1 High St", "city": "London", "lat": 51.5, "lon": -0.1},
              "intent": {"website_reachable": True}, "name": "Acme",
              "category_keys": ["cafe"], "city": "London", "opening_hours": "Mo-Su",
              "website_url": "https://a.com", "date_last_verified": None}
    v = build_validation(fields, mx_lookup=lambda d: True)
    assert v["email"]["tier"] == "validated" and v["phone"]["tier"] == "validated"
    assert v["address"]["tier"] == "validated" and v["website"]["tier"] == "validated"
    # INV-Q2: gated financial/size fields are NEVER stamped by self-run validation
    for gated in ("has_mca", "amount_owed", "lender", "size_band"):
        assert gated not in v
    # INV-Q6/Q2: nothing is verified_live from a self-run check
    assert all(fb.get("tier") != "verified_live" for fb in v.values())


def test_ingested_lead_carries_validation(monkeypatch):
    # the pipeline stamps validation_json + quality_score; assert an ingested lead has honest tiers
    import app.quality.validators.email as EM
    monkeypatch.setattr(EM, "_default_mx", lambda d: True)   # offline MX for the test
    from tests.helpers_ingest import run_fake_ingest   # provided by this task's step 3 note
    lead = run_fake_ingest()
    v = json.loads(lead.validation_json)
    assert "email" in v and "phone" in v and lead.quality_score >= 0
```
(Step-3 note: instead of a helpers file, the implementer may inline a minimal ingest in the test using
the existing `FakeAdapter` pattern from `tests/test_ingestion.py`; the assertion is only that a
pipeline-ingested lead has non-empty `validation_json` with `email`/`phone` keys and a `quality_score`.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**
`app/quality/tiers.py`:
```python
from __future__ import annotations

TIER_ORDER = ["absent", "present", "validated", "verified_live"]


def achieved_tier(fb: dict) -> str:
    if not fb or not fb.get("present"):
        return "absent"
    if fb.get("verified_live"):
        return "verified_live"
    if fb.get("validated"):
        return "validated"
    return "present"


def meets(achieved: str, required: str) -> bool:
    return TIER_ORDER.index(achieved) >= TIER_ORDER.index(required)
```
`app/quality/stamp.py`:
```python
from __future__ import annotations

from app.quality.tiers import achieved_tier
from app.quality.validators.email import validate_email, _default_mx
from app.quality.validators.phone import validate_phone
from app.quality.validators.address import validate_address
from app.quality.validators.website import validate_website
from app.quality.validators.profile import validate_profile
from app.quality.validators.freshness import validate_freshness

DEFAULT_WEIGHTS = {"email": 25, "phone": 25, "address": 15, "website": 10,
                   "profile": 15, "freshness": 10}


def build_validation(fields: dict, *, mx_lookup=None) -> dict:
    addr = fields.get("address") or {}
    blobs = {
        "email": validate_email(fields.get("email", ""), mx_lookup=mx_lookup or _default_mx),
        "phone": validate_phone(fields.get("phone", "")),
        "address": validate_address(addr.get("line1", ""), addr.get("city", ""),
                                    addr.get("postal_code", ""), addr.get("country", ""),
                                    addr.get("lat"), addr.get("lon")),
        "website": validate_website(fields.get("intent") or {}),
        "profile": validate_profile(fields.get("name", ""), fields.get("category_keys"),
                                    fields.get("city", ""), fields.get("opening_hours", ""),
                                    fields.get("website_url", "")),
        "freshness": validate_freshness(fields.get("date_last_verified")),
    }
    for fb in blobs.values():
        fb["tier"] = achieved_tier(fb)
    # NOTE (INV-Q2/Q6): no gated field (has_mca/amount_owed/lender/size_band) is produced here,
    # and no verified_live tier is ever self-generated — that requires a licensed provider.
    return blobs


def quality_score(validation: dict, weights: dict = None) -> int:
    weights = weights or DEFAULT_WEIGHTS
    total = sum(weights.values()) or 1
    got = sum(w for k, w in weights.items()
              if (validation.get(k) or {}).get("tier") in ("validated", "verified_live"))
    return round(got / total * 100)
```
`app/core/db.py` — add to `Lead` (near the JSON blobs):
```python
    validation_json: str = "{}"
    quality_score: int = Field(default=0, index=True)
```
`app/core/targeting/view.py` — add to the `lead_view(lead)` dict (reuses the existing `_load`):
```python
        "validation": _load(lead.validation_json), "quality_score": lead.quality_score,
```
`app/ingestion/pipeline.py` — after the enrichment/context is built and BEFORE constructing the stored
`Lead`, compute the stamp and pass it into the Lead(...) construction. Add
`from app.quality.stamp import build_validation, quality_score` and, using the same normalized fields the
Lead is built from (business_name, phone, public_email, website_url, address dict, category_keys,
intent/enrichment, opening_hours, date_last_verified):
```python
        _val = build_validation({
            "email": n.public_email, "phone": n.phone,
            "address": {"line1": (n.address or {}).get("line1", ""),
                        "city": (n.address or {}).get("city", ""),
                        "postal_code": (n.address or {}).get("postal_code", ""),
                        "country": (n.address or {}).get("country", ""),
                        "lat": (n.address or {}).get("lat"), "lon": (n.address or {}).get("lon")},
            "intent": enrichment, "name": n.business_name, "category_keys": n.category_keys,
            "city": (n.address or {}).get("city", ""), "opening_hours": n.opening_hours,
            "website_url": n.website_url, "date_last_verified": _now()})
        # add to the Lead(...) kwargs:
        #   validation_json=json.dumps(_val), quality_score=quality_score(_val),
```
(Match the exact variable names the pipeline already uses for the normalized lead `n` and `enrichment`;
`json` and `_now` are already imported in pipeline.py. Add the two kwargs to the existing `Lead(...)`.)
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `-m "feat(quality): tiers + ingest validation stamp (validation_json + quality_score); view exposes validation"`

---

### Task 4: Quality profiles + the gate (INV-Q2, INV-Q4)

**Files:** Create `app/quality/gate.py`, `app/quality/profiles/{__init__,base,baseline,registry}.py`;
Test `tests/test_quality_gate.py`.

**Interfaces — Produces:** `QualityProfile` (`key`, `label`, `required: dict[field->tier]`,
`weights: dict`); profile `registry` (register/get/all_keys); `BASELINE` profile
(`required = {"profile":"present","business_contact":"validated"}` where `business_contact` = phone OR
email at validated); `clears_gate(view, profile) -> bool`; `profile_score(view, profile) -> int`.
`clears_gate` reads `view["validation"][field]["tier"]` via `tiers.meets`; an ABSENT field/tier ⇒ tier
`"absent"` ⇒ does not meet (tri-state, INV-Q4). A required field with tier `verified_live` that no
provider has produced ⇒ never met ⇒ lead held back (INV-Q2).

- [ ] **Step 1: Failing tests**
```python
from app.core.db import Lead
from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.baseline import BASELINE
from app.quality.profiles.base import QualityProfile
import json


def _view(**val):
    return lead_view(Lead(business_name="X", validation_json=json.dumps(val)))


def test_clears_baseline_when_profile_and_contact_validated():
    v = _view(profile={"tier": "validated"}, email={"tier": "validated"},
              phone={"tier": "present"})
    assert clears_gate(v, BASELINE) is True


def test_held_back_when_required_field_below_tier_or_absent():   # INV-Q4
    # contact only "present" (not validated) -> held back
    v1 = _view(profile={"tier": "validated"}, email={"tier": "present"}, phone={"tier": "present"})
    assert clears_gate(v1, BASELINE) is False
    # profile absent entirely -> unknown -> held back
    v2 = _view(email={"tier": "validated"})
    assert clears_gate(v2, BASELINE) is False


def test_verified_live_requirement_never_met_without_provider():   # INV-Q2
    strict = QualityProfile(key="strict", label="Strict",
                            required={"email": "verified_live"}, weights={"email": 100})
    # best a self-run check can do is "validated" -> never meets verified_live -> held back
    v = _view(email={"tier": "validated"})
    assert clears_gate(v, strict) is False
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**
`app/quality/profiles/base.py`:
```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class QualityProfile:
    key: str
    label: str
    required: dict          # field -> min tier
    weights: dict = field(default_factory=dict)
```
`app/quality/profiles/baseline.py`:
```python
from __future__ import annotations
from app.quality.profiles.base import QualityProfile

# "business_contact" is a virtual requirement satisfied by phone OR email at the tier.
BASELINE = QualityProfile(key="baseline", label="Baseline hot bar",
                          required={"profile": "present", "business_contact": "validated"},
                          weights={"profile": 30, "business_contact": 40, "address": 15,
                                   "website": 15})
```
`app/quality/profiles/registry.py` — mirror the scoring registry (`register/get/all_keys`).
`app/quality/gate.py`:
```python
from __future__ import annotations

from app.core.targeting.view import get_path, MISSING
from app.quality.tiers import meets


def _tier(view: dict, field: str) -> str:
    t = get_path(view, f"validation.{field}.tier")
    return "absent" if t is MISSING else t


def _field_meets(view: dict, field: str, required: str) -> bool:
    if field == "business_contact":   # phone OR email at the required tier
        return meets(_tier(view, "phone"), required) or meets(_tier(view, "email"), required)
    return meets(_tier(view, field), required)


def clears_gate(view: dict, profile) -> bool:
    return all(_field_meets(view, f, req) for f, req in profile.required.items())


def profile_score(view: dict, profile) -> int:
    weights = profile.weights or {}
    total = sum(weights.values()) or 1
    got = sum(w for f, w in weights.items() if _field_meets(view, f, "validated"))
    return round(got / total * 100)
```
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `-m "feat(quality): QualityProfile + baseline + clears_gate (INV-Q2/Q4 tri-state, held-back)"`

---

### Task 5: Serve-filter hook + enforce at search, preview, unlock (INV-Q1)

**Files:** Create `app/core/serve_filters.py`, `app/quality/serve_gate.py`, `app/quality/runtime.py`;
Modify `app/core/marketplace.py` (search), `app/core/targeting/estimate.py`, `app/core/purchasing.py`
(unlock + `LeadHeldBack`), `app/leadvault.py` (startup); Test `tests/test_quality_serve_gate.py`.

**Interfaces:**
- `app/core/serve_filters.py` (GENERIC — no "quality" string): `register_serve_filter(fn)` where
  `fn(session, buyer_account_id, lead) -> bool`; `passes_serve_filters(session, buyer_account_id, lead)
  -> bool` (True iff every registered filter returns True; empty registry ⇒ True); `clear()`.
- `app/quality/serve_gate.py`: `set_gate_profile(profile)` (default BASELINE); `quality_serve_filter(
  session, ba, lead) -> bool` = `clears_gate(lead_view(lead), _active_profile)`; registered via
  `runtime.register_quality_runtime()`.
- `app/core/purchasing.py`: new `LeadHeldBack(ValueError)`; `unlock_lead` raises it when
  `not passes_serve_filters(...)`.

- [ ] **Step 1: Failing test — all three paths** (`tests/test_quality_serve_gate.py`)
```python
import json
import pytest
from sqlmodel import Session
from app.core.db import init_db, Lead, BuyerAccount, User, _now
from app.core.leadcats import sync_lead_categories
from app.core.marketplace import search
from app.core.recipes import DEFAULT_FILTERS
from app.core.targeting.estimate import estimate
from app.core.purchasing import unlock_lead, grant_credits, LeadHeldBack
from app.core.serve_filters import clear as clear_filters
from app.quality.runtime import register_quality_runtime
from app.quality.profiles.baseline import BASELINE
from app.quality.serve_gate import set_gate_profile


def _lead(session, validation):
    lead = Lead(business_name="Maybe Hot", category_keys_json=json.dumps(["cafe"]),
                city="London", phone="1", public_email="info@x.com", website_url="https://x.com",
                score_total=90, date_last_verified=_now(), price_credits=3,
                validation_json=json.dumps(validation))
    session.add(lead); session.commit(); session.refresh(lead)
    sync_lead_categories(session, lead)
    return lead


def _buyer(session):
    ba = BuyerAccount(company_name="B", credits=0, compliance_ack_at=_now())
    session.add(ba); session.commit(); session.refresh(ba)
    u = User(email="b@b.com", password_hash="x", role="buyer", buyer_account_id=ba.id)
    session.add(u); session.commit(); session.refresh(u)
    grant_credits(session, ba.id, 50)
    return ba, u


def _setup():
    clear_filters(); register_quality_runtime(); set_gate_profile(BASELINE)


def test_incomplete_lead_held_back_at_search_preview_and_unlock():   # INV-Q1 (all three)
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        # contact only "present" (not validated) -> below baseline -> HOT bar not met
        cold = _lead(s, {"profile": {"tier": "validated"},
                         "email": {"tier": "present"}, "phone": {"tier": "present"}})
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        # 1) SEARCH: not surfaced
        assert search(s, ba.id, f) == []
        # 2) PREVIEW/ESTIMATE: not counted, no sample
        comp = {"op": "AND", "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}]}
        est = estimate(s, ba.id, comp)
        assert est["count"] == 0 and est["samples"] == []
        # 3) UNLOCK: refused
        with pytest.raises(LeadHeldBack):
            unlock_lead(s, u, cold.id)


def test_hot_lead_passes_all_three():
    _setup()
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba, u = _buyer(s)
        hot = _lead(s, {"profile": {"tier": "validated"},
                        "email": {"tier": "validated"}, "phone": {"tier": "validated"}})
        f = {**DEFAULT_FILTERS, "categories": ["cafe"], "city": "London"}
        assert len(search(s, ba.id, f)) == 1
        comp = {"op": "AND", "nodes": [{"predicate": "geo.city", "params": {"value": "London"}}]}
        assert estimate(s, ba.id, comp)["count"] == 1
        assert unlock_lead(s, u, hot.id) is not None
```
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement**
`app/core/serve_filters.py`:
```python
from __future__ import annotations

_FILTERS = []


def register_serve_filter(fn) -> None:
    if fn not in _FILTERS:
        _FILTERS.append(fn)


def passes_serve_filters(session, buyer_account_id, lead) -> bool:
    return all(fn(session, buyer_account_id, lead) for fn in _FILTERS)


def clear() -> None:
    _FILTERS.clear()
```
`app/quality/serve_gate.py`:
```python
from __future__ import annotations

from app.core.targeting.view import lead_view
from app.quality.gate import clears_gate
from app.quality.profiles.baseline import BASELINE

_active = BASELINE


def set_gate_profile(profile) -> None:
    global _active
    _active = profile


def quality_serve_filter(session, buyer_account_id, lead) -> bool:
    return clears_gate(lead_view(lead), _active)
```
`app/quality/runtime.py`:
```python
from __future__ import annotations

from app.core.serve_filters import register_serve_filter
from app.quality.serve_gate import quality_serve_filter


def register_quality_runtime() -> None:
    register_serve_filter(quality_serve_filter)
```
`app/core/marketplace.py` — in `search()`, add `passes_serve_filters` to the per-lead skip chain (import
`from app.core.serve_filters import passes_serve_filters`); after the existing expired/opt-out/suppress
skips add: `if not passes_serve_filters(session, buyer_account_id, l): continue`.
`app/core/targeting/estimate.py` — in the `visible` comprehension add the same predicate:
`and passes_serve_filters(session, buyer_account_id, l)` (import it).
`app/core/purchasing.py` — add `class LeadHeldBack(ValueError): ...`; in `unlock_lead`, after the
suppression/opt-out check and BEFORE debiting, add:
`from app.core.serve_filters import passes_serve_filters` (top-level import) and
`if not passes_serve_filters(session, ba.id, lead): raise LeadHeldBack("lead does not meet the quality gate")`.
`app/leadvault.py` — after `register_targeting_runtime()` add
`from app.quality.runtime import register_quality_runtime` and `register_quality_runtime()`.
`app/web/routes_buyer.py` — the `/app/unlock/{id}` handler already catches `ValueError` and redirects;
`LeadHeldBack` is a `ValueError`, so held-back unlock attempts redirect gracefully (verify this catch
exists; if it catches specific subclasses only, add `LeadHeldBack`).
- [ ] **Step 4: Run the test + full suite.** `.venv/Scripts/python -m pytest tests/test_quality_serve_gate.py -q`; then `rm -f leadvault.db leadscraper.db` and `.venv/Scripts/python -m pytest -q -W ignore` — all pass. **IMPORTANT for the full suite:** the serve gate is now active at app import, so existing web/marketplace tests that seed leads WITHOUT a validation blob would be held back. Add a conftest autouse fixture that clears the serve filters by default for tests, OR ensure existing marketplace/web tests either seed passing validation or the gate is opt-in. The implementer MUST make the full suite green — the cleanest is a `conftest.py` autouse fixture `_reset_serve_filters` that calls `app.core.serve_filters.clear()` before each test (tests that exercise the gate re-register it explicitly, as `_setup()` does). Confirm no pre-existing web test regresses (root-cause any failure, do not dismiss).
- [ ] **Step 5: Commit** — `-m "feat(quality): serve-filter hook + enforce gate at search/preview/unlock (INV-Q1)"`

---

### Task 6: Grep-clean gate (INV-Q5) + consolidated invariants + docs

**Files:** Test `tests/test_quality_grepclean.py`; Modify `README.md`.

- [ ] **Step 1: Failing test**
```python
import pathlib, re


def test_core_is_quality_and_provider_clean():   # INV-Q5
    root = pathlib.Path("app/core")
    pat = re.compile(r"quality|energy|utility|osm|overpass|campaign|provider|mca|lender", re.I)
    hits = []
    for p in root.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{p}:{i}: {line.strip()}")
    assert hits == [], "quality/provider strings leaked into app/core:\n" + "\n".join(hits)
```
- [ ] **Step 2: Run.** If it fails, RELOCATE the offending string out of `app/core` (e.g. a docstring or
  name mentioning "quality") — do NOT weaken the test. `validation`/`serve filter`/`held back` wording is
  fine; the words in the pattern are not. Then PASS.
- [ ] **Step 3: Add a README "Lead quality gate" subsection** documenting: honest tiers
  (Present/Validated/Verified-live), that Verified-live + direct-mobile require a licensed provider and
  render "not available — requires verification/enrichment provider," the permanent no-SMTP rule
  (INV-Q6), and that leads below a profile's bar are held back at search/preview/unlock.
- [ ] **Step 4: Full suite + grep.** `rm -f leadvault.db leadscraper.db` then
  `.venv/Scripts/python -m pytest -q -W ignore` — all pass;
  `grep -rinE "quality|energy|utility|osm|overpass|campaign|provider|mca|lender" app/core/` — empty.
- [ ] **Step 5: Commit** — `-m "feat(quality): grep-clean core gate (INV-Q5) + docs"`

---

## Self-Review

**Spec coverage:** honest tiers (Task 3) · Validated-tier checks — email syntax+MX+non-disposable (T1),
phone format+line-type (T2), address geocode (T2), site-reachable (T2), profile completeness (T2),
freshness (T2), wired into ingestion (T3) · per-campaign quality profile as pluggable data/profile (T4) ·
gate hooks into ingestion + search + preview + unlock (T3, T5) · masking/suppression/audit unchanged
(T5 reuses the spine; the gate is an additional serve filter) · grep-clean core (T6). Deferred to the
Campaign layer (correctly not here): per-campaign profile SELECTION threaded through the search context —
this plan enforces a configurable active profile (default BASELINE) at serve time; the Campaign layer
will set the profile per search. The gated Verified-live/provider sources remain separate, sign-off-gated
specs.

**Invariants ↔ tests:** INV-Q1 → `test_incomplete_lead_held_back_at_search_preview_and_unlock` (all
three paths). INV-Q2 → `test_build_validation_stamps_...no_gated_fields` + `test_verified_live_requirement
_never_met_without_provider`. INV-Q3 → `test_email_validated_requires_...` + `test_phone_validated_...`.
INV-Q4 → `test_held_back_when_required_field_below_tier_or_absent`. INV-Q5 → `test_core_is_quality_and
_provider_clean`. INV-Q6 → `test_email_validator_never_smtp_probes`.

**Placeholder scan:** none — every step has runnable code/commands. The one soft spot (Task 3 Step-1
`helpers_ingest`) carries an explicit inline-alternative note.

**Type consistency:** field-blob dicts always carry `present`/`validated` (+ `tier` after `build_validation`);
`achieved_tier`/`meets`/`clears_gate` signatures consistent across T3/T4/T5; `passes_serve_filters(session,
buyer_account_id, lead)` used identically in marketplace/estimate/purchasing; `LeadHeldBack` is a
`ValueError` so the existing buyer-route ValueError catch handles it.

**Key risk called out for the executor (Task 5 Step 4):** activating the serve gate at import will hold
back existing test leads that lack a validation blob — the plan mandates a conftest reset fixture so the
gate is opt-in per test and the full suite stays green; any regression must be root-caused (the reflex the
user asked us to keep), not dismissed.
```
