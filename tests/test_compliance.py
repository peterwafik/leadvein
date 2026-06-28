from sqlmodel import Session
from app.core.db import (init_db, OptOutRequest, SuppressionList, SuppressionEntry,
                         AuditLog)
from app.core.compliance import host_of, is_opted_out, is_suppressed, audit
from sqlmodel import select


def test_host_of():
    assert host_of("https://www.joe.co.uk/menu") == "joe.co.uk"
    assert host_of("joe.com") == "joe.com"


def test_opt_out_and_suppression():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(OptOutRequest(kind="domain", value="optout.com", applied=True))
        gl = SuppressionList(buyer_account_id=None, name="global")
        s.add(gl); s.commit(); s.refresh(gl)
        s.add(SuppressionEntry(list_id=gl.id, kind="phone", value="+44 123"))
        bl = SuppressionList(buyer_account_id=7, name="buyer7")
        s.add(bl); s.commit(); s.refresh(bl)
        s.add(SuppressionEntry(list_id=bl.id, kind="domain", value="mine.com"))
        s.commit()

        assert is_opted_out(s, domain="optout.com") is True
        assert is_opted_out(s, domain="ok.com") is False
        assert is_suppressed(s, 7, phone="+44 123") is True       # global list
        assert is_suppressed(s, 7, domain="mine.com") is True     # buyer's own
        assert is_suppressed(s, 9, domain="mine.com") is False    # other buyer


def test_optout_and_suppression_normalize_values():
    from sqlmodel import Session
    from app.core.db import (init_db, OptOutRequest, SuppressionList, SuppressionEntry)
    from app.core.compliance import is_opted_out, is_suppressed
    engine = init_db("sqlite://")
    with Session(engine) as s:
        s.add(OptOutRequest(kind="domain", value="www.OptOut.com", applied=True))
        s.add(OptOutRequest(kind="phone", value="+44 123 456 789", applied=True))
        gl = SuppressionList(buyer_account_id=None, name="g"); s.add(gl); s.commit(); s.refresh(gl)
        s.add(SuppressionEntry(list_id=gl.id, kind="email", value="Sales@Biz.com"))
        s.commit()
        # domain opt-out stored with www + caps matches a bare lowercase host
        assert is_opted_out(s, domain="optout.com") is True
        # phone opt-out matches differently-formatted number (digits compared)
        assert is_opted_out(s, phone="+44123456789") is True
        # email suppression matches case-insensitively
        assert is_suppressed(s, 5, email="sales@biz.com") is True


def test_audit_writes_row():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        audit(s, 1, "unlock", "Lead", "42", {"price": 3})
        rows = s.exec(select(AuditLog)).all()
        assert rows[0].action == "unlock" and rows[0].entity_id == "42"
