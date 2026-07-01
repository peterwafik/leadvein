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
    def sql_pushdown(self, session, params):
        want = [c for c in (params.get("in") or []) if c]
        if not want:
            return None
        # NOTE (INV-5): SQL parity relies on LeadCategoryLink staying in sync with
        # category_keys_json. Any future path that edits a lead's categories MUST
        # re-run sync_lead_categories, or this pushdown could over-narrow.
        ids = lead_ids_for_categories(session, want)
        return Lead.id.in_(ids) if ids else Lead.id.in_([-1])


CATEGORY_ANY = _CategoryAny()
