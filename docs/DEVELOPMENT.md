# linprocman — development guide

Day-to-day working reference. Binding rules live in
[build-principles.md](build-principles.md); this file is the how-to.

## Environment

- Linux Mint 22.3 / Debian-family; system `python3` (3.10+ floor).
- Packages: `python3-gi gir1.2-gtk-3.0 python3-cairo python3-pil`.
  Nothing pip-installed, ever. GTK 4.14 is already importable here for
  future dual-path testing (do not flip — v1 is GTK3).

## Running the app

```bash
./run.sh                          # foreground
# persistent, survives the launching terminal/agent (the r051 lesson —
# plain background/setsid launches get reaped by agent harnesses):
systemd-run --user --unit=linprocman-app --setenv=DISPLAY=:0 \
    /usr/bin/python3 /home/user/projects/linprocman/src/main.py
systemctl --user stop linprocman-app      # to quit
wmctrl -i -a <window-id>                  # raise above other windows
```

Note for agent-driven sessions: `present()` does not defeat focus-stealing
prevention — a launched window can be mapped and pixel-verified yet buried
behind the foreground window. Verify visibility with a screenshot, raise
with `wmctrl -i -a` by window ID (the title substring also matches
file-manager windows whose path contains "linprocman" — always use the ID).

## Test tiers

| Tier | Command | What it proves |
|---|---|---|
| Unit + gates | `python3 -m pytest tests/ -q` | fixture-driven parsers, sampler math, schema, compat gates (raw-gi import ban, banned-API sweep scoped to UI trees, PyGIDeprecationWarning tier, no-claude-path, offline AST/argv) |
| Live kernel | `python3 -m pytest -m live -q` | readers + schema against the real /proc (own-pid invariants; no psutil dependency) |
| GUI walk | `DISPLAY=:0 python3 tests/live_gui_walk.py` | real navigation through NavigationManager + per-page screenshots |

The pixel rig is the operator's live X session (`:0`, `who` to confirm) —
no Xvfb needed on this machine. Settings keys for task 004 come from
[modules/persistence-config.md](modules/persistence-config.md),
[modules/graphs-hub.md](modules/graphs-hub.md) (Graphs feature).

Hardened-kernel degradation (hidepid, Yama ptrace_scope, dmesg_restrict)
shows as `lock` rows / "—" cells with no error — fixture-tested in
test_procfs.py; live behavior only differs on hosts with those settings.

Claims about UI require pixels of the real window — rendered-pixel rule
(project memory; GTK windows can't be verified through Firefox mocks).

## Gates (tests/test_gates.py)

- **Offline:** AST import allowlist + subprocess argv allowlist
  (sanctioned binaries: journalctl, dmesg — none in tree yet).
- **No-claude-path:** no file/dir named claude/CLAUDE.md/.claude anywhere.
- **Portability:** raw `gi.repository` imports only in
  `src/ui/compat/gtk_env.py`; banned GTK3-only APIs outside their compat
  adapters (sweep scoped to src/ui + src/pages — modules are provably
  GTK-free).
- **GLib-free core:** manager_sampler imports no gi/GLib (AST check).

## Task workflow (how changes get made)

1. Contract at `.zcode/tasks/NNN-<slug>.md` (goal/scope/rules/acceptance/
   report; riders attached). ZCode drafts or co-drafts with Claude.
2. Branch `task/NNN-<slug>`; executor (Claude Code, `claude -p` with
   `--permission-mode acceptEdits` — every dispatch needs the flag) writes
   code; it cannot run Bash or delete files.
3. ZCode verifies: scope diff vs branch base → pytest + live tier →
   gates → app smoke on :0 with pixel proof → merge (ff-only) to main.
4. Records: changelog entry (with executor cost), decisions.md if a
   decision was made, QUEUE.md status, ledger r-index.
5. Phase closes get an independent Claude review + operator gate + s009
   backup (`bash ~/projects/Zai-ZCode/s009_backup_project.sh <path> -m "…"`).

Schema changes cross the frozen 003→004 seam: C-review sign-off required
before dependents build (precedent: the mem_swap rejection, r048).

## Collaboration quick reference

- Dispatch: `claude -p "$(cat <contract>)" --permission-mode acceptEdits
  --output-format json --session-id <fresh-uuid>`; parse the json `result`,
  log `total_cost_usd`.
- Follow-ups: fresh session with prior conclusions embedded (held-open
  sessions reject `--session-id` resume with "already in use").
- Spend ledger: QUEUE.md bottom. Separation of duties: reviewer sessions
  never clear executor work; ZCode never both writes and clears.
- Session ids are strict UUIDs; friendly names fail silently (empty stdout).

## Repo records

- `changelog.md` — append-only, one entry per completed change (append
  discipline: old_string = last line, new_string = last line + new entry).
- `.zcode/memory/decisions.md` — architectural decisions with rationale.
- `.zcode/memory/pending.md` — carried-between-sessions work.
- `~/projects/Zai-ZCode/s-register.md` — r-index (response numbering) and
  artifact ledger.

## Known-good states

- HEAD of main is always green (merge only after the full chain passes).
- Mockup browsing: `cd docs/mockups && python3 -m http.server 8931
  --bind 127.0.0.1` (loopback only; stop when done).
