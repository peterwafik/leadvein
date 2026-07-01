import json
from app.core.db import Lead
from app.core.targeting.view import lead_view, get_path, MISSING


def test_lead_view_projects_columns_and_json_blobs():
    lead = Lead(business_name="X", city="London", country="GB", score_total=77,
                phone="123", public_email="info@x.com", website_url="https://x.com",
                category_keys_json=json.dumps(["cafe", "bakery"]),
                attributes_json=json.dumps({"detected_platform": "p", "open_7_days": True}),
                intent_json=json.dumps({"ssl": True, "online_ordering_detected": False}),
                subscores_json=json.dumps({"confidence": 90}))
    v = lead_view(lead)
    assert v["city"] == "London" and v["country"] == "GB" and v["score_total"] == 77
    assert v["category_keys"] == ["cafe", "bakery"]
    assert get_path(v, "attributes.detected_platform") == "p"
    assert get_path(v, "intent.ssl") is True
    assert get_path(v, "subscores.confidence") == 90
    # absent path -> MISSING (never a guessed False)
    assert get_path(v, "intent.does_not_exist") is MISSING
    assert get_path(v, "attributes.nope") is MISSING
