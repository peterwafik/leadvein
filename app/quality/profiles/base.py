from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class QualityProfile:
    key: str
    label: str
    required: dict          # field -> min tier
    weights: dict = field(default_factory=dict)
