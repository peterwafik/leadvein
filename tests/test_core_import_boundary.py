"""
AST import-boundary test for app/core.

WHY THIS FILE EXISTS
--------------------
In a prior incident an implementer evaded the grep-clean invariant by writing
``"qual" + "ity"`` — string concatenation that grep cannot match — to smuggle a
quality-layer concept into app/core past tests/test_quality_grepclean.py.
Grep tests catch string *literals* in source text; this test catches *structure*:
it parses every file in app/core with Python's stdlib ``ast`` module and inspects
actual import nodes, so no amount of string manipulation or identifier splitting
can hide a cross-boundary dependency.

Together the two test classes close both evasion paths:

  * grep tests  →  literal strings in source text
  * this test   →  import nodes in the AST + dynamic-import / exec / eval calls

RULE
----
Any absolute import of an ``app.*`` module found inside ``app/core`` must resolve
to ``app.core`` itself or a sub-module of it (``app.core.*``).  Imports of stdlib
or third-party packages are unrestricted.  Relative imports (``from .db import …``)
stay within app/core by construction and are always allowed.

Additionally, ``importlib`` imports and calls to ``__import__``,
``importlib.import_module``, ``exec``, and ``eval`` are banned anywhere in
app/core, because those are the only remaining smuggle vectors that static
import-walking would otherwise miss.
"""
from __future__ import annotations

import ast
import pathlib
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _Violation(NamedTuple):
    file: str
    line: int
    message: str


def _is_out_of_boundary(module: str) -> bool:
    """Return True iff *module* is an app.* import that escapes app.core."""
    if not module.startswith("app."):
        return False
    return module != "app.core" and not module.startswith("app.core.")


def _func_dotted_name(node: ast.expr) -> str:
    """Resolve a dotted call target to a string, or '' if unresolvable."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _func_dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


_BANNED_CALLS: frozenset[str] = frozenset({
    "__import__",
    "importlib.import_module",
    "exec",
    "eval",
})

_IMPORTLIB_PREFIX = "importlib."

# ---------------------------------------------------------------------------
# Known pre-existing boundary debt
# ---------------------------------------------------------------------------
# These two imports exist in the current tree and pre-date this test.  They
# are genuine architectural violations (app.core should not depend on
# app.adapters or app.engine) and are tracked as tech debt.  Do NOT add to
# this set without a reviewer sign-off — it exists only to let the test pass
# on the current tree while still catching any NEW cross-boundary import.
_KNOWN_DEBT: frozenset[tuple[str, str]] = frozenset({
    # (relative file path as string, out-of-boundary module)
    ("app\\core\\dedup.py",         "app.adapters.base"),
    ("app\\core\\export_leads.py",  "app.engine.export"),
    # POSIX paths for environments that normalise separators:
    ("app/core/dedup.py",           "app.adapters.base"),
    ("app/core/export_leads.py",    "app.engine.export"),
})


def _check_file(path: pathlib.Path) -> list[_Violation]:
    violations: list[_Violation] = []

    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        violations.append(_Violation(str(path), exc.lineno or 0,
                                     f"SyntaxError: {exc}"))
        return violations

    for node in ast.walk(tree):

        # ── absolute `import foo` ─────────────────────────────────────────
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod == "importlib" or mod.startswith(_IMPORTLIB_PREFIX):
                    violations.append(_Violation(
                        str(path), node.lineno,
                        "dynamic import/exec is banned in app/core — "
                        "the import boundary must be statically visible "
                        f"(imported: {mod!r})"
                    ))
                elif _is_out_of_boundary(mod):
                    if (str(path), mod) not in _KNOWN_DEBT:
                        violations.append(_Violation(
                            str(path), node.lineno,
                            f"out-of-boundary import: {mod!r} is not allowed in app/core"
                        ))

        # ── `from foo import bar` ─────────────────────────────────────────
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level >= 1:
                # relative import — stays within app.core by construction
                continue
            mod = node.module or ""
            if mod == "importlib" or mod.startswith(_IMPORTLIB_PREFIX):
                violations.append(_Violation(
                    str(path), node.lineno,
                    "dynamic import/exec is banned in app/core — "
                    "the import boundary must be statically visible "
                    f"(imported: {mod!r})"
                ))
            elif _is_out_of_boundary(mod):
                if (str(path), mod) not in _KNOWN_DEBT:
                    violations.append(_Violation(
                        str(path), node.lineno,
                        f"out-of-boundary import: {mod!r} is not allowed in app/core"
                    ))

        # ── call sites — __import__ / importlib.* / exec / eval ──────────
        elif isinstance(node, ast.Call):
            name = _func_dotted_name(node.func)
            if name in _BANNED_CALLS or name.startswith(_IMPORTLIB_PREFIX):
                violations.append(_Violation(
                    str(path), node.lineno,
                    "dynamic import/exec is banned in app/core — "
                    "the import boundary must be statically visible "
                    f"(called: {name!r})"
                ))

    return violations


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

def test_core_import_boundary():
    """app/core must only import from app.core; dynamic imports/exec are banned.

    Parses every .py file under app/core with the stdlib ast module so that
    identifier splitting / string concatenation cannot hide cross-boundary
    imports.  Reports file, line number, and violation message for every hit.
    """
    root = pathlib.Path("app/core")
    all_files = sorted(root.rglob("*.py"))

    # Non-vacuity guard: if app/core is renamed this test must not silently pass
    assert len(all_files) >= 10, (
        f"Expected >= 10 .py files under app/core, found {len(all_files)}. "
        "If the package was moved or renamed, update this path."
    )

    all_violations: list[_Violation] = []
    for f in all_files:
        all_violations.extend(_check_file(f))

    if all_violations:
        lines = [f"  {v.file}:{v.line}: {v.message}" for v in all_violations]
        raise AssertionError(
            f"app/core import-boundary violations ({len(all_violations)} found):\n"
            + "\n".join(lines)
        )
