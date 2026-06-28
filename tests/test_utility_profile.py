from app.scoring.engine import generic_subscores, score
from app.scoring.profiles.utility_energy import UtilityEnergyProfile


def test_high_energy_category_scores_higher_than_office():
    p = UtilityEnergyProfile()
    diner = {"category_keys": ["restaurant"], "phone": "1", "public_email": "a@b.com",
             "website_url": "https://x.com", "attributes": {"open_7_days": True},
             "date_last_verified": "2026-06-28T00:00:00+00:00",
             "source_confidence": 90, "opt_out_status": "clear",
             "suppression_status": "clear"}
    office = {"category_keys": ["accountant"], "phone": "1",
              "attributes": {}, "opt_out_status": "clear", "suppression_status": "clear"}
    hi = score(diner, p)
    lo = score(office, p)
    assert hi["total"] > lo["total"]
    assert "energy" in hi["explanation"].lower()
    assert "energy_usage_likelihood" in hi["subscores"]
