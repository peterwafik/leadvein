import json

from sqlmodel import Session

import app.campaigns.models  # noqa — register table before init_db
from app.core.db import init_db
from app.campaigns.crud import list_active, get_by_key
from app.campaigns.seed import seed_campaigns


def test_seed_two_campaigns_idempotent():
    e = init_db("sqlite://")
    with Session(e) as s:
        assert seed_campaigns(s) == 2
        seed_campaigns(s)                       # idempotent
        assert len(list_active(s)) == 2
        util = get_by_key(s, "utilities_uk")
        assert util and util.quality_profile_key == "utilities"
        # Utilities composition template is cross-category (INV-8): no category predicate
        comp = json.loads(util.composition_template)
        assert not any("category" in n["predicate"] for n in comp["nodes"])
        rest = get_by_key(s, "business_restructuring")
        # Restructuring declares gated financial+size signals, never in the composition
        gs = json.loads(rest.gated_signals)
        assert set(gs) >= {"attributes.has_mca", "attributes.amount_owed", "attributes.lender", "attributes.size_band"}
        rcomp = json.loads(rest.composition_template)
        assert not any(p in json.dumps(rcomp) for p in ["has_mca", "amount_owed", "lender", "size_band"])
