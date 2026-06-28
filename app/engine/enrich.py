from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

USER_AGENT = ("LeadScraper/0.1 (+https://example.com/contact; "
              "youssef.zaki@student.giu-uni.de)")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")
# Universal junk/infra domains that are never a real business contact — platform-AGNOSTIC.
# Per-recipe vendor hosts (the recipe's own CDN / exclude domains) are added dynamically
# from the recipe in analyse(); platform-specific tokens MUST NOT be hardcoded here.
GLOBAL_EMAIL_BLOCKLIST = ("sentry", "wixpress", "cloudflare", "gstatic",
                          "googleapis", "w3.org", "schema.org",
                          "sentry.io", "cloudfront")

PLACEHOLDER_EMAILS = {
    "user@domain.com", "name@domain.com", "email@domain.com",
    "name@email.com", "you@email.com", "email@example.com",
    "you@example.com", "yourname@example.com", "example@example.com",
    "john@doe.com", "johndoe@example.com", "firstname.lastname@example.com",
}
PLACEHOLDER_DOMAINS = {
    "domain.com", "example.com", "example.org", "example.net",
    "email.com", "yourdomain.com", "yourcompany.com", "company.com",
}

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


def _clean_emails(candidates: list[str], extra_blocklist: tuple = ()) -> list[str]:
    # global junk + the current recipe's own vendor/exclude hosts (added by analyse)
    blocklist = tuple(GLOBAL_EMAIL_BLOCKLIST) + tuple(t.lower() for t in extra_blocklist)
    out: list[str] = []
    for e in candidates:
        e = e.strip().strip(".,;:").lower()
        low = e.lower()
        if low.endswith(IMAGE_EXTS):
            continue
        if any(tok in low for tok in blocklist):
            continue
        if e in PLACEHOLDER_EMAILS:
            continue
        domain = e.split("@")[-1]
        if domain in PLACEHOLDER_DOMAINS:
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

    for fp in recipe.verify_fingerprints:
        if fp.lower() in low:
            lead.on_platform = True
            lead.matched = fp
            break

    soup = BeautifulSoup(html, "lxml")
    lead.name = _extract_name(soup)

    email_candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            email_candidates.append(href[7:].split("?")[0])
    email_candidates += EMAIL_RE.findall(html)
    # the recipe's own vendor hosts (exclude_hosts + fingerprints) are filtered out of
    # emails too — so each platform drops its own vendor/infra addresses generically
    recipe_email_blocklist = tuple(
        t.lower() for t in (list(recipe.exclude_hosts) + list(recipe.verify_fingerprints))
    )
    lead.emails = _clean_emails(email_candidates, recipe_email_blocklist)

    phones: list[str] = []
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            p = unquote(a["href"][4:]).strip()
            p = " ".join(p.split())  # collapse any runs of whitespace
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

    for label, pattern in recipe.id_extractors.items():
        try:
            m = re.search(pattern, html)
            if m and m.groups():
                lead.ids[label] = m.group(1)
        except re.error:
            continue

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
