import json
import pytest
from sqlmodel import Session
from app.core.db import (init_db, Lead, BuyerAccount, User, PurchasedLead,
                         OptOutRequest, _now)
from app.core.marketplace import search
from app.core.recipes import DEFAULT_FILTERS
from app.core.purchasing import unlock_lead, grant_credits, LeadSuppressed
from app.core.export_leads import export_purchased_csv
from app.core.compliance import lead_opted_out
from app.core.leadcats import sync_lead_categories


def test_lead_model_has_no_independent_optout_flag():
    # opt-out is collapsed into the OptOutRequest table — the Lead no longer carries its own flag
    assert not hasattr(Lead(), "opt_out_status")


def test_opt_out_single_source_normalized_across_search_unlock_export():
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate-off: this test exercises opt-out enforcement across search/unlock/export, not the quality gate
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="A", credits=0, compliance_ack_at=_now())
        s.add(ba); s.commit(); s.refresh(ba)
        u = User(email="a@b.com", password_hash="x", role="buyer", buyer_account_id=ba.id)
        s.add(u); s.commit(); s.refresh(u)
        grant_credits(s, ba.id, 50)
        lead = Lead(business_name="Gone Diner",
                    category_keys_json=json.dumps(["restaurant"]), city="London",
                    phone="+44 20 1234 5678", public_email="Sales@Gone.com",
                    website_url="https://gone.com", score_total=90,
                    date_last_verified=_now(), price_credits=3)
        s.add(lead); s.commit(); s.refresh(lead)
        sync_lead_categories(s, lead)
        # opt-out stored in a DIFFERENT format than the lead (digits-only phone)
        s.add(OptOutRequest(kind="phone", value="+442012345678", applied=True))
        s.commit()
        # single source -> normalized match
        assert lead_opted_out(s, lead) is True
        # enforced everywhere: search, unlock, export
        f = {**DEFAULT_FILTERS, "categories": ["restaurant"], "city": "London"}
        assert search(s, ba.id, f) == []
        with pytest.raises(LeadSuppressed):
            unlock_lead(s, u, lead.id)
        s.add(PurchasedLead(buyer_account_id=ba.id, lead_id=lead.id)); s.commit()
        assert "Gone Diner" not in export_purchased_csv(s, u).decode("utf-8")
