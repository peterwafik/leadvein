import json
from sqlmodel import Session
from app.core.db import init_db
from app.campaigns.seed import seed_campaigns
from app.campaigns.crud import get_by_key
from app.campaigns.compile import compile_campaign

def test_compile_utilities_and_restructuring():
    e = init_db("sqlite://")
    with Session(e) as s:
        seed_campaigns(s)
        out = compile_campaign(get_by_key(s, "utilities_uk"), {"area": "Oxford"})
        nodes = out["composition"]["nodes"]
        assert {"predicate":"geo.country","params":{"value":"GB"}} in nodes
        assert {"predicate":"geo.city","params":{"value":"Oxford"}} in nodes
        assert out["quality_profile_key"] == "utilities"
        assert out["gated_notices"] == []
        assert not any("category" in n["predicate"] for n in nodes)     # INV-8

        r = compile_campaign(get_by_key(s, "business_restructuring"),
                             {"area": "Oxford", "sectors": ["cafe","restaurant"]})
        rn = r["composition"]["nodes"]
        assert {"predicate":"category.any","params":{"in":["cafe","restaurant"]}} in rn
        paths = {g["path"] for g in r["gated_notices"]}
        assert {"attributes.has_mca","attributes.amount_owed","attributes.lender","attributes.size_band"} <= paths
        assert all(g["reason"] == "requires licensed source" for g in r["gated_notices"])
        blob = json.dumps(r["composition"])                              # INV-6: no gated field in composition
        assert not any(x in blob for x in ["has_mca","amount_owed","lender","size_band"])
