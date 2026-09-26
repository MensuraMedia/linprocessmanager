# Changelog — linprocman

Append-only. Newest entries at the bottom. One entry per completed change.

## 2026-09-26
- Project bootstrapped with development standards (s003_a).
- Technical concept + 4 UI mockups (r036): docs/process-manager-concept.md written — /proc-first data layer (zero runtime deps beyond starter), sampler-thread → queue → idle_add pipeline, jiffy-delta CPU% math, typed TreeView columns with diff-in-place updates, (pid, starttime) recycle guard, smaps_rollup for selected process only, cairo ring-buffer graphs, PSI chips; machine facts verified (kernel 7.0.0-31, PSI present, smaps_rollup readable, CLK_TCK=100, psutil 5.9.8 present but dev-only). Phosphor subset staged: 44 regular + 10 fill (resources/icons/, manifest.txt). Mockups A processes+details / B tree / C resources / D action dialogs built on the starter palette, rendered headless-Firefox to PNG and pixel-verified (crop probes disproved an initial false 'broken icons' report on B). Initial commit 1978dd7.
- Operator mandates applied (r036): docs/build-principles.md added — universal-instruction-set v2026.04 fundamentals, modularity/universality product mandate, local-only assets (Phosphor master ~/projects/assets/icons, copy-not-reference), fully offline app (no network imports — grep-gated, system packages only, direct python3 launcher replacing the starter's venv run.sh). AGENTS.md project rules + concept §1/roadmap updated to match.
- Modular docs split (r037): grouped logic broken into docs/modules/ — procfs-data, sampling-pipeline, process-table, actions-permissions, resource-graphs, persistence-config; each declares purpose/interface/logic/tests. process-manager-concept.md reduced to overview + module index + cross-cutting risks/roadmap; per-module risks moved into their docs. Module boundaries made explicit: only procfs.py reads the kernel, only manager_actions.py mutates, pages consume snapshots.


