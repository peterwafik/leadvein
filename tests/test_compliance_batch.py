"""Equivalence proof for the batched compliance prefetch (perf fix, Task 10).

The estimate() hot path replaced per-candidate `lead_opted_out()` /
`_not_suppressed()` DB lookups with two batch-built indexes. These tests assert
the batch indexes produce byte-for-byte identical opt-out / suppression
decisions to the per-lead functions they replace, and that estimate()'s visible
count matches the set computed with the per-lead functions.
"""
import json

from sqlmodel import Session

from app.core.db import (init_db, Lead, OptOutRequest, SuppressionList,
                         SuppressionEntry, _now)
from app.core.compliance import lead_opted_out, build_optout_index
from app.core.marketplace import _not_suppressed, build_suppression_index
from app.core.retention import is_expired
from app.core.leadcats import sync_lead_categories
from app.core.targeting import registry
from app.targeting.runtime import register_targeting_runtime
from app.core.targeting.estimate import estimate


def _mk(**kw):
    base = dict(business_name="Biz", country="GB", city="London", score_total=80,
                phone="", public_email="", website_url="",
                category_keys_json=json.dumps(["cafe"]),
                retention_expiry="2999-01-01T00:00:00+00:00",
                date_last_verified=_now())
    base.update(kw)
    return Lead(**base)


def _seed(s, buyer):
    leads = [
        _mk(business_name="Clean", website_url="https://clean.com",
            phone="+44 111", public_email="info@clean.com"),
        _mk(business_name="OptDomain", website_url="https://optout.com"),
        _mk(business_name="OptPhone", phone="+44 900 111 222"),
        _mk(business_name="OptEmail", public_email="stop@me.com"),
        _mk(business_name="SuppDomainGlobal", website_url="https://gblocked.com"),
        _mk(business_name="SuppPhoneBuyer", phone="+44 777 000"),
        _mk(business_name="SuppNameBuyer", website_url="https://named.com"),
        _mk(business_name="OtherBuyerOnly", website_url="https://otheronly.com"),
    ]
    for l in leads:
        s.add(l)
    s.commit()
    for l in leads:
        s.refresh(l)
        sync_lead_categories(s, l)
    # opt-outs (varied formatting/casing to exercise _norm on both sides)
    s.add(OptOutRequest(kind="domain", value="www.OptOut.com", applied=True))
    s.add(OptOutRequest(kind="phone", value="+44900111222", applied=True))
    s.add(OptOutRequest(kind="email", value="Stop@Me.com", applied=True))
    # not-applied opt-out must NOT match (applied flag respected)
    s.add(OptOutRequest(kind="domain", value="clean.com", applied=False))
    # global suppression list
    gl = SuppressionList(buyer_account_id=None, name="global")
    s.add(gl); s.commit(); s.refresh(gl)
    s.add(SuppressionEntry(list_id=gl.id, kind="domain", value="gblocked.com"))
    # buyer's own list
    bl = SuppressionList(buyer_account_id=buyer, name="mine")
    s.add(bl); s.commit(); s.refresh(bl)
    s.add(SuppressionEntry(list_id=bl.id, kind="phone", value="+44 777 000"))
    s.add(SuppressionEntry(list_id=bl.id, kind="business_name", value="SuppNameBuyer"))
    # another buyer's list — must NOT affect our buyer
    ol = SuppressionList(buyer_account_id=buyer + 999, name="other")
    s.add(ol); s.commit(); s.refresh(ol)
    s.add(SuppressionEntry(list_id=ol.id, kind="domain", value="otheronly.com"))
    s.commit()
    return leads


def test_batch_indexes_match_per_lead_decisions():
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    buyer = 1
    with Session(e) as s:
        leads = _seed(s, buyer)
        optout = build_optout_index(s)
        suppression = build_suppression_index(s, buyer)
        for l in leads:
            assert optout.matches(l) == lead_opted_out(s, l), l.business_name
            assert suppression.not_suppressed(l) == _not_suppressed(s, buyer, l), \
                l.business_name


def test_estimate_equivalence_batched_vs_per_lead():
    from app.core.serve_filters import clear as _gate_off
    _gate_off()  # gate-off: isolate compliance equivalence from the quality gate
    e = init_db("sqlite://")
    registry.clear(); register_targeting_runtime()
    buyer = 1
    with Session(e) as s:
        leads = _seed(s, buyer)
        expected = [l for l in leads
                    if not is_expired(l)
                    and not lead_opted_out(s, l)
                    and _not_suppressed(s, buyer, l)]
        comp = {"op": "AND",
                "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}]}
        est = estimate(s, buyer, comp)
        assert est["count"] == len(expected)   # == 2 (Clean, OtherBuyerOnly)
        assert est["count"] == 2
