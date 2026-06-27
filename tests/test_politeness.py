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
