from __future__ import annotations
from app.core.db import Lead, LeadCategoryLink
from app.core.leadcats import lead_ids_for_categories


class _CategoryAny:
    key = "category.any"; group = "firmographic"; label = "Category is any of"
    reads = ["category_keys"]; params_schema = {"in": "list[string]"}
    def matches(self, view, params):
        want = set(params.get("in") or [])
        if not want:
            return None
        return bool(set(view.get("category_keys") or []) & want)
    # sql_pushdown needs the session -> handled specially in Task 6 via lead_ids_for_categories


CATEGORY_ANY = _CategoryAny()
