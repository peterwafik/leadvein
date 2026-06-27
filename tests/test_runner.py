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


def test_worker_exception_is_counted_not_dropped():
    GF_local = GF
    def boom_fetch(url, **kwargs):
        raise RuntimeError("boom")
    cfg = JobConfig(source="urlscan", limit=10, keyword="", country="",
                    delay=0.0, concurrency=2, only_confirmed=False,
                    urlscan_key=None, publicwww_key=None)
    async def _run():
        events = []
        async for ev in run_job(GF_local, cfg, discover_fn=fake_discover,
                                fetch_fn=boom_fetch, robots=AllowAllRobots()):
            events.append(ev)
        return events
    events = asyncio.run(_run())
    done = events[-1]
    assert done["type"] == "done"
    assert done["checked"] == done["total"]   # nothing silently dropped
    assert done["checked"] == 2
