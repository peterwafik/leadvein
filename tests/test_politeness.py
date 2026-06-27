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
    delay = 0.1
    async def run():
        rl = RateLimiter(delay)
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        await rl.wait()  # first call returns immediately
        await rl.wait()  # second call must wait ~delay
        return loop.time() - t0
    elapsed = asyncio.run(run())
    # Allow a small slack for OS timer granularity (asyncio.sleep can wake a
    # hair early on Windows); still far above 0, which proves the limiter waited.
    assert elapsed >= delay * 0.9
