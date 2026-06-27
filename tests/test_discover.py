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
    assert meta["raw_count"] == 2
    assert meta["hosts"] == ["marios.com"]
