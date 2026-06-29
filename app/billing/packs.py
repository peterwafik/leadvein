from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Pack:
    key: str
    credits: int
    amount_cents: int  # minor units (pence/cents)
    label: str


CREDIT_PACKS = [
    Pack("pack_100", 100, 2900, "100 credits"),
    Pack("pack_500", 500, 11900, "500 credits"),
    Pack("pack_1000", 1000, 19900, "1,000 credits"),
]


def get_pack(key: str) -> Pack | None:
    return next((p for p in CREDIT_PACKS if p.key == key), None)


def currency() -> str:
    return (os.getenv("BILLING_CURRENCY") or "gbp").lower()
