# linprocman — orchestration queue

The working plan. Players: **Z** = ZCode (plan, contracts, verify, records),
**C** = Claude Code (independent review, technical expert, executor),
**OP** = operator (decisions, phase gates, backups trigger s009 anyway).
Every task = one contract at .zcode/tasks/NNN-*.md, one branch, one
verification chain (scope → pytest → gates → smoke/pixels → merge).
Reviews: every phase close gets an independent C pass; OP gates each phase.

## Standing roles

| Player | Owns | Never |
|---|---|---|
| Z | contracts, module docs, verification, changelog/ledger/decisions, merges | writes feature code inside a task's scope |
| C-executor | implementation on task branches, Report | merges, edits binding docs, records ledger entries |
| C-reviewer | independent findings (docs pre-commit, phases pre-merge) | clears its own executor work (separation of duties) |
| OP | direction decisions, phase gate, pkexec/bypass opt-ins | — |

## Queue (phases from concept §9; local resources per scope: fixtures
tests/fixtures/, icon master ~/projects/assets/icons, X11 :0 pixel rig,
system python3 — no network for app code, ever)

| # | Task | Phase | Player split | Status |
|---|---|---|---|---|
| 001 | data core (procfs/sysfs, launcher, nav shell) | 1 | Z contract/stage → C execute → Z verify | **merged 7e9e05a** |
| 002 | compat module + gate tiers + Application lifecycle + riders | 2a | Z contract → C execute → Z verify | **merged 2520d31** |
| 003 | sampler pipeline (logic-only: snapshot, rates, watchdog, queue) | 2b | Z+C co-draft → C execute → Z verify + C-review (logic-heavy) + **schema-freeze sign-off before 004** | **merged 2381dda + mem_swap fix; schema signed at 20 fields** |
| 004 | flat table UI (diff-in-place, sort/filter, selection, VmSwap, keyboard, row budget) + settings skeleton | 2c | Z contract → C execute → Z verify (pixels) | **merged ad3279d — LIVE TABLE pixel-verified** |
| 005 | phase-2 close: independent C review + fixes | 2-close | C-review + Z fixes → OP | **done 9bb8496 + backup 194655** |
| 006 | actions & safety (context menu, signals, renice, affinity) | 3 | Z contract → C execute → Z verify + live drives | **merged 3ee141d — live drives PASS** |
| 007–009 | preview pane (mockup J) + metric band (mockup K) / resources+sensors / disks | 4–6 | same pattern per module doc | queued |
| 010+ | logs engine + views + frequency (three tasks: engine, views+menu, frequency) | 7 | same pattern; argv-contract tests first | queued |
| 0xx | installer + .deb spec + v1 tag | 8 | Z contract → C execute → OP gate | queued |

## Riders (attached to nearest task)

- ✅ window title 'Dashboard' → 'linprocman' (r042 flag) — in 002
- ✅ stale page_settings strings (r042 flag) — in 002
- mockup C stacked-chart visual note — already matches whole-machine
  normalization (r042 fix); no action

## Session spend ledger (C engagements)

| r | role | cost |
|---|---|---|
| r042 | AGENTS.md probe + design review + task-001 execution | $0.01 + $0.89 + $6.08 |
| r043 | gtk4-port factual review | $0.35 |
| r044 | upgrade-architecture factual review | $0.49 |
| r045 | debian-compatibility factual review | $0.49 |

## Work order r081 (2026-09-27, operator) — DONE

Adversarial follow-up on the last-10 feature requests + corrections.
Orchestration: Z fixed/verified → adversarial verifier (subagent) checked
every item → Z applied verifier findings → C cross-review of da875fc
(design/philosophy guardrail, plan-mode consult). Agents checked each
other's work in that chain.

- Header right-click opens the column chooser again (bin-window coords;
  the process menu had swallowed header + margin clicks).
- Graphs caret toggles Basics down/up; groups start collapsed again.
- Band-chart click → Basics + auto-expanded Graphs group + highlight moves.
- Adversarial: 9/10 requests ACCOMPLISHED; r071 thresholds PARTIAL → P1
  fixed (baseline startup call restored, live-verified in the journal).
- P2s fixed: N_COLUMNS off-by-one; dead rank-popover machinery deleted;
  page_resources.py removed. 243+5 tests. Mockups: Disks + Peripherals
  served at :8931 for operator review (Phase 6 / Peripherals decision).

| r081 | design/planning consult + cross-review of da875fc (plan mode, read-only) | cost not captured by harness — first plan-mode dispatch; verdict FIX-FIRST (P2-1 caret real-event proof) → fixed in r081b |
