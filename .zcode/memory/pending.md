# Pending

- Operator review requested: docs/executor-collaboration.md (r041) — approve
  the ZCode⇄Claude Code executor design and the pilot (task 001 = Phase 1
  data core). If approved, first dispatch verifies two assumptions: Claude
  Code native AGENTS.md reading; acceptEdits Bash behavior in -p mode.
- Operator must review the adversarially re-cut plan (concept §9 phases 1–8),
  the logs mockups E/F/G/H at docs/mockups/index.html, and the sidebar width
  study (H: 150/170/190 — 170 recommended). Direction decisions still open:
  primary layout (A?), CPU % normalization default, refresh default, kernel
  threads hidden, pulse vs gauge brand mark, logs submenu/organize model,
  context-menu + Frequency scope as designed, sidebar width pick (170?).
- Implementation not started. Phase 1 runs as executor task 001 once the
  collaboration design is approved.
- Remind operator: open ~/projects/linprocman as the ZCode workspace for
  working sessions.
- Mockup HTTP server (port 8931) may still be running in the linfilesearch
  session — stop it when done viewing.



- Task 002 cleanup riders: stale strings in page_settings.py, window title
  'Dashboard' → 'linprocman' (executor flagged both as out-of-scope).
- Phase 2 (live table: sampler → flat table, diff-in-place, sort/filter,
  VmSwap, keyboard, settings skeleton) is the next contract to draft.
- MACHINE RESTART PENDING (2026-09-27 evening): app stopped via
  `systemctl --user stop linprocman-app`. After reboot relaunch with:
  systemd-run --user --unit=linprocman-app --setenv=DISPLAY=:0
  /home/user/.local/bin/linprocman
  Then verify per docs/HANDOFF.md §3 (tests → live walk → journal).
- Next work cycle: task 010 (preview pane per process-preview.md + chart
  double-click → per-metric contributor pages), then Disks build-out and
  Peripherals per operator mandate (mockups first, concept docs updated).
- issues.md tail entries are historical (all resolved by r073/r075) — keep
  for triage context only.

- r081 leftovers: (1) group-action permission-guard test was dropped in the
  r075 churn with no replacement — re-add; (2) unchecking the LAST visible
  column silently resets to all-columns on next launch (_validate_columns
  divergence) — decide policy; (3) tray fallback logs a StatusIcon
  set_title attr error before ayatana resolves — downgrade or guard;
  (4) Disks + Peripherals mockups await operator pick, then concept docs
  update + contracts.
