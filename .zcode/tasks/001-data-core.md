# Task 001 — Phase 1: data core (procfs + sysfs readers, launcher, nav shell)

Phase: 1 (concept §9)     Branch: task/001-data-core (already checked out — work here)
Dispatcher: ZCode (r042)  Executor: Claude Code, headless, acceptEdits

## Goal

Implement the Phase-1 data core of linprocman: the pure /proc and /sys
reader modules with hostile-fixture tests, the direct system-python
launcher, and the starter nav shell renamed to this app's pages. No UI
behavior beyond the shell compiles and launches.

## Read first (binding)

- docs/modules/procfs-data.md — the exact interface table, parsing rules,
  error taxonomy, system math, test list. THIS IS THE SPEC.
- docs/modules/sysfs-data.md — sensor reader spec.
- docs/build-principles.md — mandates (offline, local assets, no
  pip/venv, modularity).
- docs/process-manager-concept.md §2–§3 — module boundaries, starter map.

## Scope (touch nothing else)

- NEW  src/modules/procfs.py
- NEW  src/modules/sysfs.py
- NEW  tests/ (fixtures + test_procfs.py + test_sysfs.py + test_gates.py)
- EDIT run.sh (replace the venv/pip logic with the direct launcher)
- EDIT src/ui/sidebar.py, src/modules/manager_navigation.py,
       src/pages/content_area.py (or their real registration points):
       nav = Processes, Resources, Disks, Logs (group placeholder page),
       About, Settings; rename/remove the placeholder button03–06 pages
- EDIT src/config/* only if needed for the above page wiring
- EDIT requirements.txt to a comment header stating: system packages only
       (python3-gi, python3-cairo, python3-pil) — nothing pip-installed

## Constraints (verbatim, non-negotiable)

1. Fully offline application code: no network imports anywhere under src/
   (urllib, http, socket, requests, etc.). The AST gate enforces this.
2. The ONLY sanctioned subprocess binaries are journalctl and dmesg — and
   NOT in this task (logs phase). No subprocess use in this task.
3. Icons/assets: use only files under resources/icons/ (loaded by name per
   resources/icons/manifest.txt). Never reference ~/projects/assets or any
   remote path.
4. NEVER create any file or directory named 'claude', 'CLAUDE.md',
   '.claude', or any case variant, anywhere in the repo.
5. python3 system interpreter only; no venv, no pip, no package installs.
6. Core modules (procfs.py, sysfs.py) must import nothing UI-side — pure
   stdlib (os, re, time, functools) only.
7. procfs.py parsing rules are exact: comm = between first '(' and last
   ')'; after that tokens[0]=state (field 3), field n = tokens[n-3]; rss is
   pages; VmRSS is the memory source of truth; kthread = empty cmdline AND
   state ≠ Z. See the module doc for the full trap list.
8. Error taxonomy: FileNotFoundError = exited (row drops); PermissionError
   = locked (minimal data + None markers); nothing else escapes a reader.

## Acceptance (ZCode verifies all of this after your Report)

1. `python3 -m pytest tests/ -q` green from repo root, covering at least:
   stat (normal, comm-with-spaces, comm-with-parens, zombie-empty-cmdline,
   truncated), status (hidepid EACCES → locked shape), io (restricted →
   None), cmdline (kthread), cgroup fallbacks, system_stat (btime, busy
   fields, cpu-offline variant), net_dev (lo excluded), diskstats,
   pressure, smaps_rollup, sysfs hwmon temp+fan fixtures, missing-hwmon
   degradation; plus test_gates.py: AST import allowlist + subprocess argv
   allowlist (no network, no unsanctioned subprocess) + no-'claude'-path
   sweep of the repo tree.
2. `bash run.sh` == `python3 src/main.py` (direct launcher; no venv/pip).
3. Fixture files under tests/fixtures/proc/ and tests/fixtures/sys/ — tests
   run against bytes, never the live kernel.
4. `git diff --name-only` (ZCode checks) touches only Scope.
5. App launches headlessly under Xvfb without traceback (ZCode smoke-runs).

## Report (your final message)

Markdown: What you implemented (file map); deviations from the module docs
(none expected — any deviation is a defect); open questions; anything you
could not do because Bash was unavailable (do NOT attempt Bash; you cannot
run tests — ZCode runs them and will send failures back on this session).

## Out of scope (do not build)

Sampler thread, UI pages beyond the nav shell, GTK models, graphs, logs
engine, settings persistence. Phase 1 is data + shell only.
