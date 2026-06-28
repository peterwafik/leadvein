from app.scoring.engine import generic_subscores, score
from app.scoring.profiles import registry


class DummyProfile:
    key = "dummy"
    def combine(self, lead, base):
        total = round(sum(base.values()) / len(base))
        return {"subscores": base, "total": total,
                "explanation": f"dummy total {total}"}


def test_generic_subscores_reward_contact_and_freshness():
    full = generic_subscores({"phone": "1", "public_email": "a@b.com",
                              "website_url": "https://x.com",
                              "date_last_verified": "2026-06-28T00:00:00+00:00",
                              "source_confidence": 90, "opt_out_status": "clear",
                              "suppression_status": "clear"})
    empty = generic_subscores({"opt_out_status": "clear", "suppression_status": "clear"})
    assert full["contactability"] > empty["contactability"]
    assert full["compliance"] == 100
    assert 0 <= full["confidence"] <= 100


def test_score_delegates_to_profile():
    registry.register(DummyProfile())
    out = score({"phone": "1", "opt_out_status": "clear",
                 "suppression_status": "clear"}, registry.get("dummy"))
    assert "total" in out and "explanation" in out and "subscores" in out
