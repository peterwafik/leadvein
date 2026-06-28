from sqlmodel import Session, select
from app.core.db import init_db, User, Lead, BuyerAccount


def test_models_create_and_query():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(BuyerAccount(company_name="Acme", credits=100))
        s.add(User(email="a@b.com", password_hash="x", role="buyer"))
        s.add(Lead(business_name="Joe Diner", source_key="k", source_name="n",
                   source_url="u", source_license="ODbL", city="London"))
        s.commit()
        assert s.exec(select(User)).first().email == "a@b.com"
        lead = s.exec(select(Lead)).first()
        assert lead.suppression_status == "clear"
        assert lead.exclusivity_status == "non_exclusive"
