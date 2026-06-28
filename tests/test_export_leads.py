from sqlmodel import Session
from app.core.db import (init_db, BuyerAccount, User, Lead, PurchasedLead,
                         OptOutRequest, _now)
from app.core.export_leads import export_purchased_csv


def test_export_includes_owned_skips_optout():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        ba = BuyerAccount(company_name="A", credits=0); s.add(ba); s.commit(); s.refresh(ba)
        u = User(email="a@b.com", password_hash="x", buyer_account_id=ba.id)
        s.add(u); s.commit(); s.refresh(u)
        keep = Lead(business_name="Keep", phone="1", website_url="https://keep.com",
                    date_last_verified=_now())
        drop = Lead(business_name="Drop", phone="2", website_url="https://drop.com",
                    date_last_verified=_now())
        s.add(keep); s.add(drop); s.commit(); s.refresh(keep); s.refresh(drop)
        s.add(PurchasedLead(buyer_account_id=ba.id, lead_id=keep.id))
        s.add(PurchasedLead(buyer_account_id=ba.id, lead_id=drop.id))
        s.add(OptOutRequest(kind="domain", value="drop.com", applied=True))
        s.commit()
        csv_bytes = export_purchased_csv(s, u)
        text = csv_bytes.decode("utf-8")
        assert "Keep" in text and "keep.com" in text
        assert "Drop" not in text         # opted-out skipped at export
