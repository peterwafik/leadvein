from __future__ import annotations

import json

from sqlmodel import Session, select

from app.campaigns.models import Campaign


def create_campaign(
    session: Session,
    *,
    key: str,
    name: str,
    description: str = "",
    composition_template: dict | str,
    preferred: list | str | None = None,
    scoring_profile_key: str = "",
    quality_profile_key: str = "",
    gated_signals: list | str | None = None,
    param_schema: dict | str | None = None,
    active: bool = True,
) -> Campaign:
    def _enc(v, default):
        if v is None:
            return default
        if isinstance(v, str):
            return v
        return json.dumps(v)

    c = Campaign(
        key=key,
        name=name,
        description=description,
        composition_template=_enc(composition_template, "{}"),
        preferred=_enc(preferred, "[]"),
        scoring_profile_key=scoring_profile_key,
        quality_profile_key=quality_profile_key,
        gated_signals=_enc(gated_signals, "[]"),
        param_schema=_enc(param_schema, "{}"),
        active=active,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def list_active(session: Session) -> list[Campaign]:
    return list(session.exec(select(Campaign).where(Campaign.active == True)).all())  # noqa: E712


def get_by_key(session: Session, key: str) -> Campaign | None:
    return session.exec(select(Campaign).where(Campaign.key == key)).first()


def get(session: Session, id: int) -> Campaign | None:
    return session.get(Campaign, id)


def update_campaign(session: Session, campaign: Campaign, **kwargs) -> Campaign:
    for k, v in kwargs.items():
        setattr(campaign, k, v)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign
