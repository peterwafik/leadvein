from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.view import lead_view
from app.core.db import Lead
import json


def _view(**kw):
    base = dict(city="London", country="GB", phone="", public_email="", score_total=50,
                attributes_json="{}", intent_json="{}", subscores_json="{}",
                category_keys_json="[]")
    base.update(kw)
    return lead_view(Lead(**base))


def test_predicates_registered():
    registry.clear(); register_targeting_runtime()
    for k in ["geo.country", "geo.city", "quality.min_score", "freshness.verified_within",
              "category.any", "contactability.has_business_contact", "web.has_signal",
              "web.is_enriched", "contactability.has_role_email"]:
        assert registry.get(k)


def test_geo_and_score_predicates():
    registry.clear(); register_targeting_runtime()
    v = _view(country="GB", city="London", score_total=80)
    assert registry.get("geo.country").matches(v, {"value": "GB"}) is True
    assert registry.get("geo.country").matches(v, {"value": "FR"}) is False
    assert registry.get("quality.min_score").matches(v, {"min": 70}) is True
    assert registry.get("quality.min_score").matches(v, {"min": 90}) is False


def test_role_email_allowlist_invariant():   # INV-2
    registry.clear(); register_targeting_runtime()
    p = registry.get("contactability.has_role_email")
    assert p.matches(_view(public_email="info@acme.com"), {}) is True
    assert p.matches(_view(public_email="sales@acme.com"), {}) is True
    assert p.matches(_view(public_email="john.smith@acme.com"), {}) is False   # personal -> NOT role
    assert p.matches(_view(public_email=""), {}) is None                        # absent -> unknown


def test_web_signal_is_tristate():
    registry.clear(); register_targeting_runtime()
    p = registry.get("web.has_signal")
    assert p.matches(_view(intent_json=json.dumps({"ecommerce_detected": True})),
                     {"signal": "ecommerce_detected"}) is True
    assert p.matches(_view(intent_json=json.dumps({"ecommerce_detected": False})),
                     {"signal": "ecommerce_detected"}) is False
    assert p.matches(_view(intent_json="{}"), {"signal": "ecommerce_detected"}) is None  # un-enriched
