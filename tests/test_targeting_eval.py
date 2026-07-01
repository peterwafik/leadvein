from app.core.targeting import registry
from app.core.targeting.composition import (evaluate, selects,
                                            kleene_and, kleene_or, kleene_not)
from app.core.targeting.view import get_path, MISSING


class _Signal:
    # returns True/False from view["intent"][name], or None when the path is absent (un-enriched)
    def __init__(self, key, name):
        self.key = key; self.group = "web"; self.label = key
        self.reads = [f"intent.{name}"]; self.params_schema = {}; self._name = name
    def matches(self, view, params):
        val = get_path(view, f"intent.{self._name}")
        return None if val is MISSING else bool(val)


def _setup():
    registry.clear()
    registry.register(_Signal("web.ecom", "ecommerce_detected"))


def test_kleene_truth_tables():
    assert kleene_not(True) is False and kleene_not(False) is True and kleene_not(None) is None
    assert kleene_and([True, True]) is True
    assert kleene_and([True, False]) is False
    assert kleene_and([True, None]) is None
    assert kleene_and([False, None]) is False
    assert kleene_and([]) is True                    # empty AND -> True
    assert kleene_or([False, None]) is None
    assert kleene_or([True, None]) is True
    assert kleene_or([False, False]) is False
    assert kleene_or([]) is False                    # empty OR -> False


def test_include_iff_true_and_empty_composition():
    _setup()
    assert selects({}, {"op": "AND", "nodes": []}) is True      # empty composition matches all


def test_not_signal_excludes_unenriched_leads():
    _setup()
    enriched_true = {"intent": {"ecommerce_detected": True}}
    enriched_false = {"intent": {"ecommerce_detected": False}}
    unenriched = {"intent": {}}                                  # signal ABSENT
    comp = {"op": "AND", "nodes": [{"predicate": "web.ecom", "negate": True}]}
    # NOT ecommerce -> only leads KNOWN not to have it; never un-enriched
    assert selects(enriched_false, comp) is True
    assert selects(enriched_true, comp) is False
    assert selects(unenriched, comp) is False                    # <-- the invariant
    # positive filter likewise excludes un-enriched
    pos = {"op": "AND", "nodes": [{"predicate": "web.ecom"}]}
    assert selects(unenriched, pos) is False
    assert selects(enriched_true, pos) is True
