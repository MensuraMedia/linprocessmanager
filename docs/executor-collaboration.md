# ZCode ⇄ Claude Code collaboration — the zcode-executor mechanism

Status: proposed for operator approval (r041, 2026-09-26). Nothing in here has
been executed yet — this is the design; the pilot (§8) runs only after
approval.
Scope: building linprocman from this ZCode session and from future sessions
in the linprocman workspace.
Doctrine basis: universal-instruction-set v2026.04 (vendored master at
~/doctrines/universal-instruction-set); the universal-polyglot standard
(Draft 1, 2026-08-18, never adopted) supplies the topology analysis — this
document adopts its **T2 delegation topology with the roles inverted** for
this project.

## 1. Ground truth — verified on this machine (2026-09-26)

| Fact | Status |
|---|---|
| Claude Code `2.1.282` at `~/.local/bin/claude`, `~/.claude` populated, daemon running | verified |
| Headless flags: `-p/--print`, `--output-format` (incl. json), `--append-system-prompt`, `--permission-mode`, `--add-dir`, `--model`, `--session-id`, `-c/--continue`, `--agents`, `--dangerously-skip-permissions` | verified via `claude --help` |
| `zcode` CLI at `~/.local/bin/zcode` (ZCode 3.14.3 AppImage install) | verified |
| No tool named "zcode-executor" exists in Zai-ZCode, doctrines, or PATH | verified — the name is *defined* by this document |
| Claude Code reads `AGENTS.md` as project memory natively | **assumed** — verify in the pilot before relying on it |
| A `--append-system-prompt-file` variant exists | unclear from help truncation — verify; inline `--append-system-prompt` is the safe path |
| Doctrine polyglot standard exists as an unadopted draft | verified (T1 substitution disqualified; T2 delegation recommended; phase-ownership and routing-gate models) |

## 2. Topology decision

**T2 delegation, inverted: ZCode (GLM) orchestrates; Claude Code executes.**

- **ZCode owns** — planning, module docs, task contracts, verification, the
  changelog/ledger/decisions records, adversarial review (red-team skill),
  and the operator gate. Everything through r040.
- **Claude Code owns** — implementation turns: writing `src/` code against
  the module docs' interfaces, refactors inside a task branch, fixture and
  test authoring. It never edits the binding docs (build-principles,
  module docs), never records ledger/changelog entries, never merges.
- **T1 substitution is disqualified** (doctrine §02): pointing one harness
  at the other's model is a swap, not collaboration.
- **T3 peer exchange is the fallback**, not the default: for
  whole-repository sweeps too large for a single task contract, Claude Code
  works on a branch and git is the audit log — but every handoff re-builds
  context, so task files (§4) stay the primary mechanism.
- **T4 external orchestration is rejected** — we already own a loop, two
  harnesses, and an audit trail; a third orchestrator buys nothing.

Doctrine phase ownership, mapped:

| Phase | Owner | Notes |
|---|---|---|
| P1 Specify | ZCode | task contracts from module docs; decisions.md entries |
| P2 Implement | Claude Code (executor) | on a task branch, scope-limited |
| P3 Verify | ZCode + independent agents | separation of duties (doctrine §03): **the writer never clears its own work** — ZCode runs tests + gates + adversarial pass |
| P4 Release | operator + ZCode | merge to main, changelog, backup (s009), version |

## 3. Trust boundary and data classification (doctrine G1)

linprocman payloads are **C1 — proprietary, non-personal**: own source,
docs, plans. No PII, no credentials, no user data — settings.json is UI
preferences. C3 (secrets) and C2 (regulated personal data) do not exist in
this repo and must never appear in a task file; the task-contract template
states this and ZCode reviews each task file before dispatch. Claude Code
runs on the operator's existing Anthropic account — the same arrangement
already in place for every other project on this machine; no new egress is
created by this document.

The app's offline mandate is untouched: it binds `src/` at runtime, not the
build tools. The AST/argv gates police the app; dev tooling (claude CLI,
firefox, pytest) is tooling.

## 4. The task contract (the coupling artifact)

Tasks live in-repo at `.zcode/tasks/NNN-<slug>.md` — copy-not-reference:
each task is self-contained and survives machine moves. Sections:

```
# Task NNN — <title>
Phase: <roadmap phase>     Branch: task/NNN-<slug>
Goal: one paragraph
Scope: explicit file/dir list — anything else the executor touches is a defect
Read: module docs + build-principles paths (executor must read these first)
Constraints (verbatim): offline app code; AST/argv gates; icons only from
  resources/icons; NEVER create files or dirs named 'claude' or 'CLAUDE.md'
  or '.claude' anywhere in the repo; no pip/venv; python3 system only
Acceptance: the module doc's Tests section, verbatim, plus: pytest green,
  gates green, git diff touches only Scope
Report: what changed, what was skipped, open questions — as the final message
```

ZCode writes the contract (P1), the operator may amend, then it is
dispatched. Task files are committed — they are the audit record.

## 5. Tooling — invocation and lifecycle

**Dispatch (ZCode → executor), verified flags:**

```
cd ~/projects/linprocman
git switch -c task/001-vendor-starter
claude -p "$(cat .zcode/tasks/001-vendor-starter.md)" \
  --permission-mode acceptEdits \
  --output-format json \
  --session-id <recorded-uuid> \
  --model <operator-chosen; default account default>
```

- **Attended vs unattended.** Default is `acceptEdits` (edits auto-applied,
  shell commands still gated — executor pauses if it needs one, ZCode sees
  the wait and decides). `--dangerously-skip-permissions` is **opt-in per
  task by the operator only**, never a default, and is recorded in the
  changelog entry for that task.
- **Continuation.** `--session-id` + `-c` lets ZCode send follow-up turns
  to the same executor conversation (fix-the-failures loops) without
  re-establishing context.
- **Result.** `--output-format json` gives ZCode a machine-readable result
  (cost/token counts logged into the changelog entry — additive tracking).
- **Memory rules.** The executor gets context from the task file and the
  repo's own `AGENTS.md`/module docs — never from a `CLAUDE.md` (which
  must not exist here; global operator rule). If Claude Code's native
  AGENTS.md reading is confirmed (pilot step 1), nothing else is needed;
  otherwise the task contract embeds the project rules verbatim.
- **Executor never merges.** Work happens on `task/NNN-*`; main stays
  always-green by construction.

**Verification (P3, ZCode-owned, in order:**

1. `git diff --name-only main..task/NNN-*` — scope check; out-of-scope
   files = defect, task rejected.
2. `python3 -m pytest tests/ -q` — green.
3. Gates: AST import allowlist + subprocess argv allowlist
   (build-principles §4) + no-'claude'-path sweep of the repo.
4. UI work additionally: rendered-pixel verification (headless-Firefox rig)
   — the r036/r039 lesson stands: no claim without pixels.
5. Optional independent adversarial pass (red-team skill) on the diff.

**Release (P4):** ZCode fast-forwards main, appends the changelog entry
(task, branch, scope, result, cost), records decisions if any, commits,
backs up (s009) at phase boundaries per the global backup standard.

## 6. Administration through this session and later ones

- **This session:** ZCode orchestrates via its Bash tool (`claude -p …`);
  the executor's turns appear here as tool calls; every dispatch and result
  is summarized to the operator. Response numbering stays ZCode's r-index;
  executor work is logged as `executor task NNN` changelog lines, not as
  r-numbers.
- **Future sessions (linprocman workspace):** this document + decisions.md
  carry the mechanism; the SessionStart context injects the pending task
  list. No session-local state is load-bearing.
- **Ledger:** the wrapper (§7) becomes an sNNN artifact when implemented;
  until then dispatches are inline Bash. Every executor task is recorded.
- **Costs:** token/cost counts from the json output go into each changelog
  entry. Doctrine P6 (tiered cost): executor model choice is the
  operator's; ZCode does not silently re-tier.
- **Failure modes and handling:**

| Failure | Handling |
|---|---|
| Executor waits on a permission prompt | visible as no-output; ZCode re-dispatches attended or narrows scope |
| Executor drifts beyond Scope | scope check fails the task; fix on the same session-id or reject |
| Executor invents network/pip usage | gates fail the task; contract violated — reject, not repair |
| Task contract ambiguous | executor's Report section surfaces it; ZCode amends the contract, re-dispatch |
| Session context lost | task files are self-contained; `--session-id` continuation or fresh dispatch |

## 7. The wrapper (future sNNN artifact — after approval)

A thin `sNNN_executor_task.sh` will formalize: contract lint (sections
present, no C2/C3 patterns, scope lists existing paths), dispatch with
recorded session-id, json-result capture, and the verification chain
(§5). Kept deliberately dumb — the intelligence is in the contracts and
the docs, not the wrapper. Not written yet: the artifact protocol requires
operator review of this design first.

## 8. Pilot (proposed, not started)

**Task 001 — Phase 1, data core.** Vendor the starter into `src/`, replace
`run.sh` with the direct launcher, implement `procfs.py` + `sysfs.py`
readers with fixtures per [modules/procfs-data.md](modules/procfs-data.md)
and [modules/sysfs-data.md](modules/sysfs-data.md). This is the right pilot
because it exercises everything: contract discipline, scope limits, the
gates, fixtures-first testing, and the merge gate — on the phase with the
most hostile-fixture precision and the least UI ambiguity.

Pilot exit criteria: pytest green from a clean checkout, gates green,
scope clean, executor Report read by the operator, one changelog entry
with cost data, backup taken. If the pilot shows the collaboration is not
worth its overhead, the correct outcome is to say so and stop (doctrine
§08 step-3 logic applies verbatim).

## 9. Compliance vs build-principles

| Principle | Status |
|---|---|
| Copy, not reference | task contracts are in-repo files; no runtime cross-loads |
| Portable | repo + claude CLI + task files; nothing machine-specific beyond the account |
| Immutable foundation | adds `.zcode/tasks/`; modifies no universal file |
| Additive customization / tracking | changelog gains executor entries; git unchanged |
| Tiered cost | executor model is an explicit operator choice per task family |
| Platform-native | `claude -p` is the official headless surface; no adapters |
| Language-agnostic | the mechanism is process-boundary, Python-irrelevant |
| No-'claude'-path rule | contract constraint + verification sweep — the executor works in this repo without ever creating Claude-native memory files |

## 10. Not verified (honest list)

- Claude Code native `AGENTS.md` reading (assumed; pilot step 1).
- `--append-system-prompt-file` existence (use inline form).
- `acceptEdits` exact behavior for Bash in `-p` mode (pilot will reveal).
- Claude pricing/token accounting fields in the json output.
- No executor dispatch has run; every invocation line above is designed,
  not executed.
