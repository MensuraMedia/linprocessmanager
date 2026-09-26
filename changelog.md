# Changelog — linprocman

Append-only. Newest entries at the bottom. One entry per completed change.

## 2026-09-26
- Project bootstrapped with development standards (s003_a).
- Technical concept + 4 UI mockups (r036): docs/process-manager-concept.md written — /proc-first data layer (zero runtime deps beyond starter), sampler-thread → queue → idle_add pipeline, jiffy-delta CPU% math, typed TreeView columns with diff-in-place updates, (pid, starttime) recycle guard, smaps_rollup for selected process only, cairo ring-buffer graphs, PSI chips; machine facts verified (kernel 7.0.0-31, PSI present, smaps_rollup readable, CLK_TCK=100, psutil 5.9.8 present but dev-only). Phosphor subset staged: 44 regular + 10 fill (resources/icons/, manifest.txt). Mockups A processes+details / B tree / C resources / D action dialogs built on the starter palette, rendered headless-Firefox to PNG and pixel-verified (crop probes disproved an initial false 'broken icons' report on B). Initial commit.

