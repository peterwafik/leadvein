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
