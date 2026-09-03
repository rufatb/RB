"""Day-82: structural invariants the inventory pass established.

The §2 audit found that importing a module could fire 133 HTTP requests and
write a 38MB file, and that four study harnesses failed with bare
FileNotFoundErrors against paths belonging to a container that no longer
exists. Both are asserted here so they cannot come back.
"""

import ast
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = sorted(f[:-3] for f in os.listdir(REPO)
              if f.endswith(".py") and not f.startswith("_"))


def _tree(m):
    with open(os.path.join(REPO, m + ".py")) as f:
        return ast.parse(f.read(), filename=m + ".py")


# ── importing must never touch the network or write a file ──────────────────

# MATCH THE RECEIVER, NOT JUST THE METHOD. A first pass flagged `get` and
# caught `os.environ.get` and `cfg.get` in four places — a check that fires on
# correct code is one that gets deleted rather than obeyed. Only calls whose
# receiver is plausibly an HTTP client count.
HTTP_RECEIVERS = {"requests", "session", "sess", "http", "client", "urllib",
                  "urlopen", "s"}
NETWORK_METHODS = {"get", "post", "put", "head", "request"}
BARE_NETWORK = {"urlopen", "urlretrieve"}       # network whatever the receiver
WRITERS = {"to_csv", "to_json", "savefig", "to_parquet"}


def _receiver(func):
    """Left-most name of an attribute chain: requests.get -> 'requests'."""
    n = func.value
    while isinstance(n, ast.Attribute):
        n = n.value
    return n.id if isinstance(n, ast.Name) else ""


def _toplevel_calls(tree):
    """Attribute calls reachable at module level, excluding def/class bodies."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.If):
            # `if __name__ == "__main__":` is exactly how you opt IN to running.
            t = node.test
            if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__"):
                continue
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                out.append((_receiver(n.func), n.func.attr))
    return out


def _network_hits(m):
    hits = set()
    for recv, attr in _toplevel_calls(_tree(m)):
        if attr in BARE_NETWORK:
            hits.add(f"{recv}.{attr}" if recv else attr)
        elif attr in NETWORK_METHODS and recv.lower() in HTTP_RECEIVERS:
            hits.add(f"{recv}.{attr}")
    return sorted(hits)


def test_no_module_fetches_from_the_network_when_imported():
    """validate_events_build fired 133 threaded requests on import.

    An inventory pass that merely imported every module to see which ones load
    therefore ran a full ten-year harvest as a side effect.
    """
    bad = {m: _network_hits(m) for m in MODS}
    bad = {m: v for m, v in bad.items() if v}
    assert not bad, f"network calls at import time: {bad}"


def test_no_module_writes_a_data_file_when_imported():
    """It also wrote a 38MB csv, which is how a dataset acquires no provenance."""
    bad = {m: sorted({a for _, a in _toplevel_calls(_tree(m))} & WRITERS)
           for m in MODS}
    bad = {m: v for m, v in bad.items() if v}
    assert not bad, f"file writes at import time: {bad}"


# ── a missing input must be actionable, never a bare traceback ──────────────

def test_the_network_check_would_fire_on_a_real_harvest():
    """POSITIVE CONTROL. A check that cannot detect the thing it forbids is
    decoration — and this one was already loosened once after false positives,
    which is exactly when a check quietly stops working."""
    import textwrap
    src = textwrap.dedent("""
        import requests
        rows = [requests.get(u) for u in URLS]
        def safe():
            return requests.get("ok-inside-a-function")
        if __name__ == "__main__":
            requests.get("ok-under-main")
    """)
    tree = ast.parse(src)
    hits = {f"{_receiver(n.func)}.{n.func.attr}"
            for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef))
            and not (isinstance(node, ast.If)
                     and isinstance(node.test, ast.Compare)
                     and isinstance(node.test.left, ast.Name)
                     and node.test.left.id == "__name__")
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in NETWORK_METHODS
            and _receiver(n.func).lower() in HTTP_RECEIVERS}
    assert hits == {"requests.get"}, hits


def test_os_environ_get_is_not_mistaken_for_a_network_call():
    """The four false positives that forced the receiver check."""
    import textwrap
    tree = ast.parse(textwrap.dedent("""
        import os
        D = os.environ.get("TD_DATA_DIR", "x")
        G = cfg.get("peer_groups") or {}
    """))
    hits = [(r, a) for node in tree.body for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            for r, a in [(_receiver(n.func), n.func.attr)]
            if a in NETWORK_METHODS and r.lower() in HTTP_RECEIVERS]
    assert hits == [], hits


def test_a_missing_bar_cache_names_the_fix_rather_than_raising():
    """The default TD_DATA_DIR is a scratchpad from a session that has ended.

    Two studies failed with `FileNotFoundError: .../td_data` and nothing said
    the cache was never committed, so BLOCKED was indistinguishable from broken.
    """
    import validate_deep as vd
    try:
        vd.require_data("/nonexistent/definitely/not/here")
        assert False, "expected a stated refusal"
    except SystemExit as e:
        msg = str(e)
    assert "TD_DATA_DIR" in msg
    assert "INVENTORY.md" in msg
    assert "cannot be re-derived" in msg


def test_require_data_returns_the_directory_when_it_exists():
    """A guard that always fires is one nobody reads."""
    import validate_deep as vd
    assert vd.require_data(REPO) == REPO


# ── the study layer is the record, and must stay loadable ───────────────────

def test_every_module_parses():
    """A file that will not parse cannot encode anything, record or otherwise."""
    broken = {}
    for m in MODS:
        try:
            _tree(m)
        except SyntaxError as e:
            broken[m] = str(e)
    assert not broken, broken


def test_the_inventory_exists_and_names_the_three_tiers():
    p = os.path.join(REPO, "INVENTORY.md")
    assert os.path.exists(p), "INVENTORY.md is the §2 deliverable"
    txt = open(p).read()
    for tier in ("LIVE", "TEST", "STUDY"):
        assert tier in txt


def test_the_rebuildable_panel_is_not_committed():
    """daily.csv is 38MB and regenerable; it must never enter git history."""
    r = subprocess.run(["git", "check-ignore", "daily.csv"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, "daily.csv is not gitignored"
