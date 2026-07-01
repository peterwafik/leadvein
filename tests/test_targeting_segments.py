import json
from sqlmodel import Session
from app.core.db import init_db, Segment
from app.core.targeting.segments import (create_segment, list_segments, get_owned, update_segment)


def test_segment_crud_is_owner_scoped():
    e = init_db("sqlite://")
    with Session(e) as s:
        comp = {"op": "AND", "nodes": [{"predicate": "geo.country", "params": {"value": "GB"}}]}
        seg = create_segment(s, 1, "UK cafes", comp)
        assert seg.id and json.loads(seg.composition_json) == comp
        assert [x.id for x in list_segments(s, 1)] == [seg.id]
        assert list_segments(s, 2) == []                       # buyer-scoped
        assert get_owned(s, seg.id, 1).name == "UK cafes"
        assert get_owned(s, seg.id, 2) is None                 # ownership guard
        up = update_segment(s, seg.id, 1, name="renamed")
        assert up.name == "renamed" and up.updated_at is not None
        assert update_segment(s, seg.id, 2, name="hijack") is None  # cannot update others'
