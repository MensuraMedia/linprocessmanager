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
import os

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

# The only binaries a subprocess call site may invoke (none used in Phase 1).
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


def _sanctioned_binary(call):
    """Return a sanctioned binary name if statically provable, else None."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.List) and arg.elts:
        first = arg.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return os.path.basename(first.value)
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        tokens = arg.value.split()
        if tokens:
            return os.path.basename(tokens[0])
    return None


def test_subprocess_argv_allowlist():
    offenders = []
    for path in _iter_src_files():
        for call in _spawn_calls(_parse(path)):
            binary = _sanctioned_binary(call)
            if binary not in SANCTIONED_BINARIES:
                offenders.append("%s: spawn of %r" % (
                    os.path.relpath(path, REPO_ROOT), binary))
    assert offenders == [], "unsanctioned subprocess call sites: %s" % offenders


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
