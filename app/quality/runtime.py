from __future__ import annotations

from app.core.serve_filters import register_serve_filter
from app.quality.serve_gate import quality_serve_filter


def register_quality_runtime() -> None:
    register_serve_filter(quality_serve_filter)
