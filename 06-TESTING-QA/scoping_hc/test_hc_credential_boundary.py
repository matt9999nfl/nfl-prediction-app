"""
Requirement F — the credential boundary, asserted structurally.

ADR-012 commitment 1: the chat "holds no BigQuery credential, has no query
path, and cannot execute generated code. It cannot do anything a wizard user
could not do."  If that boundary has been breached, everything else in ADR-012
is decoration, so this is checked first and checked by parsing rather than by
grepping.

Why AST and not grep: the implementation's own guard
(tests/test_scoping_core.py::test_render_module_does_not_reach_for_a_model)
searches the source TEXT for the strings "claude_scoping", "anthropic" and
"bigquery".  That check has two holes in opposite directions — a prose sentence
in a docstring matches it (render.py's own docstring contains the words "import
claude_scoping" and "hit BigQuery", so the module passes its own guard by
luck of phrasing rather than by structure), and any indirect import
(importlib, getattr on a module object, a string built at runtime) does not
match it at all.  Parsing the module answers what it actually imports and
calls.
"""
from __future__ import annotations

import ast

import pytest

# Anything that would give app/scoping/ a way to reach storage, a model, the
# network, the clock, or arbitrary execution.
FORBIDDEN_IMPORT_ROOTS = {
    "google",
    "google.cloud",
    "anthropic",
    "requests",
    "httpx",
    "urllib",
    "http",
    "socket",
    "subprocess",
    "importlib",
    "sqlite3",
    "sqlalchemy",
    "db_dtypes",
    "pandas_gbq",
}

# Modules inside the backend that hold a credential or a query path.
FORBIDDEN_APP_IMPORTS = {
    "app.bigquery_client",
    "app.claude_scoping",
    "app.claude_inference",
    "app.dependencies",
    "app.storage",
}

FORBIDDEN_APP_PREFIXES = ("app.queries", "app.routers")

FORBIDDEN_BUILTIN_CALLS = {"eval", "exec", "compile", "__import__", "open"}


def _imported_modules(source: str) -> set[str]:
    """Every module name this source imports, from the parse tree only."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                found.add(node.module)
    return found


def _called_names(source: str) -> set[str]:
    """Dotted names appearing in call position."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        parts: list[str] = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.append(func.id)
            names.add(".".join(reversed(parts)))
    return names


def _root(module_name: str) -> str:
    return module_name.split(".")[0]


# ── the boundary itself ──────────────────────────────────────────────────────


def test_no_scoping_module_imports_a_credential_or_a_query_path(scoping_src):
    """
    ADR-012 commitment 1, as a property of the import graph.

    Every module under app/scoping/ must import only stdlib, pydantic, and its
    own siblings. A single import of google.cloud, app.queries.* or
    app.bigquery_client here would give the chat a path to BigQuery that is not
    the wizard's write API.
    """
    offences: list[str] = []
    for filename, source in scoping_src.items():
        for module in _imported_modules(source):
            if _root(module) in FORBIDDEN_IMPORT_ROOTS or module in FORBIDDEN_IMPORT_ROOTS:
                offences.append(f"{filename} imports {module}")
            if module in FORBIDDEN_APP_IMPORTS or module.startswith(FORBIDDEN_APP_PREFIXES):
                offences.append(f"{filename} imports {module}")
    assert not offences, (
        "app/scoping/ must hold no BigQuery credential and no query path "
        "(ADR-012 commitment 1). Found: " + "; ".join(offences)
    )


def test_no_scoping_module_can_execute_generated_code(scoping_src):
    """ADR-012 commitment 1: 'cannot execute generated code'."""
    offences = [
        f"{filename} calls {name}()"
        for filename, source in scoping_src.items()
        for name in _called_names(source)
        if name in FORBIDDEN_BUILTIN_CALLS
    ]
    # schema.py and gaps.py legitimately read their own data files at import
    # time via Path.read_text, which is not a builtin `open` call.
    assert not offences, (
        "app/scoping/ must not be able to execute or eval anything. Found: "
        + "; ".join(offences)
    )


def test_no_scoping_module_writes_sql(scoping_src):
    """
    No SQL verb, in any module, in any string.

    The point is not that SQL text is dangerous on its own — it is that a SQL
    string under app/scoping/ means someone has started building a second
    write path beside the wizard's.
    """
    verbs = ("select ", "insert into", "update ", "delete from", "merge into", "create table")
    offences: list[str] = []
    for filename, source in scoping_src.items():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                # Skip docstrings: a docstring is prose, not a query.
                if any(verb in lowered for verb in verbs) and "\n" in node.value:
                    offences.append(f"{filename}:{node.lineno}")
    assert not offences, (
        "SQL found in app/scoping/, which is supposed to hold no query path. "
        "Lines: " + ", ".join(offences)
    )


# ── render() purity, checked structurally rather than by string search ───────


def test_render_reaches_nothing_outside_its_arguments(scoping_src):
    """
    ADR-012 commitment 3: render() is a pure template function.

    The named contract violation is someone adding a generated summary
    paragraph. The implementation guards that by grepping its own source for
    "claude_scoping"/"anthropic"/"bigquery" — but render.py's docstring
    contains both of those words in prose, so that guard is passing on the
    text of a warning about the thing it is warning about. This checks the
    parse tree instead, and also covers the clock, randomness, and the
    filesystem, none of which the grep looks for.
    """
    source = scoping_src["render.py"]
    imports = _imported_modules(source)
    assert imports <= {"__future__", "typing", "app.scoping.hashing", "app.scoping.schema"}, (
        f"render.py imports something beyond its pure dependencies: {sorted(imports)}"
    )

    impure = {
        "datetime.now", "datetime.today", "datetime.utcnow", "date.today",
        "time.time", "random.random", "random.choice", "uuid.uuid4",
        "os.getenv", "os.environ.get",
    }
    called = _called_names(source)
    assert not (called & impure), (
        f"render() consults something outside its arguments: {sorted(called & impure)}"
    )


# ── dispatch reaches the platform only via the wizard's handlers ─────────────


def _function_node(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


@pytest.fixture(scope="module")
def scoping_router_src(backend_root):
    return (backend_root / "app" / "routers" / "scoping.py").read_text(encoding="utf-8")


def test_dispatch_reaches_the_platform_only_through_the_wizard_handlers(scoping_router_src):
    """
    ADR-012 commitment 1, at the one place it could be broken cheaply.

    dispatch() may create an experiment and start a run. It must do that by
    calling the wizard's own handlers. Any direct BigQuery call inside dispatch
    would be a parallel write path that looks identical from the outside.
    """
    node = _function_node(scoping_router_src, "dispatch")
    called = _called_names(ast.unparse(node))

    assert "create_experiment" in called, "dispatch no longer calls create_experiment"
    assert "trigger_run" in called, "dispatch no longer calls trigger_run"

    forbidden = {c for c in called if c.startswith(("bq.", "client.", "bigquery."))}
    assert not forbidden, (
        f"dispatch talks to BigQuery directly: {sorted(forbidden)}. The chat is "
        "supposed to reach the platform only through create_experiment / trigger_run."
    )

    # The only session-store writes dispatch may make are its own bookkeeping.
    sq_calls = {c for c in called if c.startswith("sq.")}
    assert sq_calls <= {"sq.get_session", "sq.mark_dispatched"}, (
        f"dispatch writes to the session store beyond its own bookkeeping: {sorted(sq_calls)}"
    )


def test_dispatch_does_not_consult_the_governor(scoping_router_src):
    """
    ADR-012: the governor advises and cannot veto.

    Asserted here as the ABSENCE of a call, so that a governor gaining a veto
    fails the build rather than being noticed in review.
    """
    node = _function_node(scoping_router_src, "dispatch")
    called = _called_names(ast.unparse(node))
    assert not {c for c in called if c.startswith("governor.")}, (
        "dispatch consults the governor. A governor with a veto becomes a thing "
        "to route around."
    )
