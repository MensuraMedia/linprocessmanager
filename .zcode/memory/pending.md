# Pending

- Task 014 — Logs saved views + flags (mockup F): next executor dispatch
  after the operator confirms the saved-view UX.
- Task 015 — Logs frequency analysis (mockup G): after 014; reuses the
  013 engine seam.
- Network v2 — per-app monitor pane + history pane (mockups Q2/Q3
  CONFIRMED as design directions): needs the per-app ring allocation
  policy sign-off (bounded tracked-app set, eviction) before build.
- Disks v2 — per-mount capacity sparklines (spec'd, disks-capacity.md §3).
- Small carried items: Basics late-render check on hub visit; chooser
  confirmation pass; Network rows for restricted-only pids show "—" rates
  by design (Yama).
- fit_source_id journal spam: FIXED r136 — watch one resize cycle for
  regression.
- Remind operator: the app currently runs from the linprocman-app transient
  unit; a machine restart needs:
  systemctl --user reset-failed linprocman-app 2>/dev/null
  systemd-run --user --unit=linprocman-app --setenv=DISPLAY=:0 /home/user/.local/bin/linprocman
