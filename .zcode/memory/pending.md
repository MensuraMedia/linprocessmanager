# Pending

- Operator must review docs/process-manager-concept.md and pick a mockup
  direction (A processes+details is the primary candidate).
- Open decisions (concept §8): primary layout; CPU % normalization default;
  refresh defaults (2 s table / 1 s graphs); kernel threads hidden default;
  brand mark pulse vs gauge.
- Starter not yet vendored into src/ — roadmap step 1 in the concept doc.
- Then: procfs.py readers + fixture tests → sampler → flat table → actions →
  tree → details → resources graphs → settings/installer.
- Remind operator: open ~/projects/linprocman as the ZCode workspace for
  working sessions (context injection applies there).
