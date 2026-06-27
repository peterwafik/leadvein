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
    country: str = ""  # reserved for future geo-filtering; captured but not yet applied to discovery
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
            loop = asyncio.get_running_loop()
            try:
                final_url, html = await loop.run_in_executor(None, lambda: fetch_fn(url))
            except Exception:
                await queue.put(("skip", host, None))
                return
            if not html:
                await queue.put(("skip", host, None))
                return
            try:
                lead = analyse(recipe, final_url or url, html)
            except Exception:
                await queue.put(("skip", host, None))
                return
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
