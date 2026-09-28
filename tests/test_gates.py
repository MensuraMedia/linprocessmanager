"""Self-reliance / safety gates (build-principles.md §4, task constraints).

These enforce the mandates statically, against the source tree:

1. No network imports anywhere under ``src/`` (AST, not grep).
2. Core-module import allowlist: ``procfs.py`` / ``sysfs.py`` import only the
   sanctioned pure-stdlib subset (no UI, no network).
3. Subprocess-argv allowlist: every process-spawning call site must invoke a
   sanctioned binary (``journalctl``/``dmesg``). Phase 1 uses no subprocess at
   all, so the set of call sites must be empty-or-sanctioned.
4. No file or directory named ``claude`` / ``CLAUDE.md`` / ``.claude`` (any
   case) anywhere in the repo.
"""

import ast
import importlib
import importlib.util
import os
import warnings

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SRC = os.path.join(REPO_ROOT, "src")

# Network modules that must never be imported (roots + notable dotted names).
NET_ROOTS = {
    "socket", "socketserver", "ssl", "urllib", "http", "ftplib", "telnetlib",
    "smtplib", "poplib", "imaplib", "nntplib", "xmlrpc", "asyncore",
    "asynchat", "requests", "urllib3", "httpx", "aiohttp", "httplib2",
    "websocket", "websockets", "pycurl",
}

# The only imports the pure core modules may use.
CORE_ALLOWED = {"os", "re", "time", "functools"}
CORE_MODULES = {"procfs.py", "sysfs.py"}

# The only binaries a subprocess call site may invoke. journalctl is spawned by
# the logs engine (manager_logs.read_journal, Phase 7) as an argv LIST with a
# literal binary and `=`-form values only; dmesg is the reserved fallback.
SANCTIONED_BINARIES = {"journalctl", "dmesg"}

BANNED_PATH_NAMES = {"claude", "claude.md", ".claude"}


def _iter_src_files():
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def _parse(path):
    with open(path, "r", encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=path)


def _absolute_imports(tree):
    """Top-level imported module names (absolute imports only)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module)
    return names


# ---------------------------------------------------------------------------
# 1. no network imports anywhere under src/
# ---------------------------------------------------------------------------

def test_no_network_imports_in_src():
    offenders = []
    for path in _iter_src_files():
        for name in _absolute_imports(_parse(path)):
            root = name.split(".")[0]
            if root in NET_ROOTS:
                offenders.append("%s imports %s" % (
                    os.path.relpath(path, REPO_ROOT), name))
    assert offenders == [], "network imports found: %s" % offenders


# ---------------------------------------------------------------------------
# 2. core-module import allowlist
# ---------------------------------------------------------------------------

def test_core_modules_import_allowlist():
    offenders = []
    for path in _iter_src_files():
        if os.path.basename(path) not in CORE_MODULES:
            continue
        for name in _absolute_imports(_parse(path)):
            root = name.split(".")[0]
            if root not in CORE_ALLOWED:
                offenders.append("%s imports %s" % (
                    os.path.relpath(path, REPO_ROOT), name))
    assert offenders == [], "core modules import outside allowlist: %s" % offenders


# ---------------------------------------------------------------------------
# 3. subprocess-argv allowlist
# ---------------------------------------------------------------------------

def _spawn_calls(tree):
    """Process-spawning call sites: subprocess.* and os.system/popen/exec/spawn."""
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = func.value.id
            attr = func.attr
            if module == "subprocess":
                calls.append(node)
            elif module == "os" and (
                attr in ("system", "popen")
                or attr.startswith("exec")
                or attr.startswith("spawn")
            ):
                calls.append(node)
    return calls


def _uses_shell(call):
    """True if the spawn passes ``shell=True`` (shell parsing = flag injection).

    Only a literal ``shell=True`` is provable; anything else (variable, absent)
    is treated as no shell — but the argv-list requirement below already blocks
    the string forms a shell would need.
    """
    for kw in call.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
            return kw.value.value is True
    return False


def _sanctioned_binary(call):
    """Return the sanctioned binary for an argv-LIST spawn, else None.

    Only the argv-list form is honoured: ``run(["/usr/bin/journalctl", ...])``
    whose first element is a string literal naming a sanctioned binary. A shell
    STRING (``run("journalctl ...")``) — or any other first-arg shape — returns
    None and therefore fails the gate: user input must never reach a shell.
    """
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.List) and arg.elts:
        first = arg.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return os.path.basename(first.value)
    return None


def test_subprocess_argv_allowlist():
    offenders = []
    for path in _iter_src_files():
        for call in _spawn_calls(_parse(path)):
            rel = os.path.relpath(path, REPO_ROOT)
            if _uses_shell(call):
                offenders.append("%s: shell=True spawn" % rel)
                continue
            binary = _sanctioned_binary(call)
            if binary not in SANCTIONED_BINARIES:
                offenders.append("%s: spawn of %r" % (rel, binary))
    assert offenders == [], "unsanctioned subprocess call sites: %s" % offenders


def _one_call(src):
    return _spawn_calls(ast.parse(src))[0]


def test_gate_accepts_journalctl_argv_list():
    """The sanctioned pattern: argv list, literal binary, `=`-form values."""
    call = _one_call(
        "subprocess.run(['/usr/bin/journalctl', '--no-pager', "
        "'--grep=' + value])")
    assert not _uses_shell(call)
    assert _sanctioned_binary(call) == "journalctl"


def test_gate_rejects_string_invocation():
    """A shell/string invocation must fail even for a sanctioned binary."""
    call = _one_call("subprocess.run('/usr/bin/journalctl --no-pager')")
    assert _sanctioned_binary(call) not in SANCTIONED_BINARIES


def test_gate_rejects_shell_true():
    call = _one_call("subprocess.run(['/usr/bin/journalctl'], shell=True)")
    assert _uses_shell(call) is True


def test_gate_rejects_variable_argv():
    """A bare variable (unprovable binary) is not the sanctioned list form."""
    call = _one_call("subprocess.run(argv)")
    assert _sanctioned_binary(call) is None


# ---------------------------------------------------------------------------
# 4. no 'claude'-named path anywhere in the repo
# ---------------------------------------------------------------------------

def test_no_claude_paths_in_repo():
    offenders = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in list(dirs) + files:
            if name.lower() in BANNED_PATH_NAMES:
                offenders.append(os.path.relpath(os.path.join(root, name), REPO_ROOT))
    assert offenders == [], "banned 'claude' paths found: %s" % offenders


# ===========================================================================
# GTK compat / upgrade gates (task 002; upgrade-architecture.md §3-4,
# gtk4-port.md §4). Three tiers: the raw-import ban, the banned-API sweep, and
# the PyGObject-deprecation-as-error tier — plus a dual-path structural check.
# ===========================================================================

def _rel(path):
    """Repo-relative path with forward slashes (portable comparisons)."""
    return os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")


def _under(rel, prefix):
    return rel == prefix or rel.startswith(prefix + "/")


# Toolkit-seam file anchors (upgrade-architecture.md §3 table).
COMPAT_DIR = "src/ui/compat"


def _is_ui_tree(rel):
    """GTK can only be referenced under src/ui/ or src/pages/ (raw-import ban)."""
    return rel.startswith("src/ui/") or rel.startswith("src/pages/")
GTK_ENV_REL = "src/ui/compat/gtk_env.py"
LAYOUT_REL = "src/ui/compat/layout.py"
DIALOGS_REL = "src/ui/compat/dialogs.py"
CHARTS_REL = "src/ui/compat/charts.py"
EVENTS_REL = "src/ui/compat/events.py"
MAIN_REL = "src/main.py"

GTK_ENV_PATH = os.path.join(SRC, "ui", "compat", "gtk_env.py")


# ---------------------------------------------------------------------------
# Tier 6a — raw ``gi`` / ``gi.repository`` import ban.
#
# ``gi.require_version`` and ``from gi.repository import ...`` (and bare
# ``import gi``) may appear ONLY in gtk_env.py — a bare import silently loads a
# default version and defeats the single flip point (upgrade-architecture.md
# §2). The ban holds repo-wide: every other module under ``src/`` routes its
# toolkit symbols through ``src/ui/compat``. There is no pending allowlist.
# ---------------------------------------------------------------------------

GI_IMPORT_ALLOWED = {GTK_ENV_REL}


def _touches_gi(tree):
    """True if the module imports ``gi``/``gi.repository`` or calls
    ``gi.require_version`` — the three ways version knowledge leaks in."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "gi.repository" or module.startswith("gi.repository."):
                return True
            if module == "gi" or module.startswith("gi."):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "gi" or alias.name.startswith("gi."):
                    return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if (func.attr == "require_version"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "gi"):
                return True
    return False


def test_raw_gi_import_ban():
    offenders = []
    for path in _iter_src_files():
        rel = _rel(path)
        if not _touches_gi(_parse(path)):
            continue
        if rel in GI_IMPORT_ALLOWED:
            continue
        offenders.append(rel)
    assert offenders == [], (
        "raw gi/gi.repository import outside gtk_env.py (route through "
        "src/ui/compat): %s" % offenders)


def test_gtk_env_is_the_gi_entry_point():
    """gtk_env.py must actually be the (single) binding entry point."""
    assert _touches_gi(_parse(GTK_ENV_PATH)), "gtk_env.py must import gi"


# ---------------------------------------------------------------------------
# Tier 6b — banned-API sweep (scoped, AST-based so adapter docstrings that
# merely *mention* the APIs are not flagged).
#
# Box-only pack_start/pack_end outside layout.py; container ``.add(`` /
# ``set_border_width`` outside compat; ``.destroy(`` outside dialogs.py;
# ``show_all`` outside main.py + compat; ``connect('button-press-event'|
# 'key-press-event')`` outside events.py; ``connect('draw')`` outside
# charts.py; and Gtk.{Dialog,MessageDialog,RadioButton,ShortcutController}
# anywhere.
#
# The GTK-container bans (add/set_border_width/destroy) apply only to the
# UI trees (src/ui/, src/pages/) — the raw-import ban already proves
# src/modules/ holds no GTK, and plain-Python set.add()/dict ops there are
# legitimate (r048 tuning: manager_sampler._rollup_targets.add).
# ---------------------------------------------------------------------------

BANNED_CONNECT_SIGNALS = {"button-press-event", "key-press-event"}
BANNED_GTK_ATTRS = {"Dialog", "MessageDialog", "RadioButton", "ShortcutController"}


def _banned_api_violations():
    offenders = []
    for path in _iter_src_files():
        rel = _rel(path)
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr in ("pack_start", "pack_end") and rel != LAYOUT_REL:
                    offenders.append("%s: %s()" % (rel, attr))
                elif attr in ("add", "set_border_width") and _is_ui_tree(rel) and not _under(rel, COMPAT_DIR):
                    offenders.append("%s: %s()" % (rel, attr))
                elif attr == "destroy" and _is_ui_tree(rel) and rel != DIALOGS_REL:
                    offenders.append("%s: destroy()" % rel)
                elif (attr == "show_all"
                      and rel != MAIN_REL and not _under(rel, COMPAT_DIR)):
                    offenders.append("%s: show_all()" % rel)
                elif attr == "connect" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        sig = first.value
                        if sig in BANNED_CONNECT_SIGNALS and rel not in (EVENTS_REL, "src/ui/compat/tray.py"):
                            offenders.append("%s: connect(%r)" % (rel, sig))
                        elif sig == "draw" and rel != CHARTS_REL:
                            offenders.append("%s: connect('draw')" % rel)
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "Gtk"
                    and node.attr in BANNED_GTK_ATTRS):
                offenders.append("%s: Gtk.%s" % (rel, node.attr))
    return offenders


def test_banned_api_sweep():
    offenders = _banned_api_violations()
    assert offenders == [], (
        "banned GTK3-only API outside its compat adapter: %s" % offenders)


# ---------------------------------------------------------------------------
# Tier 6c — PyGObject binding-level deprecations as errors, scoped outside
# compat (upgrade-architecture.md §4.2). Catches binding-level misuse
# (deprecated constructor args / removed overrides); GTK's own C-level
# deprecations do not surface through PyGObject and are covered by 6b + smoke.
# ---------------------------------------------------------------------------

def test_no_binding_deprecations_outside_compat():
    gi = pytest.importorskip("gi")
    try:
        deprecation = gi.PyGIDeprecationWarning
    except AttributeError:  # pragma: no cover - very old pygobject
        pytest.skip("gi.PyGIDeprecationWarning unavailable")

    with warnings.catch_warnings():
        # Escalate binding deprecations to errors everywhere...
        warnings.simplefilter("error", deprecation)
        # ...except where they originate inside the compat seam, which is
        # allowed to touch version-specific bindings by design.
        warnings.filterwarnings(
            "default", category=deprecation, module=r".*\.compat\..*")
        # Importing the UI package cascades through every migrated UI + page
        # module (ui/__init__ -> dashboard_window -> sidebar/content_area ->
        # pages -> components), exercising import-time binding usage.
        importlib.import_module("ui")
        importlib.import_module("pages")


# ---------------------------------------------------------------------------
# Dual-path proof (acceptance 5). Each adapter must carry BOTH toolkit
# spellings behind a GTK_MAJOR branch. Verified by source inspection (no GTK
# objects required) — a process holds one Gtk version, so the non-active path's
# GTK-calling lines only run under that toolkit, but the branch + both spellings
# must be present now (upgrade-architecture.md §3 testing-scope note).
# ---------------------------------------------------------------------------

DUAL_PATH_EXPECTATIONS = {
    "layout.py": ["GTK_MAJOR", "pack_start", "append", "set_child"],
    "menu.py": ["GTK_MAJOR", "bind_model", "new_from_model"],
    "events.py": ["GTK_MAJOR", "GestureMultiPress", "GestureClick"],
    "charts.py": ["GTK_MAJOR", 'connect("draw"', "set_draw_func"],
    "icons.py": ["GTK_MAJOR", "new_from_pixbuf", "new_from_paintable"],
    "css.py": ["GTK_MAJOR", "add_provider_for_screen", "add_provider_for_display"],
}


def test_adapters_carry_dual_paths():
    missing = []
    for filename, needles in DUAL_PATH_EXPECTATIONS.items():
        path = os.path.join(SRC, "ui", "compat", filename)
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in needles:
            if needle not in source:
                missing.append("%s missing %r" % (filename, needle))
    assert missing == [], "adapter dual-path spelling missing: %s" % missing


def test_gtk_env_requires_both_gtk_and_gdk():
    """The port flips Gtk AND Gdk together — both require_version calls live
    here, GdkPixbuf pinned to 2.0 (upgrade-architecture.md §3)."""
    with open(GTK_ENV_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert 'require_version("Gtk", "3.0")' in source
    assert 'require_version("Gdk", "3.0")' in source
    assert 'require_version("GdkPixbuf", "2.0")' in source


# ---------------------------------------------------------------------------
# Capability-flag selection logic (feature-probe pattern,
# debian-compatibility.md §2). Pure integer logic — no GTK objects — so both
# GTK3 and GTK4 selections are unit-tested every run.
# ---------------------------------------------------------------------------

def _load_gtk_env():
    """Load gtk_env.py directly by file path (bypassing ui/__init__)."""
    pytest.importorskip("gi")
    spec = importlib.util.spec_from_file_location(
        "compat_gtk_env_under_test", GTK_ENV_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, ValueError) as exc:  # missing typelib, etc.
        pytest.skip("GTK bindings unavailable: %s" % exc)
    return module


def test_capability_flag_selection_logic():
    env = _load_gtk_env()
    flags = env.compute_capability_flags

    # AlertDialog is GTK4 >= 4.10 only.
    assert flags(3, 24)["HAS_ALERT_DIALOG"] is False
    assert flags(4, 8)["HAS_ALERT_DIALOG"] is False
    assert flags(4, 10)["HAS_ALERT_DIALOG"] is True
    assert flags(4, 14)["HAS_ALERT_DIALOG"] is True

    # GestureClick / Texture / per-display provider are GTK4-wide.
    assert flags(3, 24)["HAS_GESTURE_CLICK"] is False
    assert flags(4, 6)["HAS_GESTURE_CLICK"] is True
    assert flags(3, 24)["HAS_TEXTURE"] is False
    assert flags(4, 6)["HAS_TEXTURE"] is True
    assert flags(3, 24)["HAS_DISPLAY_PROVIDER"] is False
    assert flags(4, 6)["HAS_DISPLAY_PROVIDER"] is True

    # Module-level flags agree with the running toolkit.
    assert env.GTK_MAJOR in (3, 4)
    assert env.HAS_ALERT_DIALOG == (
        (env.GTK_MAJOR, env.GTK_MINOR) >= (4, 10))
