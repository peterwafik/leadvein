# Lead Scraper MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable FastAPI web app that finds businesses running a chosen web technology (via fingerprint Recipes), verifies + enriches them with public contact details, streams progress live, and exports to xlsx/csv — with GloriaFood working end-to-end.

**Architecture:** A pure-Python scraping engine (`discover → fetch → analyse → export`) is driven by configurable `Recipe` objects. A FastAPI layer persists Recipes/Jobs/Leads in SQLite (SQLModel), runs jobs as background asyncio tasks, and streams `progress`/`lead`/`done` events over SSE to a single static Tailwind-CDN page.

**Tech Stack:** Python 3.11 (invoked as `py -3.11`), FastAPI, Uvicorn, requests, beautifulsoup4 + lxml, openpyxl, SQLModel/SQLite, pytest. Frontend: Tailwind via CDN + vanilla JS (no bundler).

## Global Constraints

- Python invoked as `py -3.11` on Windows; all run/test commands use it.
- No Node, no Docker, no bundler. Frontend is one static HTML page + vanilla JS.
- Engine modules (`app/engine/*`) must NOT import FastAPI, the DB, or any web layer — they are pure and unit-testable in isolation.
- Default discovery source is urlscan.io free (no API key required). PublicWWW requires `PUBLICWWW_KEY`.
- Descriptive User-Agent on every outbound request: `LeadScraper/0.1 (+https://example.com/contact; youssef.zaki@student.giu-uni.de)`.
- Politeness defaults: global request delay 1.0s, concurrency cap 5 (max 10), per-request timeout 12s. Respect robots.txt.
- Email filtering drops image extensions (`.png .jpg .jpeg .gif .svg .webp .ico`) and tracking/vendor domains (`fbgcdn`, `sentry`, `wixpress`, `cloudflare`, `gstatic`, `googleapis`, `w3.org`, `schema.org`, `example.com`).
- Excel tab name is `<Type> Prospects`. CSV mirror always available.
- A job MUST surface the exact discovery query and the raw candidate count from the source; the UI MUST distinguish "0 candidates found" (discovery returned nothing) from "N candidates found, 0 confirmed" (verification matched nothing). These are different states, never collapsed into one message.
- When `manual_hosts` is provided, discovery is bypassed entirely and only those hosts are verified/enriched (query reported as `(manual domain list)`).
- Every outbound-data action collects only publicly published business contact info; UI shows a ToS/GDPR/CAN-SPAM disclaimer.
- Use `py -3.11 -m pytest` for tests. Commit after each task.

---

## File Structure

```
app/
  __init__.py
  engine/
    __init__.py
    recipes.py     # Recipe dataclass + BUILTIN_RECIPES seed + lookup helpers
    politeness.py  # RobotsCache, RateLimiter
    discover.py    # discover_urlscan, discover_publicwww, normalize_hosts, discover()
    enrich.py      # norm_url, fetch, analyse -> LeadData
    export.py      # rows_to_xlsx, rows_to_csv, append_xlsx
    runner.py      # run_job async generator (discover -> enrich -> events)
  db.py            # SQLModel models Recipe/Job/Lead + engine/session + seed_builtins
  schemas.py       # Pydantic request/response models
  main.py          # FastAPI app, routes, SSE, static mount, startup
  static/
    index.html
    app.js
    styles.css
tests/
  test_recipes.py
  test_discover.py
  test_enrich.py
  test_export.py
  test_runner.py
  test_api.py
requirements.txt
.env.example
README.md
pytest.ini
```

---

### Task 1: Project scaffold, dependencies, package skeleton

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.env.example`
- Create: `app/__init__.py`, `app/engine/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: an importable `app` package and a working pytest setup.

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.30.1
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
openpyxl==3.1.5
sqlmodel==0.0.21
python-multipart==0.0.9
python-dotenv==1.0.1
pytest==8.2.2
httpx==0.27.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: Create `.env.example`**

```
# Optional API keys. Leave blank to use urlscan.io free search.
URLSCAN_KEY=
PUBLICWWW_KEY=
```

- [ ] **Step 4: Create empty package files**

`app/__init__.py`, `app/engine/__init__.py`, `tests/__init__.py` — all empty files.

- [ ] **Step 5: Write smoke test `tests/test_smoke.py`**

```python
import app  # noqa: F401


def test_app_package_imports():
    assert app is not None
```

- [ ] **Step 6: Create venv and install deps**

Run:
```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```
Expected: installs succeed. (On Windows the interpreter is `.venv/Scripts/python`.)

- [ ] **Step 7: Run smoke test**

Run: `.venv/Scripts/python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold lead scraper project"
```
(If `git init` already done or git unavailable, skip git and note it.)

---

### Task 2: Recipe model + built-in seed library

**Files:**
- Create: `app/engine/recipes.py`
- Test: `tests/test_recipes.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `@dataclass Recipe(id:str, category:str, type:str, urlscan_query:str, publicwww_query:str, verify_fingerprints:list[str], id_extractors:dict[str,str], exclude_hosts:list[str], logo:str="", is_builtin:bool=True)`
  - `BUILTIN_RECIPES: list[Recipe]`
  - `get_builtin(recipe_id:str) -> Recipe | None`
  - `recipes_by_category(recipes:list[Recipe]) -> dict[str, list[Recipe]]`

- [ ] **Step 1: Write failing test `tests/test_recipes.py`**

```python
from app.engine.recipes import (
    Recipe, BUILTIN_RECIPES, get_builtin, recipes_by_category,
)


def test_gloriafood_recipe_is_faithful():
    gf = get_builtin("gloriafood")
    assert gf is not None
    assert gf.type == "GloriaFood"
    assert gf.category == "Online Ordering / Restaurants"
    assert gf.urlscan_query == "domain:fbgcdn.com"
    assert gf.publicwww_query == '"fbgcdn.com/embedder"'
    for fp in ["fbgcdn.com", "ewm2.js", "data-glf-cuid", "data-glf-ruid", "gloriafood"]:
        assert fp in gf.verify_fingerprints
    assert set(gf.id_extractors.keys()) == {"ruid", "cuid"}
    assert "foodbooking" in gf.exclude_hosts


def test_catalog_has_expected_breadth():
    ids = {r.id for r in BUILTIN_RECIPES}
    for expected in ["gloriafood", "shopify", "calendly", "intercom", "stripe_checkout"]:
        assert expected in ids
    # every recipe has at least one fingerprint and a urlscan query
    for r in BUILTIN_RECIPES:
        assert r.verify_fingerprints, r.id
        assert r.urlscan_query, r.id


def test_grouping_by_category():
    grouped = recipes_by_category(BUILTIN_RECIPES)
    assert "Online Ordering / Restaurants" in grouped
    assert any(r.type == "GloriaFood" for r in grouped["Online Ordering / Restaurants"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_recipes.py -v`
Expected: FAIL (ModuleNotFoundError: app.engine.recipes).

- [ ] **Step 3: Implement `app/engine/recipes.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Recipe:
    id: str
    category: str
    type: str
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = field(default_factory=list)
    id_extractors: dict[str, str] = field(default_factory=dict)
    exclude_hosts: list[str] = field(default_factory=list)
    logo: str = ""
    is_builtin: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _r(**kw) -> Recipe:
    return Recipe(**kw)


BUILTIN_RECIPES: list[Recipe] = [
    # ---- Online Ordering / Restaurants ----
    _r(
        id="gloriafood",
        category="Online Ordering / Restaurants",
        type="GloriaFood",
        urlscan_query="domain:fbgcdn.com",
        publicwww_query='"fbgcdn.com/embedder"',
        verify_fingerprints=["fbgcdn.com", "ewm2.js", "data-glf-cuid",
                             "data-glf-ruid", "gloriafood"],
        id_extractors={
            "ruid": r'data-glf-ruid=["\']([0-9a-fA-F-]+)["\']',
            "cuid": r'data-glf-cuid=["\']([0-9a-fA-F-]+)["\']',
        },
        exclude_hosts=["gloriafood", "fbgcdn", "foodbooking"],
    ),
    _r(id="chownow", category="Online Ordering / Restaurants", type="ChowNow",
       urlscan_query="domain:chownow.com", publicwww_query='"chownow.com"',
       verify_fingerprints=["chownow.com", "chownow"], exclude_hosts=["chownow"]),
    _r(id="flipdish", category="Online Ordering / Restaurants", type="Flipdish",
       urlscan_query="domain:flipdish.com", publicwww_query='"flipdish.com"',
       verify_fingerprints=["flipdish.com", "flipdish"], exclude_hosts=["flipdish"]),

    # ---- E-commerce ----
    _r(id="shopify", category="E-commerce", type="Shopify",
       urlscan_query="domain:cdn.shopify.com", publicwww_query='"cdn.shopify.com"',
       verify_fingerprints=["cdn.shopify.com", "shopify"], exclude_hosts=["shopify"]),
    _r(id="woocommerce", category="E-commerce", type="WooCommerce",
       urlscan_query='"woocommerce"', publicwww_query='"woocommerce"',
       verify_fingerprints=["woocommerce", "wp-content/plugins/woocommerce"],
       exclude_hosts=["woocommerce.com"]),
    _r(id="bigcommerce", category="E-commerce", type="BigCommerce",
       urlscan_query="domain:bigcommerce.com", publicwww_query='"bigcommerce.com"',
       verify_fingerprints=["bigcommerce.com", "bigcommerce"], exclude_hosts=["bigcommerce"]),
    _r(id="magento", category="E-commerce", type="Magento",
       urlscan_query='"Magento"', publicwww_query='"Magento"',
       verify_fingerprints=["magento", "mage/"], exclude_hosts=["magento.com"]),

    # ---- Website Builders ----
    _r(id="wix", category="Website Builders", type="Wix",
       urlscan_query="domain:wixstatic.com", publicwww_query='"wixstatic.com"',
       verify_fingerprints=["wixstatic.com", "wix.com", "_wix"], exclude_hosts=["wix.com", "wixsite.com"]),
    _r(id="squarespace", category="Website Builders", type="Squarespace",
       urlscan_query="domain:squarespace.com", publicwww_query='"squarespace.com"',
       verify_fingerprints=["squarespace.com", "static1.squarespace"], exclude_hosts=["squarespace.com"]),
    _r(id="webflow", category="Website Builders", type="Webflow",
       urlscan_query="domain:webflow.com", publicwww_query='"webflow.com"',
       verify_fingerprints=["webflow.com", "wf-", "webflow"], exclude_hosts=["webflow.com", "webflow.io"]),
    _r(id="godaddy", category="Website Builders", type="GoDaddy Websites",
       urlscan_query="domain:img1.wsimg.com", publicwww_query='"img1.wsimg.com"',
       verify_fingerprints=["img1.wsimg.com", "wsimg.com"], exclude_hosts=["godaddy.com", "wsimg.com"]),

    # ---- Booking / Scheduling ----
    _r(id="calendly", category="Booking / Scheduling", type="Calendly",
       urlscan_query="domain:assets.calendly.com", publicwww_query='"assets.calendly.com"',
       verify_fingerprints=["assets.calendly.com", "calendly.com", "calendly"], exclude_hosts=["calendly.com"]),
    _r(id="acuity", category="Booking / Scheduling", type="Acuity",
       urlscan_query="domain:acuityscheduling.com", publicwww_query='"acuityscheduling.com"',
       verify_fingerprints=["acuityscheduling.com", "acuity"], exclude_hosts=["acuityscheduling.com"]),
    _r(id="calcom", category="Booking / Scheduling", type="Cal.com",
       urlscan_query="domain:cal.com", publicwww_query='"cal.com/embed"',
       verify_fingerprints=["cal.com/embed", "cal-embed", "app.cal.com"], exclude_hosts=["cal.com"]),
    _r(id="mindbody", category="Booking / Scheduling", type="Mindbody",
       urlscan_query="domain:mindbodyonline.com", publicwww_query='"mindbodyonline.com"',
       verify_fingerprints=["mindbodyonline.com", "mindbody"], exclude_hosts=["mindbodyonline.com"]),

    # ---- Marketing / Chat widgets ----
    _r(id="hubspot", category="Marketing / Chat widgets", type="HubSpot",
       urlscan_query="domain:js.hs-scripts.com", publicwww_query='"js.hs-scripts.com"',
       verify_fingerprints=["js.hs-scripts.com", "hs-scripts", "hubspot"], exclude_hosts=["hubspot.com"]),
    _r(id="intercom", category="Marketing / Chat widgets", type="Intercom",
       urlscan_query="domain:widget.intercom.io", publicwww_query='"widget.intercom.io"',
       verify_fingerprints=["widget.intercom.io", "intercom"], exclude_hosts=["intercom.com", "intercom.io"]),
    _r(id="drift", category="Marketing / Chat widgets", type="Drift",
       urlscan_query="domain:js.driftt.com", publicwww_query='"js.driftt.com"',
       verify_fingerprints=["js.driftt.com", "drift.com", "driftt"], exclude_hosts=["drift.com", "driftt.com"]),
    _r(id="tawkto", category="Marketing / Chat widgets", type="Tawk.to",
       urlscan_query="domain:embed.tawk.to", publicwww_query='"embed.tawk.to"',
       verify_fingerprints=["embed.tawk.to", "tawk.to"], exclude_hosts=["tawk.to"]),

    # ---- Payments ----
    _r(id="stripe_checkout", category="Payments", type="Stripe Checkout",
       urlscan_query="domain:js.stripe.com", publicwww_query='"js.stripe.com"',
       verify_fingerprints=["js.stripe.com", "stripe"], exclude_hosts=["stripe.com"]),
    _r(id="paypal_buttons", category="Payments", type="PayPal Buttons",
       urlscan_query="domain:paypal.com", publicwww_query='"paypal.com/sdk/js"',
       verify_fingerprints=["paypal.com/sdk/js", "paypalobjects", "paypal-button"],
       exclude_hosts=["paypal.com"]),
]


def get_builtin(recipe_id: str) -> Recipe | None:
    for r in BUILTIN_RECIPES:
        if r.id == recipe_id:
            return r
    return None


def recipes_by_category(recipes: list[Recipe]) -> dict[str, list[Recipe]]:
    grouped: dict[str, list[Recipe]] = {}
    for r in recipes:
        grouped.setdefault(r.category, []).append(r)
    return grouped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_recipes.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/recipes.py tests/test_recipes.py
git commit -m "feat(engine): Recipe model + built-in seed library"
```

---

### Task 3: Enrich — norm_url, analyse (HTML parsing), fetch

**Files:**
- Create: `app/engine/enrich.py`
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `Recipe` from `app.engine.recipes`.
- Produces:
  - `norm_url(host_or_url:str) -> str` — returns `https://host/` form.
  - `@dataclass LeadData(name, website, on_platform:bool, matched:str, emails:list[str], phones:list[str], ids:dict[str,str], socials:dict[str,str], address:str, country:str)`
  - `analyse(recipe:Recipe, url:str, html:str) -> LeadData` — pure, no network.
  - `fetch(url:str, *, timeout:int=12, user_agent:str) -> tuple[str|None, str|None]` — `(final_url, html)`; retries trailing `/`. (network; tested via monkeypatch.)
  - Constants `IMAGE_EXTS`, `TRACKING_TOKENS`, `USER_AGENT`.

- [ ] **Step 1: Write failing test `tests/test_enrich.py`**

```python
from app.engine.recipes import get_builtin
from app.engine.enrich import norm_url, analyse


GF = get_builtin("gloriafood")

SAMPLE_HTML = """
<html><head>
<title>Mario's Pizzeria</title>
<meta property="og:site_name" content="Mario's Pizzeria Official">
</head><body>
<a href="mailto:info@marios.com">Email us</a>
<a href="tel:+1-555-123-4567">Call</a>
Reach sales@marios.com or noreply@fbgcdn.com (skip this) and logo@cdn.png
<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>
<div data-glf-cuid="11111111-2222-3333-4444-555555555555"
     data-glf-ruid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"></div>
<a href="https://facebook.com/marios">fb</a>
<a href="https://instagram.com/marios">ig</a>
</body></html>
"""


def test_norm_url_adds_scheme_and_slash():
    assert norm_url("marios.com") == "https://marios.com/"
    assert norm_url("https://marios.com") == "https://marios.com/"


def test_analyse_confirms_platform_and_matched_fingerprint():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.on_platform is True
    assert lead.matched in GF.verify_fingerprints


def test_analyse_extracts_name():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.name == "Mario's Pizzeria"


def test_analyse_extracts_filtered_emails():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert "info@marios.com" in lead.emails
    assert "sales@marios.com" in lead.emails
    assert "noreply@fbgcdn.com" not in lead.emails  # tracking domain filtered
    assert "logo@cdn.png" not in lead.emails         # image-ext filtered


def test_analyse_extracts_phone_from_tel():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert any("555" in p for p in lead.phones)


def test_analyse_extracts_recipe_ids():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.ids["ruid"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert lead.ids["cuid"] == "11111111-2222-3333-4444-555555555555"


def test_analyse_extracts_socials():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert "facebook" in lead.socials
    assert "instagram" in lead.socials


def test_analyse_not_confirmed_when_absent():
    lead = analyse(GF, "https://x.com/", "<html><title>x</title></html>")
    assert lead.on_platform is False
    assert lead.matched == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_enrich.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/engine/enrich.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

USER_AGENT = ("LeadScraper/0.1 (+https://example.com/contact; "
              "youssef.zaki@student.giu-uni.de)")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")
TRACKING_TOKENS = ("fbgcdn", "sentry", "wixpress", "cloudflare", "gstatic",
                   "googleapis", "w3.org", "schema.org", "example.com",
                   "sentry.io", "cloudfront")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
SOCIAL_HOSTS = {
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "linkedin": "linkedin.com",
    "twitter": "twitter.com",
}


@dataclass
class LeadData:
    name: str = ""
    website: str = ""
    on_platform: bool = False
    matched: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    socials: dict[str, str] = field(default_factory=dict)
    address: str = ""
    country: str = ""


def norm_url(host_or_url: str) -> str:
    s = host_or_url.strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    if not s.endswith("/") and s.count("/") <= 2:
        s = s + "/"
    return s


def _clean_emails(candidates: list[str]) -> list[str]:
    out: list[str] = []
    for e in candidates:
        e = e.strip().strip(".,;:").lower()
        low = e.lower()
        if low.endswith(IMAGE_EXTS):
            continue
        if any(tok in low for tok in TRACKING_TOKENS):
            continue
        if e and e not in out:
            out.append(e)
    return out


def _extract_name(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        if t:
            return t
    for prop in ("og:site_name", "og:title"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def analyse(recipe, url: str, html: str) -> LeadData:
    lead = LeadData(website=url)
    low = html.lower()

    # verify fingerprints
    for fp in recipe.verify_fingerprints:
        if fp.lower() in low:
            lead.on_platform = True
            lead.matched = fp
            break

    soup = BeautifulSoup(html, "lxml")
    lead.name = _extract_name(soup)

    # emails: mailto links first, then regex over text
    email_candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            email_candidates.append(href[7:].split("?")[0])
    email_candidates += EMAIL_RE.findall(html)
    lead.emails = _clean_emails(email_candidates)

    # phones: tel links first, else regex over visible text
    phones: list[str] = []
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            p = a["href"][4:].strip()
            if p and p not in phones:
                phones.append(p)
    if not phones:
        text = soup.get_text(" ")
        for m in PHONE_RE.findall(text):
            mm = m.strip()
            digits = re.sub(r"\D", "", mm)
            if 7 <= len(digits) <= 15 and mm not in phones:
                phones.append(mm)
    lead.phones = phones[:5]

    # recipe id extractors
    for label, pattern in recipe.id_extractors.items():
        m = re.search(pattern, html)
        if m:
            lead.ids[label] = m.group(1)

    # socials
    for name, host in SOCIAL_HOSTS.items():
        for a in soup.find_all("a", href=True):
            if host in a["href"].lower():
                lead.socials[name] = a["href"]
                break

    return lead


def fetch(url: str, *, timeout: int = 12, user_agent: str = USER_AGENT):
    headers = {"User-Agent": user_agent}
    for candidate in (url, url if url.endswith("/") else url + "/"):
        try:
            resp = requests.get(candidate, headers=headers, timeout=timeout,
                                allow_redirects=True)
            if resp.status_code == 200 and resp.text:
                return resp.url, resp.text
        except requests.RequestException:
            continue
    return None, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_enrich.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/enrich.py tests/test_enrich.py
git commit -m "feat(engine): fetch + analyse enrichment"
```

---

### Task 4: Discovery — urlscan + publicwww + host normalization

**Files:**
- Create: `app/engine/discover.py`
- Test: `tests/test_discover.py`

**Interfaces:**
- Consumes: `Recipe`.
- Produces:
  - `normalize_hosts(hosts:Iterable[str], exclude_hosts:list[str]) -> list[str]` — lowercase, strip `www.`, dedup, drop excluded.
  - `discover_urlscan(query:str, *, limit:int, api_key:str|None, session=requests) -> list[str]`
  - `discover_publicwww(query:str, *, limit:int, api_key:str, session=requests) -> list[str]`
  - `discover_meta(recipe:Recipe, *, source:str, limit:int, keyword:str="", urlscan_key=None, publicwww_key=None, session=requests) -> dict` returning `{"query": str, "raw_count": int, "hosts": list[str]}` — `raw_count` is the candidate count straight from the source BEFORE normalize/dedup; `hosts` is the deduped, exclude-filtered, limited list to verify.
  - `discover(recipe:Recipe, *, source:str, limit:int, keyword:str="", urlscan_key=None, publicwww_key=None, session=requests) -> list[str]` (source in {"urlscan","publicwww"}); thin wrapper returning `discover_meta(...)["hosts"]`.

- [ ] **Step 1: Write failing test `tests/test_discover.py`**

```python
from app.engine.recipes import get_builtin
from app.engine.discover import normalize_hosts, discover_urlscan


GF = get_builtin("gloriafood")


def test_normalize_hosts_dedup_strip_www_and_exclude():
    raw = ["WWW.Marios.com", "marios.com", "cdn.fbgcdn.com", "joes.com"]
    out = normalize_hosts(raw, GF.exclude_hosts)
    assert "marios.com" in out
    assert "joes.com" in out
    assert out.count("marios.com") == 1
    assert all("fbgcdn" not in h for h in out)


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self._pages.pop(0)


def test_discover_urlscan_extracts_and_paginates():
    page1 = FakeResp(200, {
        "results": [
            {"page": {"domain": "marios.com"}, "sort": [1]},
            {"page": {"domain": "www.joes.com"}, "sort": [2]},
        ],
        "has_more": True,
    })
    page2 = FakeResp(200, {
        "results": [{"page": {"domain": "pat.com"}, "sort": [3]}],
        "has_more": False,
    })
    session = FakeSession([page1, page2])
    hosts = discover_urlscan("domain:fbgcdn.com", limit=100, api_key=None,
                             session=session)
    assert "marios.com" in hosts
    assert "joes.com" in hosts
    assert "pat.com" in hosts
    assert session.calls == 2


def test_discover_urlscan_respects_limit():
    page1 = FakeResp(200, {
        "results": [
            {"page": {"domain": "a.com"}, "sort": [1]},
            {"page": {"domain": "b.com"}, "sort": [2]},
        ],
        "has_more": True,
    })
    session = FakeSession([page1])
    hosts = discover_urlscan("q", limit=2, api_key=None, session=session)
    assert len(hosts) == 2
    assert session.calls == 1


def test_discover_meta_surfaces_query_and_raw_count():
    from app.engine.discover import discover_meta
    # two raw results, one is the vendor's own infra host -> excluded after dedup
    page = FakeResp(200, {
        "results": [
            {"page": {"domain": "marios.com"}, "sort": [1]},
            {"page": {"domain": "cdn.fbgcdn.com"}, "sort": [2]},
        ],
        "has_more": False,
    })
    session = FakeSession([page])
    meta = discover_meta(GF, source="urlscan", limit=50, session=session)
    assert meta["query"] == "domain:fbgcdn.com"
    assert meta["raw_count"] == 2            # raw, before exclude/dedup
    assert meta["hosts"] == ["marios.com"]   # fbgcdn host filtered out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_discover.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/engine/discover.py`**

```python
from __future__ import annotations

import time
from typing import Iterable

import requests

from .enrich import USER_AGENT

URLSCAN_API = "https://urlscan.io/api/v1/search/"
PUBLICWWW_API = "https://publicwww.com/websites/{query}/"


def normalize_hosts(hosts: Iterable[str], exclude_hosts: list[str]) -> list[str]:
    excl = [e.lower() for e in exclude_hosts]
    out: list[str] = []
    seen: set[str] = set()
    for h in hosts:
        if not h:
            continue
        host = h.strip().lower()
        if host.startswith("www."):
            host = host[4:]
        host = host.split("/")[0]
        if any(tok in host for tok in excl):
            continue
        if host in seen:
            continue
        seen.add(host)
        out.append(host)
    return out


def discover_urlscan(query: str, *, limit: int, api_key: str | None,
                     session=requests) -> list[str]:
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["API-Key"] = api_key
    hosts: list[str] = []
    search_after = None
    backoff = 2.0
    while len(hosts) < limit:
        params = {"q": query, "size": 100}
        if search_after is not None:
            params["search_after"] = ",".join(str(x) for x in search_after)
        resp = session.get(URLSCAN_API, params=params, headers=headers, timeout=20)
        if getattr(resp, "status_code", 200) == 429:
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        for r in results:
            dom = (r.get("page") or {}).get("domain")
            if dom:
                hosts.append(dom)
                if len(hosts) >= limit:
                    break
        if not data.get("has_more"):
            break
        search_after = results[-1].get("sort")
        if not search_after:
            break
    return hosts[:limit]


def discover_publicwww(query: str, *, limit: int, api_key: str,
                       session=requests) -> list[str]:
    if not api_key:
        raise ValueError("PublicWWW requires PUBLICWWW_KEY")
    headers = {"User-Agent": USER_AGENT}
    url = PUBLICWWW_API.format(query=query)
    resp = session.get(url, params={"export": "urls", "key": api_key},
                       headers=headers, timeout=30)
    text = getattr(resp, "text", "") or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[:limit]


def discover_meta(recipe, *, source: str, limit: int, keyword: str = "",
                  urlscan_key=None, publicwww_key=None, session=requests) -> dict:
    if source == "publicwww":
        q = recipe.publicwww_query
        if keyword:
            q = f"{q} {keyword}"
        raw = discover_publicwww(q, limit=limit * 2, api_key=publicwww_key,
                                 session=session)
    else:
        q = recipe.urlscan_query
        if keyword:
            q = f"{q} AND page.title:{keyword}"
        raw = discover_urlscan(q, limit=limit * 2, api_key=urlscan_key,
                               session=session)
    hosts = normalize_hosts(raw, recipe.exclude_hosts)[:limit]
    return {"query": q, "raw_count": len(raw), "hosts": hosts}


def discover(recipe, *, source: str, limit: int, keyword: str = "",
             urlscan_key=None, publicwww_key=None, session=requests) -> list[str]:
    return discover_meta(recipe, source=source, limit=limit, keyword=keyword,
                         urlscan_key=urlscan_key, publicwww_key=publicwww_key,
                         session=session)["hosts"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_discover.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/discover.py tests/test_discover.py
git commit -m "feat(engine): urlscan + publicwww discovery"
```

---

### Task 5: Politeness — robots.txt cache + rate limiter

**Files:**
- Create: `app/engine/politeness.py`
- Test: `tests/test_politeness.py`

**Interfaces:**
- Consumes: nothing (stdlib `urllib.robotparser`).
- Produces:
  - `class RobotsCache: __init__(self, user_agent:str, fetcher=None)`; `allowed(self, url:str) -> bool` (caches per host; failure-open = allowed).
  - `class RateLimiter: __init__(self, delay:float)`; `async def wait(self) -> None` (enforces min interval between calls).

- [ ] **Step 1: Write failing test `tests/test_politeness.py`**

```python
import asyncio

from app.engine.politeness import RobotsCache, RateLimiter


def test_robots_allows_when_no_rules():
    cache = RobotsCache("UA", fetcher=lambda host: "")  # empty robots = allow
    assert cache.allowed("https://marios.com/") is True


def test_robots_blocks_disallowed_path():
    robots = "User-agent: *\nDisallow: /private"
    cache = RobotsCache("UA", fetcher=lambda host: robots)
    assert cache.allowed("https://marios.com/private/x") is False
    assert cache.allowed("https://marios.com/menu") is True


def test_robots_failure_open():
    def boom(host):
        raise RuntimeError("network down")
    cache = RobotsCache("UA", fetcher=boom)
    assert cache.allowed("https://marios.com/") is True


def test_rate_limiter_enforces_delay():
    async def run():
        rl = RateLimiter(0.05)
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        await rl.wait()
        await rl.wait()
        return loop.time() - t0
    elapsed = asyncio.run(run())
    assert elapsed >= 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_politeness.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/engine/politeness.py`**

```python
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .enrich import USER_AGENT


def _default_fetcher(host: str) -> str:
    resp = requests.get(f"https://{host}/robots.txt",
                        headers={"User-Agent": USER_AGENT}, timeout=8)
    if resp.status_code == 200:
        return resp.text
    return ""


class RobotsCache:
    def __init__(self, user_agent: str = USER_AGENT, fetcher=None):
        self.user_agent = user_agent
        self.fetcher = fetcher or _default_fetcher
        self._cache: dict[str, RobotFileParser | None] = {}

    def _parser_for(self, host: str) -> RobotFileParser | None:
        if host in self._cache:
            return self._cache[host]
        parser: RobotFileParser | None
        try:
            text = self.fetcher(host)
            parser = RobotFileParser()
            parser.parse(text.splitlines())
        except Exception:
            parser = None  # failure-open
        self._cache[host] = parser
        return parser

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        path = parts.path or "/"
        parser = self._parser_for(host)
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, path)
        except Exception:
            return True


class RateLimiter:
    def __init__(self, delay: float):
        self.delay = delay
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait_for = self._last + self.delay - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last = loop.time()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_politeness.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/politeness.py tests/test_politeness.py
git commit -m "feat(engine): robots.txt cache + rate limiter"
```

---

### Task 6: Export — xlsx, csv, append-to-tracker

**Files:**
- Create: `app/engine/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `rows_to_csv(columns:list[str], rows:list[dict]) -> bytes`
  - `rows_to_xlsx(sheet_name:str, columns:list[str], rows:list[dict]) -> bytes`
  - `append_xlsx(existing:bytes, sheet_name:str, rows:list[dict]) -> bytes` — preserves the uploaded sheet's existing header/column order; maps row dict keys onto those columns.

- [ ] **Step 1: Write failing test `tests/test_export.py`**

```python
import io
from openpyxl import load_workbook

from app.engine.export import rows_to_csv, rows_to_xlsx, append_xlsx

COLUMNS = ["name", "website", "email"]
ROWS = [
    {"name": "Mario's", "website": "marios.com", "email": "info@marios.com"},
    {"name": "Joe's", "website": "joes.com", "email": ""},
]


def test_rows_to_csv_has_header_and_rows():
    data = rows_to_csv(COLUMNS, ROWS).decode("utf-8")
    lines = [l for l in data.splitlines() if l]
    assert lines[0] == "name,website,email"
    assert "Mario's,marios.com,info@marios.com" in lines[1]
    assert len(lines) == 3


def test_rows_to_xlsx_named_sheet_and_content():
    blob = rows_to_xlsx("GloriaFood Prospects", COLUMNS, ROWS)
    wb = load_workbook(io.BytesIO(blob))
    assert "GloriaFood Prospects" in wb.sheetnames
    ws = wb["GloriaFood Prospects"]
    assert [c.value for c in ws[1]] == COLUMNS
    assert ws.cell(row=2, column=1).value == "Mario's"


def test_append_xlsx_preserves_existing_column_order():
    # existing tracker with a DIFFERENT column order
    existing_cols = ["website", "name", "email", "status"]
    existing = rows_to_xlsx("GloriaFood Prospects", existing_cols,
                            [{"website": "old.com", "name": "Old", "email": "",
                              "status": "Contacted"}])
    merged = append_xlsx(existing, "GloriaFood Prospects", ROWS)
    wb = load_workbook(io.BytesIO(merged))
    ws = wb["GloriaFood Prospects"]
    assert [c.value for c in ws[1]] == existing_cols  # order preserved
    # original row kept, new rows appended mapped onto existing order
    assert ws.cell(row=2, column=1).value == "old.com"
    assert ws.cell(row=3, column=2).value == "Mario's"  # name is col 2 here
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_export.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/engine/export.py`**

```python
from __future__ import annotations

import csv
import io

from openpyxl import Workbook, load_workbook


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, bool):
        return "Y" if value else "N"
    return str(value)


def rows_to_csv(columns: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_stringify(row.get(c, "")) for c in columns])
    return buf.getvalue().encode("utf-8")


def rows_to_xlsx(sheet_name: str, columns: list[str], rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # Excel tab name limit
    ws.append(columns)
    for row in rows:
        ws.append([_stringify(row.get(c, "")) for c in columns])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def append_xlsx(existing: bytes, sheet_name: str, rows: list[dict]) -> bytes:
    wb = load_workbook(io.BytesIO(existing))
    name = sheet_name[:31]
    if name in wb.sheetnames:
        ws = wb[name]
    else:
        ws = wb.create_sheet(name)
    header = [c.value for c in ws[1] if c.value is not None]
    if not header:
        # empty sheet: seed header from first row's keys
        header = list(rows[0].keys()) if rows else []
        ws.append(header)
    for row in rows:
        ws.append([_stringify(row.get(col, "")) for col in header])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_export.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/export.py tests/test_export.py
git commit -m "feat(engine): xlsx/csv export + append-to-tracker"
```

---

### Task 7: Runner — orchestrate discover → enrich → events

**Files:**
- Create: `app/engine/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `Recipe`, `discover_meta`, `fetch`, `analyse`, `RobotsCache`, `RateLimiter`.
- Produces:
  - `@dataclass JobConfig(source:str, limit:int, keyword:str, country:str, delay:float, concurrency:int, only_confirmed:bool, urlscan_key, publicwww_key, manual_hosts:list[str]=[])` — when `manual_hosts` is non-empty, discovery is bypassed and those hosts are verified directly.
  - `async def run_job(recipe, config:JobConfig, *, discover_fn=discover_meta, fetch_fn=fetch, robots=None) -> AsyncIterator[dict]` — `discover_fn(recipe, **kwargs) -> {"query","raw_count","hosts"}`. Yields events: `{"type":"progress", "checked","total","confirmed","current_host","query","raw_candidates","log"}`, `{"type":"lead", "lead":{...}}`, `{"type":"done", "checked","confirmed","raw_candidates","query","totals"}`. `fetch_fn(url)->(final_url, html)`. The FIRST progress event always carries `query` (exact discovery query, or `"(manual domain list)"`) and `raw_candidates` (count from source before dedup, or len(manual_hosts)) so the UI can distinguish "0 candidates found" from "N found, 0 confirmed".
  - `def lead_to_row(lead:LeadData, recipe, source_query:str) -> dict` — column-keyed dict for export/table.

- [ ] **Step 1: Write failing test `tests/test_runner.py`**

```python
import asyncio

from app.engine.recipes import get_builtin
from app.engine.runner import run_job, JobConfig

GF = get_builtin("gloriafood")

CONFIRMED_HTML = (
    '<html><title>Mario</title><body>'
    '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
    '<a href="mailto:info@marios.com">e</a></body></html>'
)
PLAIN_HTML = "<html><title>Nope</title><body>nothing here</body></html>"


def fake_discover(recipe, **kwargs):
    return {"query": "domain:fbgcdn.com", "raw_count": 2,
            "hosts": ["marios.com", "nothere.com"]}


def make_fetch():
    def fetch_fn(url, **kwargs):
        if "marios" in url:
            return url, CONFIRMED_HTML
        return url, PLAIN_HTML
    return fetch_fn


class AllowAllRobots:
    def allowed(self, url):
        return True


def collect(recipe, config):
    async def _run():
        events = []
        async for ev in run_job(recipe, config, discover_fn=fake_discover,
                                fetch_fn=make_fetch(), robots=AllowAllRobots()):
            events.append(ev)
        return events
    return asyncio.run(_run())


def test_run_job_emits_progress_lead_and_done():
    cfg = JobConfig(source="urlscan", limit=10, keyword="", country="",
                    delay=0.0, concurrency=2, only_confirmed=False,
                    urlscan_key=None, publicwww_key=None)
    events = collect(GF, cfg)
    types = [e["type"] for e in events]
    assert "progress" in types
    assert "lead" in types
    assert types[-1] == "done"
    leads = [e["lead"] for e in events if e["type"] == "lead"]
    confirmed = [l for l in leads if l["on_platform"] in (True, "Y")]
    assert any("marios.com" in l["website"] for l in confirmed)
    # first progress event surfaces the discovery query + raw candidate count
    first = next(e for e in events if e["type"] == "progress")
    assert first["query"] == "domain:fbgcdn.com"
    assert first["raw_candidates"] == 2


def test_manual_hosts_bypass_discovery():
    def boom(recipe, **kwargs):
        raise AssertionError("discovery must not run when manual_hosts set")

    cfg = JobConfig(source="urlscan", limit=10, keyword="", country="",
                    delay=0.0, concurrency=2, only_confirmed=True,
                    urlscan_key=None, publicwww_key=None,
                    manual_hosts=["marios.com"])

    async def _run():
        events = []
        async for ev in run_job(GF, cfg, discover_fn=boom,
                                fetch_fn=make_fetch(), robots=AllowAllRobots()):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    first = next(e for e in events if e["type"] == "progress")
    assert first["query"] == "(manual domain list)"
    assert first["raw_candidates"] == 1
    leads = [e["lead"] for e in events if e["type"] == "lead"]
    assert any("marios.com" in l["website"] for l in leads)


def test_only_confirmed_filters_unconfirmed():
    cfg = JobConfig(source="urlscan", limit=10, keyword="", country="",
                    delay=0.0, concurrency=2, only_confirmed=True,
                    urlscan_key=None, publicwww_key=None)
    events = collect(GF, cfg)
    leads = [e["lead"] for e in events if e["type"] == "lead"]
    assert all(l["on_platform"] in (True, "Y") for l in leads)
    assert len(leads) == 1


def test_done_carries_totals():
    cfg = JobConfig(source="urlscan", limit=10, keyword="", country="",
                    delay=0.0, concurrency=2, only_confirmed=False,
                    urlscan_key=None, publicwww_key=None)
    events = collect(GF, cfg)
    done = events[-1]
    assert done["checked"] == 2
    assert done["confirmed"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_runner.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/engine/runner.py`**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator

from .discover import discover_meta as _discover_meta
from .enrich import analyse, fetch as _fetch, norm_url
from .politeness import RobotsCache, RateLimiter


@dataclass
class JobConfig:
    source: str = "urlscan"
    limit: int = 200
    keyword: str = ""
    country: str = ""
    delay: float = 1.0
    concurrency: int = 5
    only_confirmed: bool = True
    urlscan_key: str | None = None
    publicwww_key: str | None = None
    manual_hosts: list = field(default_factory=list)


def lead_to_row(lead, recipe, source_query: str) -> dict:
    return {
        "name": lead.name,
        "website": lead.website,
        "on_platform": "Y" if lead.on_platform else "N",
        "matched": lead.matched,
        "email": lead.emails[0] if lead.emails else "",
        "emails_all": "; ".join(lead.emails),
        "phone": lead.phones[0] if lead.phones else "",
        "phones_all": "; ".join(lead.phones),
        "ids": "; ".join(f"{k}={v}" for k, v in lead.ids.items()),
        "address": lead.address,
        "country": lead.country,
        "socials": "; ".join(f"{k}={v}" for k, v in lead.socials.items()),
        "platform": recipe.type,
        "source_query": source_query,
        "status": "Not contacted",
        "notes": "",
    }


async def run_job(recipe, config: JobConfig, *, discover_fn=_discover_meta,
                  fetch_fn=_fetch, robots=None) -> AsyncIterator[dict]:
    robots = robots if robots is not None else RobotsCache()
    limiter = RateLimiter(config.delay)

    if config.manual_hosts:
        query = "(manual domain list)"
        raw_candidates = len(config.manual_hosts)
        hosts = list(config.manual_hosts)
    else:
        meta = discover_fn(recipe, source=config.source, limit=config.limit,
                           keyword=config.keyword, urlscan_key=config.urlscan_key,
                           publicwww_key=config.publicwww_key)
        query = meta["query"]
        raw_candidates = meta["raw_count"]
        hosts = meta["hosts"]
    source_query = query
    total = len(hosts)
    yield {"type": "progress", "checked": 0, "total": total, "confirmed": 0,
           "current_host": "", "query": query, "raw_candidates": raw_candidates,
           "log": f"Discovered {raw_candidates} candidate(s) from source; "
                  f"{total} to verify · query: {query}"}

    sem = asyncio.Semaphore(max(1, min(config.concurrency, 10)))
    state = {"checked": 0, "confirmed": 0}
    queue: asyncio.Queue = asyncio.Queue()

    async def worker(host: str):
        async with sem:
            url = norm_url(host)
            if not robots.allowed(url):
                await queue.put(("skip", host, None))
                return
            await limiter.wait()
            loop = asyncio.get_event_loop()
            final_url, html = await loop.run_in_executor(None, lambda: fetch_fn(url))
            if not html:
                await queue.put(("skip", host, None))
                return
            lead = analyse(recipe, final_url or url, html)
            await queue.put(("lead", host, lead))

    tasks = [asyncio.create_task(worker(h)) for h in hosts]

    async def closer():
        await asyncio.gather(*tasks, return_exceptions=True)
        await queue.put(("__end__", None, None))

    closer_task = asyncio.create_task(closer())

    while True:
        kind, host, payload = await queue.get()
        if kind == "__end__":
            break
        state["checked"] += 1
        if kind == "lead":
            lead = payload
            if lead.on_platform:
                state["confirmed"] += 1
            if (not config.only_confirmed) or lead.on_platform:
                yield {"type": "lead",
                       "lead": lead_to_row(lead, recipe, source_query)}
        yield {"type": "progress", "checked": state["checked"], "total": total,
               "confirmed": state["confirmed"], "current_host": host or "",
               "log": f"[{state['checked']}/{total}] {host}: "
                      f"confirmed={'Y' if kind=='lead' and payload.on_platform else 'N'}"}

    await closer_task
    yield {"type": "done", "checked": state["checked"], "total": total,
           "confirmed": state["confirmed"], "query": query,
           "raw_candidates": raw_candidates,
           "totals": {"checked": state["checked"], "confirmed": state["confirmed"],
                      "raw_candidates": raw_candidates, "query": query}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_runner.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/engine/runner.py tests/test_runner.py
git commit -m "feat(engine): job runner with concurrency + politeness"
```

---

### Task 8: Database models + built-in seeding

**Files:**
- Create: `app/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `BUILTIN_RECIPES`.
- Produces:
  - SQLModel tables `Recipe`, `Job`, `Lead` (fields per spec §6; JSON stored as `str` columns).
  - `init_db(path:str=":memory:" | file) -> Engine`
  - `get_session()` context/dependency
  - `seed_builtins(session)` — inserts built-in recipes if absent (idempotent).
  - `all_recipes(session) -> list[dict]` — built-in + custom merged for the API.

- [ ] **Step 1: Write failing test `tests/test_db.py`**

```python
from sqlmodel import Session
from app.db import init_db, seed_builtins, all_recipes, Recipe, Job


def test_seed_is_idempotent_and_lists_builtins():
    engine = init_db("sqlite://")  # in-memory
    with Session(engine) as s:
        seed_builtins(s)
        seed_builtins(s)  # twice -> no duplicates
        recipes = all_recipes(s)
        ids = [r["id"] for r in recipes]
        assert ids.count("gloriafood") == 1
        assert "calendly" in ids


def test_custom_recipe_persists():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_builtins(s)
        s.add(Recipe(id="myrec", category="Custom", type="MyTech",
                     urlscan_query="domain:x.com", publicwww_query="",
                     fingerprints_json='["x.com"]', extractors_json="{}",
                     exclude_hosts_json="[]", is_builtin=False))
        s.commit()
        ids = [r["id"] for r in all_recipes(s)]
        assert "myrec" in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/db.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, Session, create_engine, select

from app.engine.recipes import BUILTIN_RECIPES


class Recipe(SQLModel, table=True):
    id: str = Field(primary_key=True)
    category: str = ""
    type: str = ""
    logo: str = ""
    urlscan_query: str = ""
    publicwww_query: str = ""
    fingerprints_json: str = "[]"
    extractors_json: str = "{}"
    exclude_hosts_json: str = "[]"
    is_builtin: bool = False


class Job(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    recipe_id: str = ""
    source: str = "urlscan"
    filters_json: str = "{}"
    columns_json: str = "[]"
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    totals_json: str = "{}"


class Lead(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = ""
    name: str = ""
    website: str = ""
    on_platform: str = "N"
    matched: str = ""
    email: str = ""
    emails_all: str = ""
    phone: str = ""
    phones_all: str = ""
    ids_json: str = "{}"
    address: str = ""
    country: str = ""
    socials_json: str = "{}"
    source_query: str = ""
    found_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "Not contacted"
    notes: str = ""


def init_db(url: str = "sqlite:///leadscraper.db"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(url, connect_args=connect_args)
    SQLModel.metadata.create_all(engine)
    return engine


def _recipe_to_api(r: Recipe) -> dict:
    return {
        "id": r.id, "category": r.category, "type": r.type, "logo": r.logo,
        "urlscan_query": r.urlscan_query, "publicwww_query": r.publicwww_query,
        "verify_fingerprints": json.loads(r.fingerprints_json or "[]"),
        "id_extractors": json.loads(r.extractors_json or "{}"),
        "exclude_hosts": json.loads(r.exclude_hosts_json or "[]"),
        "is_builtin": r.is_builtin,
    }


def seed_builtins(session: Session) -> None:
    for br in BUILTIN_RECIPES:
        existing = session.get(Recipe, br.id)
        if existing:
            continue
        session.add(Recipe(
            id=br.id, category=br.category, type=br.type, logo=br.logo,
            urlscan_query=br.urlscan_query, publicwww_query=br.publicwww_query,
            fingerprints_json=json.dumps(br.verify_fingerprints),
            extractors_json=json.dumps(br.id_extractors),
            exclude_hosts_json=json.dumps(br.exclude_hosts),
            is_builtin=True,
        ))
    session.commit()


def all_recipes(session: Session) -> list[dict]:
    rows = session.exec(select(Recipe)).all()
    return [_recipe_to_api(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): SQLModel models + built-in seeding"
```

---

### Task 9: Schemas + Recipe-from-DB adapter

**Files:**
- Create: `app/schemas.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Consumes: `app.engine.recipes.Recipe`, DB `Recipe`.
- Produces:
  - Pydantic `RecipeCreate`, `TestRecipeRequest`, `JobCreate` (see code).
  - `engine_recipe_from_api(d:dict) -> app.engine.recipes.Recipe` — builds the pure-engine Recipe from an API/DB dict so the engine can run it.
  - `DEFAULT_COLUMNS: list[str]` — canonical output column order.

- [ ] **Step 1: Write failing test `tests/test_schemas.py`**

```python
from app.schemas import engine_recipe_from_api, DEFAULT_COLUMNS, JobCreate


def test_engine_recipe_from_api_roundtrip():
    d = {
        "id": "calendly", "category": "Booking / Scheduling", "type": "Calendly",
        "urlscan_query": "domain:assets.calendly.com", "publicwww_query": "",
        "verify_fingerprints": ["assets.calendly.com"], "id_extractors": {},
        "exclude_hosts": ["calendly.com"],
    }
    r = engine_recipe_from_api(d)
    assert r.type == "Calendly"
    assert r.verify_fingerprints == ["assets.calendly.com"]


def test_default_columns_present():
    for c in ["name", "website", "on_platform", "email", "phone", "status"]:
        assert c in DEFAULT_COLUMNS


def test_jobcreate_defaults():
    jc = JobCreate(recipe_id="gloriafood")
    assert jc.source == "urlscan"
    assert jc.limit == 200
    assert jc.only_confirmed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/schemas.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from app.engine.recipes import Recipe

DEFAULT_COLUMNS = [
    "name", "website", "on_platform", "matched", "email", "emails_all",
    "phone", "phones_all", "ids", "address", "country", "socials",
    "platform", "source_query", "status", "notes",
]


class RecipeCreate(BaseModel):
    category: str
    type: str
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = Field(default_factory=list)
    id_extractors: dict[str, str] = Field(default_factory=dict)
    exclude_hosts: list[str] = Field(default_factory=list)


class TestRecipeRequest(BaseModel):
    urlscan_query: str = ""
    publicwww_query: str = ""
    verify_fingerprints: list[str] = Field(default_factory=list)
    id_extractors: dict[str, str] = Field(default_factory=dict)
    exclude_hosts: list[str] = Field(default_factory=list)
    source: str = "urlscan"


class JobCreate(BaseModel):
    recipe_id: str
    source: str = "urlscan"
    keyword: str = ""
    country: str = ""
    limit: int = 200
    delay: float = 1.0
    concurrency: int = 5
    only_confirmed: bool = True
    manual_hosts: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=lambda: list(DEFAULT_COLUMNS))


def engine_recipe_from_api(d: dict) -> Recipe:
    return Recipe(
        id=d.get("id", "custom"),
        category=d.get("category", ""),
        type=d.get("type", ""),
        urlscan_query=d.get("urlscan_query", ""),
        publicwww_query=d.get("publicwww_query", ""),
        verify_fingerprints=list(d.get("verify_fingerprints", [])),
        id_extractors=dict(d.get("id_extractors", {})),
        exclude_hosts=list(d.get("exclude_hosts", [])),
        is_builtin=bool(d.get("is_builtin", False)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py tests/test_schemas.py
git commit -m "feat: API schemas + engine-recipe adapter"
```

---

### Task 10: FastAPI app — recipes, test, jobs, SSE, exports

**Files:**
- Create: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces a FastAPI `app` with:
  - `GET /api/recipes` → `{"grouped": {category: [recipe,...]}, "recipes": [...]}`
  - `POST /api/recipes` (RecipeCreate) → created recipe dict
  - `POST /api/recipes/test` (TestRecipeRequest) → `{"checked": n, "matched": m, "samples": [...]}`
  - `POST /api/jobs` (JobCreate) → `{"job_id": ...}` (starts background task)
  - `GET /api/jobs/{id}/stream` → SSE
  - `GET /api/jobs/{id}/results.xlsx` / `.csv`
  - `POST /api/jobs/{id}/append` (multipart file) → merged xlsx
  - `GET /` → serves `static/index.html`
- Uses an in-process `JOBS: dict[str, dict]` holding `{config, recipe, columns, queue, rows, status, totals}`.

- [ ] **Step 1: Write failing test `tests/test_api.py`**

```python
from fastapi.testclient import TestClient

import app.main as main


def client():
    return TestClient(main.app)


def test_recipes_endpoint_lists_builtins():
    c = client()
    r = c.get("/api/recipes")
    assert r.status_code == 200
    data = r.json()
    ids = [x["id"] for x in data["recipes"]]
    assert "gloriafood" in ids
    assert "Online Ordering / Restaurants" in data["grouped"]


def test_create_custom_recipe():
    c = client()
    body = {"category": "Custom", "type": "Calendly Custom",
            "urlscan_query": "domain:assets.calendly.com",
            "verify_fingerprints": ["assets.calendly.com"]}
    r = c.post("/api/recipes", json=body)
    assert r.status_code == 200
    assert r.json()["type"] == "Calendly Custom"


def test_index_served():
    c = client()
    r = c.get("/")
    assert r.status_code == 200
    assert "Lead Scraper" in r.text


def test_job_run_with_manual_hosts():
    # manual_hosts bypasses discovery; FETCH_OVERRIDE avoids the network entirely.
    def fake_fetch(url, **kwargs):
        return url, ('<html><title>Mario</title><body>'
                     '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
                     '<a href="mailto:info@marios.com">e</a></body></html>')

    main.FETCH_OVERRIDE = fake_fetch
    try:
        c = client()
        rj = c.post("/api/jobs", json={"recipe_id": "gloriafood",
                                       "manual_hosts": ["marios.com"],
                                       "delay": 0.0, "only_confirmed": True})
        job_id = rj.json()["job_id"]
        # drain SSE
        with c.stream("GET", f"/api/jobs/{job_id}/stream") as resp:
            body = "".join(chunk for chunk in resp.iter_text())
        assert "done" in body
        assert "(manual domain list)" in body  # query surfaced
        # results downloadable
        rx = c.get(f"/api/jobs/{job_id}/results.csv")
        assert rx.status_code == 200
        assert "marios.com" in rx.text
    finally:
        main.FETCH_OVERRIDE = None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `app/main.py`**

```python
from __future__ import annotations

import asyncio
import io
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import (FileResponse, StreamingResponse, Response,
                               JSONResponse)
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.db import init_db, seed_builtins, all_recipes, Recipe
from app.engine.discover import discover, discover_urlscan, discover_publicwww
from app.engine.enrich import fetch, analyse, norm_url
from app.engine.export import rows_to_csv, rows_to_xlsx, append_xlsx
from app.engine.recipes import recipes_by_category
from app.engine.runner import run_job, JobConfig, lead_to_row
from app.schemas import (RecipeCreate, TestRecipeRequest, JobCreate,
                         engine_recipe_from_api, DEFAULT_COLUMNS)

load_dotenv()
STATIC_DIR = Path(__file__).parent / "static"
URLSCAN_KEY = os.getenv("URLSCAN_KEY") or None
PUBLICWWW_KEY = os.getenv("PUBLICWWW_KEY") or None

app = FastAPI(title="Lead Scraper")
engine = init_db()
with Session(engine) as _s:
    seed_builtins(_s)

JOBS: dict[str, dict] = {}
FETCH_OVERRIDE = None  # tests may set this to bypass network


def _recipe_dict(recipe_id: str) -> dict | None:
    with Session(engine) as s:
        r = s.get(Recipe, recipe_id)
        if not r:
            return None
        return {
            "id": r.id, "category": r.category, "type": r.type,
            "urlscan_query": r.urlscan_query, "publicwww_query": r.publicwww_query,
            "verify_fingerprints": json.loads(r.fingerprints_json or "[]"),
            "id_extractors": json.loads(r.extractors_json or "{}"),
            "exclude_hosts": json.loads(r.exclude_hosts_json or "[]"),
            "is_builtin": r.is_builtin,
        }


@app.get("/api/recipes")
def list_recipes():
    with Session(engine) as s:
        recipes = all_recipes(s)
    grouped: dict[str, list] = {}
    for r in recipes:
        grouped.setdefault(r["category"], []).append(r)
    return {"recipes": recipes, "grouped": grouped}


@app.post("/api/recipes")
def create_recipe(body: RecipeCreate):
    rid = body.type.lower().replace(" ", "_") + "_" + uuid.uuid4().hex[:6]
    with Session(engine) as s:
        s.add(Recipe(
            id=rid, category=body.category, type=body.type,
            urlscan_query=body.urlscan_query, publicwww_query=body.publicwww_query,
            fingerprints_json=json.dumps(body.verify_fingerprints),
            extractors_json=json.dumps(body.id_extractors),
            exclude_hosts_json=json.dumps(body.exclude_hosts),
            is_builtin=False,
        ))
        s.commit()
    return _recipe_dict(rid)


@app.post("/api/recipes/test")
def test_recipe(body: TestRecipeRequest):
    recipe = engine_recipe_from_api(body.model_dump())
    try:
        hosts = discover(recipe, source=body.source, limit=5,
                         urlscan_key=URLSCAN_KEY, publicwww_key=PUBLICWWW_KEY)
    except Exception as e:
        raise HTTPException(400, f"Discovery failed: {e}")
    fetch_fn = FETCH_OVERRIDE or fetch
    samples = []
    matched = 0
    for h in hosts:
        final_url, html = fetch_fn(norm_url(h))
        if not html:
            samples.append({"host": h, "confirmed": False, "matched": ""})
            continue
        lead = analyse(recipe, final_url or h, html)
        if lead.on_platform:
            matched += 1
        samples.append({"host": h, "confirmed": lead.on_platform,
                        "matched": lead.matched})
    return {"checked": len(hosts), "matched": matched, "samples": samples}


@app.post("/api/jobs")
def create_job(body: JobCreate):
    rd = _recipe_dict(body.recipe_id)
    if not rd:
        raise HTTPException(404, "recipe not found")
    recipe = engine_recipe_from_api(rd)
    columns = body.columns or list(DEFAULT_COLUMNS)
    config = JobConfig(
        source=body.source, limit=min(body.limit, 1000), keyword=body.keyword,
        country=body.country, delay=body.delay,
        concurrency=min(body.concurrency, 10), only_confirmed=body.only_confirmed,
        urlscan_key=URLSCAN_KEY, publicwww_key=PUBLICWWW_KEY,
        manual_hosts=[h.strip() for h in body.manual_hosts if h.strip()],
    )
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"recipe": recipe, "config": config, "columns": columns,
                    "rows": [], "status": "pending", "totals": {}}
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")

    async def event_gen():
        job["status"] = "running"
        fetch_fn = FETCH_OVERRIDE or fetch
        # run_job defaults discover_fn to discover_meta (real network); when the
        # job carries manual_hosts, discovery is bypassed entirely.
        try:
            async for ev in run_job(job["recipe"], job["config"],
                                    fetch_fn=fetch_fn):
                if ev["type"] == "lead":
                    job["rows"].append(ev["lead"])
                if ev["type"] == "done":
                    job["status"] = "done"
                    job["totals"] = ev["totals"]
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
        except Exception as e:  # surface engine errors to the client
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _job_rows(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs/{job_id}/results.csv")
def results_csv(job_id: str):
    job = _job_rows(job_id)
    data = rows_to_csv(job["columns"], job["rows"])
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition":
                             f'attachment; filename="leads_{job_id}.csv"'})


@app.get("/api/jobs/{job_id}/results.xlsx")
def results_xlsx(job_id: str):
    job = _job_rows(job_id)
    sheet = f"{job['recipe'].type} Prospects"
    data = rows_to_xlsx(sheet, job["columns"], job["rows"])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="leads_{job_id}.xlsx"'})


@app.post("/api/jobs/{job_id}/append")
async def append_tracker(job_id: str, file: UploadFile = File(...)):
    job = _job_rows(job_id)
    existing = await file.read()
    sheet = f"{job['recipe'].type} Prospects"
    merged = append_xlsx(existing, sheet, job["rows"])
    return Response(
        content=merged,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="tracker_{job_id}.xlsx"'})


# static + index (mounted last so /api/* wins)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"detail": "UI not built"}, status_code=200)
```

> Note for the implementer: the API test avoids the network by (a) passing
> `manual_hosts` so `run_job` bypasses discovery, and (b) setting
> `main.FETCH_OVERRIDE` so `fetch` is never called. Ensure the stream handler
> reads `FETCH_OVERRIDE` at call time (it does, via `FETCH_OVERRIDE or fetch`).
> `discover`/`discover_urlscan`/`discover_publicwww` remain imported for the
> `/api/recipes/test` endpoint. The `done` SSE frame includes the `query` and
> `raw_candidates` fields produced by the runner.

- [ ] **Step 4: Create placeholder `app/static/index.html`** (real UI in Task 11; needed for `test_index_served`)

```html
<!doctype html><html><head><meta charset="utf-8"><title>Lead Scraper</title></head>
<body><h1>Lead Scraper</h1></body></html>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: PASS (4 tests). If the SSE streaming test is flaky under TestClient, the implementer may assert on `job["status"] == "done"` after draining instead.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/static/index.html tests/test_api.py
git commit -m "feat(api): FastAPI routes, SSE, exports, recipe test"
```

---

### Task 11: Frontend — single-page 4-step wizard + live results

**Files:**
- Modify/replace: `app/static/index.html`
- Create: `app/static/app.js`, `app/static/styles.css`
- Test: manual (browser) + the existing `test_index_served` keeps passing.

**Interfaces:**
- Consumes the REST API from Task 10. No build step; Tailwind via CDN.

- [ ] **Step 1: Replace `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lead Scraper</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body class="bg-slate-50 text-slate-800">
  <div class="flex min-h-screen">
    <!-- Sidebar -->
    <aside class="hidden md:flex w-56 flex-col bg-white border-r border-slate-200 p-4">
      <div class="text-lg font-semibold text-emerald-600 mb-6">Lead Scraper</div>
      <nav class="space-y-1 text-sm">
        <a class="block px-3 py-2 rounded-lg bg-emerald-50 text-emerald-700 font-medium">Search</a>
        <a class="block px-3 py-2 rounded-lg text-slate-500">Jobs</a>
        <a class="block px-3 py-2 rounded-lg text-slate-500">Recipes</a>
        <a class="block px-3 py-2 rounded-lg text-slate-500">Settings</a>
      </nav>
    </aside>

    <!-- Main -->
    <main class="flex-1 p-6 grid grid-cols-1 lg:grid-cols-5 gap-6">
      <!-- Config wizard -->
      <section class="lg:col-span-2 space-y-4">
        <h1 class="text-xl font-semibold">Find leads</h1>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
          <h2 class="font-medium">1 · What to find</h2>
          <label class="block text-sm">Category
            <select id="category" class="mt-1 w-full border rounded-lg p-2"></select>
          </label>
          <label class="block text-sm">Type
            <select id="type" class="mt-1 w-full border rounded-lg p-2"></select>
          </label>
          <button id="customBtn" class="text-emerald-600 text-sm underline">+ Custom recipe</button>
          <div id="fingerprints" class="text-xs text-slate-500"></div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
          <h2 class="font-medium">2 · Where / filters</h2>
          <label class="block text-sm">Discovery source
            <select id="source" class="mt-1 w-full border rounded-lg p-2">
              <option value="urlscan">urlscan.io (free)</option>
              <option value="publicwww">PublicWWW (needs key)</option>
            </select>
          </label>
          <label class="block text-sm">Country / region (optional)
            <input id="country" class="mt-1 w-full border rounded-lg p-2" placeholder="e.g. US" />
          </label>
          <label class="block text-sm">Vertical / keyword (optional)
            <input id="keyword" class="mt-1 w-full border rounded-lg p-2" placeholder="e.g. pizza" />
          </label>
          <label class="block text-sm">Max results: <span id="limitVal">200</span>
            <input id="limit" type="range" min="10" max="1000" value="200" class="w-full" />
          </label>
          <div class="flex gap-3">
            <label class="text-sm flex-1">Delay (s)
              <input id="delay" type="number" step="0.5" value="1.0" class="mt-1 w-full border rounded-lg p-2" />
            </label>
            <label class="text-sm flex-1">Concurrency
              <input id="concurrency" type="number" min="1" max="10" value="5" class="mt-1 w-full border rounded-lg p-2" />
            </label>
          </div>
          <label class="text-sm flex items-center gap-2">
            <input id="onlyConfirmed" type="checkbox" checked /> Only export confirmed leads
          </label>
          <details class="text-sm">
            <summary class="cursor-pointer text-slate-500">Manual domains (bypass discovery)</summary>
            <textarea id="manualHosts" rows="3" class="mt-1 w-full border rounded-lg p-2 font-mono text-xs"
              placeholder="one host per line, e.g.&#10;marios-pizza.com&#10;joes-diner.com"></textarea>
            <p class="text-xs text-slate-400 mt-1">If filled, discovery is skipped and only these
              hosts are verified/enriched — useful for validating the engine on known sites.</p>
          </details>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-2">
          <h2 class="font-medium">3 · Fields to extract</h2>
          <div id="columns" class="grid grid-cols-2 gap-1 text-xs"></div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
          <h2 class="font-medium">4 · Run</h2>
          <p class="text-xs text-slate-500">You are responsible for complying with the data
            sources' Terms of Service (urlscan, PublicWWW) and applicable law (GDPR/CAN-SPAM)
            when contacting leads. Only publicly published contact info is collected.</p>
          <button id="runBtn" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg py-2 font-medium">Run</button>
        </div>
      </section>

      <!-- Results -->
      <section class="lg:col-span-3 space-y-4">
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <div class="flex items-center justify-between mb-2">
            <h2 class="font-medium">Results</h2>
            <div class="space-x-2">
              <button id="dlXlsx" disabled class="text-sm px-3 py-1 rounded-lg border disabled:opacity-40">Download .xlsx</button>
              <button id="dlCsv" disabled class="text-sm px-3 py-1 rounded-lg border disabled:opacity-40">Download .csv</button>
            </div>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-2 mb-2">
            <div id="bar" class="bg-emerald-500 h-2 rounded-full" style="width:0%"></div>
          </div>
          <div id="summary" class="text-sm text-slate-600 mb-2">Idle.</div>
          <div class="overflow-auto max-h-[45vh] border rounded-lg">
            <table class="w-full text-xs">
              <thead class="bg-slate-100 sticky top-0">
                <tr>
                  <th class="text-left p-2">Confirmed</th>
                  <th class="text-left p-2">Name</th>
                  <th class="text-left p-2">Website</th>
                  <th class="text-left p-2">Email</th>
                  <th class="text-left p-2">Phone</th>
                </tr>
              </thead>
              <tbody id="rows"></tbody>
            </table>
          </div>
        </div>
        <div class="bg-slate-900 text-emerald-300 rounded-xl p-3 font-mono text-xs h-40 overflow-auto" id="log"></div>
      </section>
    </main>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `app/static/styles.css`**

```css
/* small supplements to Tailwind CDN */
body { font-family: Inter, system-ui, -apple-system, sans-serif; }
#log::-webkit-scrollbar { width: 8px; }
#log::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
```

- [ ] **Step 3: Create `app/static/app.js`**

```javascript
const DEFAULT_COLUMNS = [
  "name","website","on_platform","matched","email","emails_all",
  "phone","phones_all","ids","address","country","socials",
  "platform","source_query","status","notes",
];

let RECIPES = [];
let GROUPED = {};
let currentJob = null;

const $ = (id) => document.getElementById(id);

async function loadRecipes() {
  const res = await fetch("/api/recipes");
  const data = await res.json();
  RECIPES = data.recipes;
  GROUPED = data.grouped;
  const cat = $("category");
  cat.innerHTML = "";
  Object.keys(GROUPED).forEach((c) => {
    const o = document.createElement("option");
    o.value = c; o.textContent = c; cat.appendChild(o);
  });
  populateTypes();
}

function populateTypes() {
  const cat = $("category").value;
  const type = $("type");
  type.innerHTML = "";
  (GROUPED[cat] || []).forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id; o.textContent = r.type; type.appendChild(o);
  });
  showFingerprints();
}

function selectedRecipe() {
  const id = $("type").value;
  return RECIPES.find((r) => r.id === id);
}

function showFingerprints() {
  const r = selectedRecipe();
  $("fingerprints").textContent = r
    ? "Matches if page contains: " + r.verify_fingerprints.join(", ")
    : "";
}

function buildColumns() {
  const box = $("columns");
  box.innerHTML = "";
  DEFAULT_COLUMNS.forEach((c) => {
    const id = "col_" + c;
    const label = document.createElement("label");
    label.className = "flex items-center gap-1";
    label.innerHTML = `<input type="checkbox" id="${id}" checked /> ${c}`;
    box.appendChild(label);
  });
}

function selectedColumns() {
  return DEFAULT_COLUMNS.filter((c) => $("col_" + c)?.checked);
}

function chip(confirmed) {
  const yes = confirmed === "Y" || confirmed === true;
  const cls = yes ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500";
  return `<span class="px-2 py-0.5 rounded-full ${cls}">${yes ? "Y" : "N"}</span>`;
}

function addRow(lead) {
  const tr = document.createElement("tr");
  tr.className = "border-t";
  tr.innerHTML =
    `<td class="p-2">${chip(lead.on_platform)}</td>` +
    `<td class="p-2">${lead.name || ""}</td>` +
    `<td class="p-2"><a class="text-emerald-600 underline" href="${lead.website}" target="_blank">${lead.website}</a></td>` +
    `<td class="p-2">${lead.email || ""}</td>` +
    `<td class="p-2">${lead.phone || ""}</td>`;
  $("rows").appendChild(tr);
}

function logLine(msg) {
  const el = $("log");
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}

async function runJob() {
  $("rows").innerHTML = "";
  $("log").textContent = "";
  $("bar").style.width = "0%";
  $("dlXlsx").disabled = true;
  $("dlCsv").disabled = true;

  const manualHosts = ($("manualHosts").value || "")
    .split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
  const body = {
    recipe_id: $("type").value,
    source: $("source").value,
    keyword: $("keyword").value,
    country: $("country").value,
    limit: parseInt($("limit").value, 10),
    delay: parseFloat($("delay").value),
    concurrency: parseInt($("concurrency").value, 10),
    only_confirmed: $("onlyConfirmed").checked,
    manual_hosts: manualHosts,
    columns: selectedColumns(),
  };
  const res = await fetch("/api/jobs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const { job_id } = await res.json();
  currentJob = job_id;

  let lastQuery = "";
  let rawCandidates = null;
  const es = new EventSource(`/api/jobs/${job_id}/stream`);
  es.addEventListener("progress", (e) => {
    const d = JSON.parse(e.data);
    if (d.query !== undefined) lastQuery = d.query;
    if (d.raw_candidates !== undefined) rawCandidates = d.raw_candidates;
    const pct = d.total ? Math.round((d.checked / d.total) * 100) : 0;
    $("bar").style.width = pct + "%";
    $("summary").textContent = `${d.checked}/${d.total} checked · ${d.confirmed} confirmed`;
    if (d.log) logLine(d.log);
  });
  es.addEventListener("lead", (e) => addRow(JSON.parse(e.data).lead));
  es.addEventListener("done", (e) => {
    const d = JSON.parse(e.data);
    const raw = d.raw_candidates ?? rawCandidates ?? d.total;
    const q = d.query || lastQuery;
    let msg;
    if (raw === 0) {
      // discovery genuinely returned nothing — NOT an engine failure
      msg = `0 candidates found for query: ${q}. Try a different source, keyword, or manual domains.`;
    } else if (d.confirmed === 0) {
      msg = `${raw} candidate(s) found, ${d.checked} checked, 0 confirmed on platform (query: ${q}).`;
    } else {
      msg = `Done — ${raw} candidate(s), ${d.checked} checked, ${d.confirmed} confirmed (query: ${q}).`;
    }
    $("summary").textContent = msg;
    $("dlXlsx").disabled = false;
    $("dlCsv").disabled = false;
    es.close();
  });
  es.addEventListener("error", () => { logLine("[stream closed]"); es.close(); });
}

async function customRecipe() {
  const type = prompt("Type name (e.g. Calendly):");
  if (!type) return;
  const fp = prompt("Verify fingerprint (e.g. assets.calendly.com):");
  if (!fp) return;
  const urlscan = prompt("urlscan query:", `domain:${fp}`) || `domain:${fp}`;
  const body = { category: "Custom", type, urlscan_query: urlscan,
                 verify_fingerprints: [fp] };
  // test before saving
  const test = await fetch("/api/recipes/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, source: "urlscan" }),
  }).then((r) => r.json());
  if (!confirm(`Test: ${test.matched}/${test.checked} candidates matched. Save recipe?`))
    return;
  await fetch("/api/recipes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadRecipes();
}

function wire() {
  $("category").addEventListener("change", populateTypes);
  $("type").addEventListener("change", showFingerprints);
  $("limit").addEventListener("input", () => $("limitVal").textContent = $("limit").value);
  $("runBtn").addEventListener("click", runJob);
  $("customBtn").addEventListener("click", customRecipe);
  $("dlXlsx").addEventListener("click", () => currentJob && (window.location = `/api/jobs/${currentJob}/results.xlsx`));
  $("dlCsv").addEventListener("click", () => currentJob && (window.location = `/api/jobs/${currentJob}/results.csv`));
}

buildColumns();
wire();
loadRecipes();
```

- [ ] **Step 4: Run the existing API test to confirm index still served**

Run: `.venv/Scripts/python -m pytest tests/test_api.py::test_index_served -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/static/index.html app/static/app.js app/static/styles.css
git commit -m "feat(ui): single-page 4-step wizard + live results"
```

---

### Task 12: README, manual run, full-suite verification

**Files:**
- Create: `README.md`
- Test: full suite + manual smoke run.

**Interfaces:** none new.

- [ ] **Step 1: Create `README.md`**

```markdown
# Lead Scraper

Find businesses running a specific web technology, verify it, scrape public
contact details, and export to Excel/CSV.

## Requirements
- Python 3.11 (Windows: `py -3.11`)

## Setup
```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Run
```bash
.venv/Scripts/python -m uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## API keys (optional)
Copy `.env.example` to `.env`. urlscan.io free search needs no key.
Set `PUBLICWWW_KEY` to use PublicWWW; `URLSCAN_KEY` raises urlscan rate limits.

## Tests
```bash
.venv/Scripts/python -m pytest -q
```

## Compliance
You are responsible for complying with urlscan/PublicWWW Terms of Service and
applicable law (GDPR/CAN-SPAM). Only publicly published contact info is collected.
The Status column lets the sheet double as an outreach tracker.
```

- [ ] **Step 2: Run the full test suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 3: Engine validation via MANUAL domains (no discovery, no urlscan)**

This isolates the verify/enrich half so a thin urlscan index can't be mistaken
for an engine bug. Start the server: `.venv/Scripts/python -m uvicorn app.main:app`.
In the browser, Type "GloriaFood", expand **Manual domains (bypass discovery)**, and
paste 5–10 hand-picked domains known to run GloriaFood (the human partner supplies
these). Click Run.

Expected: the summary reads `(manual domain list)` as the query, every pasted host is
checked, and the confirmed ones show a Y chip with emails/phones. Download .xlsx and
confirm the `GloriaFood Prospects` tab. This proves fetch + analyse + extract + export
work independently of discovery.

- [ ] **Step 4: Verify the candidate-accounting distinction**

Confirm the UI shows two genuinely different end states:
- A query with no index hits → summary `0 candidates found for query: …` (not an error/empty hang).
- A run with hits but none matching → summary `N candidate(s) found, … 0 confirmed`.
Use a deliberately obscure custom fingerprint to force the first case if needed.

- [ ] **Step 5: HOLD — live urlscan discovery run (requires human GO)**

⚠️ Do NOT run this step until the human partner explicitly says go. Then:
1. Category "Online Ordering / Restaurants" → Type "GloriaFood", source "urlscan (free)",
   Max results 25, Run. Watch progress; note the surfaced query + raw candidate count.
2. Click "+ Custom recipe", create Calendly (`assets.calendly.com`), accept the test
   result, run it.

Expected: progress streams; the summary distinguishes "0 candidates" from "found, none
confirmed"; xlsx downloads.

- [ ] **Step 6: HOLD — ground-truth parity vs the original script (requires the original `gloriafood_finder.py`)**

⚠️ Requires the human partner to place their original `gloriafood_finder.py` in the repo
(it is NOT present in this workspace — see spec §11). Then run BOTH at limit ~25 over the
same urlscan query and diff the **confirmed-domain sets**:

```bash
# original script — export confirmed GloriaFood domains to a sorted list
.venv/Scripts/python gloriafood_finder.py discover --limit 25 > original_hosts.txt
# new tool — run GloriaFood at limit 25, download results.csv, extract confirmed websites
# (use the UI or call POST /api/jobs then GET results.csv), then:
#   compare the set of confirmed website hosts from each, sorted
```

Acceptance: the two confirmed-domain sets match (allowing for ordering and urlscan index
drift between the two runs — re-run close together). A mismatch beyond index drift means
the port diverged; investigate fingerprints/normalization before declaring parity.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: README + run instructions"
```

---

## Self-Review

**Spec coverage:**
- Recipe object + built-in library + grouping → Task 2 ✓
- Custom recipe builder + Test recipe → Task 10 (`/api/recipes`, `/api/recipes/test`) + Task 11 (`customRecipe()`) ✓
- Discovery (urlscan free + publicwww, dedup, exclude_hosts) → Task 4 ✓
- Verify/enrich (fingerprints, name, emails filtered, phones, ids, socials) → Task 3 ✓
- Politeness (robots, rate limit, concurrency, UA, timeouts) → Task 5 + Task 7 ✓
- Export xlsx (`<Type> Prospects` tab) + csv + append preserving order → Task 6 ✓
- Data model Recipe/Job/Lead → Task 8 ✓
- REST API (recipes, test, jobs, SSE stream, results.xlsx/csv, append) → Task 10 ✓
- 4-step wizard UI + live progress + streaming table + downloads + disclaimer → Task 11 ✓
- Selectable output columns → Task 9 (DEFAULT_COLUMNS) + Task 11 ✓
- README + .env.example → Task 1 + Task 12 ✓
- Acceptance test (GloriaFood end-to-end + Calendly custom) → Task 12 Step 5 ✓
- Manual-domain bypass (verify/enrich without discovery) → Task 7 (`manual_hosts`) + Task 10 (`JobCreate.manual_hosts`) + Task 11 (textarea) + Task 12 Step 3 ✓
- Candidate accounting (surface query + raw count; distinguish "0 candidates" vs "found, 0 confirmed") → Task 4 (`discover_meta`) + Task 7 (progress/done events) + Task 11 (summary logic) + Task 12 Step 4 ✓
- Live run held for explicit go + ground-truth parity vs original script → Task 12 Steps 5–6 ✓

**Deferred (documented in spec §10):** rich Jobs/History screen, per-recipe logos, full Settings page. Jobs are persisted in-process for the session; a `Job`/`Lead` DB-persistence pass and history UI are a follow-up plan.

**Placeholder scan:** No "TBD"/"implement later"; every code step shows real code. The Task 10 SSE test note offers a fallback assertion if TestClient streaming is flaky — that is guidance, not a placeholder.

**Type consistency:** `lead_to_row` keys match `DEFAULT_COLUMNS` and the table renderer's `on_platform`/`email`/`phone` keys. `JobConfig` fields match `JobCreate` + `create_job` construction. `engine_recipe_from_api` field names match `Recipe` dataclass. `discover()` signature is consistent across Task 4 (def), Task 7 (call), Task 10 (call).

**Known follow-ups (not blockers):**
- Job/Lead rows are kept in the in-process `JOBS` dict for download; persisting them to the SQLite `Job`/`Lead` tables (already defined) enables the Jobs/History page — next plan.
- `country` filter is captured but only lightly applied (keyword/heuristic); a stronger geo filter is a follow-up.
```
