from sqlmodel import Session
from app.db import init_db, seed_builtins, all_recipes, Recipe, Job


def test_seed_is_idempotent_and_lists_builtins():
    engine = init_db("sqlite://")  # in-memory
    with Session(engine) as s:
        seed_builtins(s)
        seed_builtins(s)  # twice -> no duplicates
        recipes = all_recipes(s)
        ids = [r["id"] for r in recipes]
        assert ids.count("gloriafood") == 1
        assert "calendly" in ids


def test_custom_recipe_persists():
    engine = init_db("sqlite://")
    with Session(engine) as s:
        seed_builtins(s)
        s.add(Recipe(id="myrec", category="Custom", type="MyTech",
                     urlscan_query="domain:x.com", publicwww_query="",
                     fingerprints_json='["x.com"]', extractors_json="{}",
                     exclude_hosts_json="[]", is_builtin=False))
        s.commit()
        ids = [r["id"] for r in all_recipes(s)]
        assert "myrec" in ids
