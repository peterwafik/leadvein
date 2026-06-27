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
                # Normalize: strip www. and lowercase
                dom = dom.lower()
                if dom.startswith("www."):
                    dom = dom[4:]
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
