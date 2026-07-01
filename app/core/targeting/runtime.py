from __future__ import annotations
# Re-export from the concrete implementation layer (app.targeting.runtime).
# The predicates live outside core; this shim lets tests import from the
# canonical core package path.
from app.targeting.runtime import register_targeting_runtime  # noqa: F401

__all__ = ["register_targeting_runtime"]
