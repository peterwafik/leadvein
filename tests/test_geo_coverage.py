"""Coverage counts are honest: only serveable leads count; gate-held leads don't."""
from __future__ import annotations

import json

from sqlmodel import Session

import app.leadvault as lv
from app.core.db import Lead
from app.geo.coverage import geo_lead_counts, invalidate_geo_counts


def _lead(city, country, validated=True, **kw):
    v = {"profile": {"tier": "validated"},
         "phone": {"tier": "validated" if validated else "present"},
         "email": {"tier": "absent"}}
    return Lead(business_name=f"biz-{city}", city=city, country=country,
                phone="+441865000000", category_keys_json='["bakery"]',
                validation_json=json.dumps(v), **kw)


def test_counts_only_serveable_leads():
    with Session(lv.engine) as s:
        s.add(_lead("Coverageville", "GB", validated=True))
        s.add(_lead("Coverageville", "GB", validated=True))
        s.add(_lead("Coverageville", "GB", validated=False))  # gate-held: not counted
        s.commit()
    invalidate_geo_counts()
    with Session(lv.engine) as s:
        counts = geo_lead_counts(s)
    assert counts["cities"][("GB", "coverageville")] == 2
    assert counts["countries"]["GB"] >= 2
    assert counts["city_names"]["coverageville"] == "Coverageville"


def test_cache_invalidation():
    with Session(lv.engine) as s:
        before = geo_lead_counts(s)["cities"].get(("GB", "cachetown"), 0)
        s.add(_lead("Cachetown", "GB"))
        s.commit()
        # stale until invalidated
        assert geo_lead_counts(s)["cities"].get(("GB", "cachetown"), 0) == before
        invalidate_geo_counts()
        assert geo_lead_counts(s)["cities"][("GB", "cachetown")] == before + 1
