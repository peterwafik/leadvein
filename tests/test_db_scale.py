"""Scale plumbing: WAL journal mode + indexes needed before a national import."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlmodel import Session

import app.leadvault as lv


def test_sqlite_wal_enabled():
    with Session(lv.engine) as s:
        mode = s.exec(text("PRAGMA journal_mode")).one()[0]
        sync = s.exec(text("PRAGMA synchronous")).one()[0]
    assert str(mode).lower() == "wal"
    assert int(sync) == 1          # NORMAL


def test_scale_indexes_present():
    insp = inspect(lv.engine)
    names = {ix["name"] for ix in insp.get_indexes("lv_lead")}
    assert any("region" in n for n in names)
    assert any("retention_expiry" in n for n in names)
    assert "ix_lv_lead_country_score" in names
