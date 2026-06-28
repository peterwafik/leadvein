from __future__ import annotations

from sqlmodel import Session, select

from app.core.compliance import audit, is_suppressed, is_opted_out, host_of
from app.core.db import PurchasedLead, Lead
from app.core.masking import unlock_view
from app.engine.export import rows_to_csv

EXPORT_COLUMNS = ["business_name", "phone", "public_email", "website_url",
                  "address_line1", "city", "region", "postal_code", "country",
                  "category_keys", "score_total", "score_explanation",
                  "source_name", "source_url", "source_license",
                  "date_last_verified", "lawful_basis"]


def export_purchased_csv(session: Session, user, columns: list[str] | None = None) -> bytes:
    cols = columns or EXPORT_COLUMNS
    ba_id = user.buyer_account_id
    purchases = session.exec(select(PurchasedLead).where(
        PurchasedLead.buyer_account_id == ba_id)).all()
    rows = []
    for p in purchases:
        lead = session.get(Lead, p.lead_id)
        if lead is None:
            continue
        if (is_opted_out(session, domain=host_of(lead.website_url), phone=lead.phone,
                         email=lead.public_email)
                or is_suppressed(session, ba_id, domain=host_of(lead.website_url),
                                 phone=lead.phone, email=lead.public_email,
                                 business_name=lead.business_name)):
            continue
        rows.append(unlock_view(lead))
    audit(session, user.id, "export", "BuyerAccount", str(ba_id),
          {"count": len(rows)})
    return rows_to_csv(cols, rows)
