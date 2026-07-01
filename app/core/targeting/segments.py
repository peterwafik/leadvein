from __future__ import annotations

import json

from sqlmodel import Session, select

from app.core.db import Segment, _now


def create_segment(session: Session, buyer_account_id: int, name: str,
                   composition: dict, *, origin_key: str = "") -> Segment:
    seg = Segment(buyer_account_id=buyer_account_id, name=name,
                  composition_json=json.dumps(composition),
                  origin_key=origin_key)
    session.add(seg); session.commit(); session.refresh(seg)
    return seg


def list_segments(session: Session, buyer_account_id: int) -> list:
    return session.exec(select(Segment).where(
        Segment.buyer_account_id == buyer_account_id).order_by(Segment.id.desc())).all()


def get_owned(session: Session, segment_id: int, buyer_account_id: int):
    seg = session.get(Segment, segment_id)
    if seg is None or seg.buyer_account_id != buyer_account_id:
        return None
    return seg


def delete_segment(session: Session, segment_id: int, buyer_account_id: int) -> bool:
    seg = get_owned(session, segment_id, buyer_account_id)
    if seg is None:
        return False
    session.delete(seg)
    session.commit()
    return True


def update_segment(session: Session, segment_id: int, buyer_account_id: int, *,
                   name: str | None = None, composition: dict | None = None):
    seg = get_owned(session, segment_id, buyer_account_id)
    if seg is None:
        return None
    if name is not None:
        seg.name = name
    if composition is not None:
        seg.composition_json = json.dumps(composition)
    seg.updated_at = _now()
    session.add(seg); session.commit(); session.refresh(seg)
    return seg
