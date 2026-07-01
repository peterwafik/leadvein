import pytest
from app.core.targeting import registry


class _Fake:
    key = "x.demo"; group = "demo"; label = "Demo"; reads = ["intent.ssl"]; params_schema = {}
    def matches(self, view, params): return True


def test_register_get_all_and_available():
    registry.clear()
    p = _Fake()
    registry.register(p)
    assert registry.get("x.demo") is p
    assert registry.all_keys() == ["x.demo"]
    assert registry.available({"intent.ssl", "city"}) == [p]      # reads satisfied
    assert registry.available({"city"}) == []                     # reads not populated
    with pytest.raises(KeyError):
        registry.get("nope")
