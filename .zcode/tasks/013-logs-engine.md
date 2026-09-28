# Task 013 — Logs engine (Phase 7, part 1 of 3)

Executor task in the isolated worktree you were launched in (commit
nothing, run no git commands; ZCode integrates after verification).

## Binding specs (read first)

1. `docs/modules/logs-journal.md` — the journal reader contract.
2. `docs/mockups/mockup-e-logs.html/.png` — the page the engine feeds
   (views are task 014; you build the ENGINE + a minimal functional page).
3. `docs/build-principles.md` — offline mandate; argv discipline.

## Scope — the argv-contract engine, tests FIRST

1. **Write the argv-contract tests before the implementation**
   (`tests/test_logs_engine.py`): every journalctl invocation is asserted
   as an EXACT argv list (frozen strings — no shell, no string formatting
   of arguments; user input flows only as `--grep=VALUE` /
   `_SYSTEMD_UNIT=VALUE` argv entries). Cover: boot preset, unit filter,
   priority filter, since/until time-jump, follow/tail lines count, grep.
2. **`src/modules/manager_logs.py`** (new, core, UI-free — stdlib only):
   - `build_argv(preset, unit=None, priority=None, since=None, until=None,
     grep=None, lines=500, follow=False)` — pure, returns the argv list;
     invalid input → ValueError (never a malformed command).
   - `read_journal(argv, runtime_root=None)` — runs `/usr/bin/journalctl`
     via subprocess with the argv list (no shell), captures stdout with a
     bounded read (lines cap), decodes with errors="replace", returns
     structured entries: list of dicts {timestamp, priority, unit, message}
     parsed from `--output=json` fields when available with a plaintext
     fallback. Timeout + ProcessLookupError guards; never raises past the
     boundary — errors come back as {"error": "..."} entries.
   - Offline mandate: journalctl is a local binary — allowed; document it
     in the module docstring.
3. **Minimal functional page wiring** (`src/pages/page_logs.py`): preset
   combo (the four presets), unit entry, priority combo, lines selector,
   a Load button, and a monospace read-only results list (timestamp +
   priority badge + unit + message columns). Priority coloring per the
   mockup E language (red/yellow by severity). Search/refresh cadence and
   saved views are task 014 — do not build them.

## Constraints

- No gi in core (manager_logs.py); page uses compat seams only; no
  .add()/.show_all()/.get_children() in page code.
- The subprocess allowlist gate (tests/test_gates.py) may need the
  journalctl argv pattern ADDED — extend the gate test to allow exactly
  `/usr/bin/journalctl` with argv-list-only invocations, and assert that
  shell/string invocations still fail.
- "—" taxonomy; empty journal → empty state text, never an error dialog.

## Tests

argv-contract tests (step 1), parse tests (json + plaintext fallback),
timeout/missing-binary guards, page build + preset-load smoke (UI tier).

## Report

Files written, test counts, interpretation calls. ZCode verifies: scope
diff → pytest → gates (incl. the extended subprocess gate) → live capture
loading the real journal on :0.
