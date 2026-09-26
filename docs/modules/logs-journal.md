# Module doc — system logs (`src/modules/manager_logs.py` + `src/pages/page_logs.py`)

Part of the linprocman modular docs. Siblings: [log-frequency.md](log-frequency.md) ·
[procfs-data.md](procfs-data.md) · [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[disks-filesystems.md](disks-filesystems.md) · [sysfs-data.md](sysfs-data.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Operator-mandated feature (r039): system logs in the sidebar as a **submenu**,
searchable, organizable. Source of truth: the systemd journal via the local
`journalctl` binary — zero new runtime deps, no python3-systemd, no sockets.

## Sidebar submenu

```
Logs ▸                    (scroll icon, expandable group in the sidebar nav)
  Journal                 all fields, default view
  Kernel                  preset:  journalctl -k
  Auth                    preset:  facility auth,authpriv (+ sudo/sshd emphasis)
  Applications            preset:  user units / _UID = current user
  Saved Views …           operator-defined named filter sets (see Organize)
```

Presets are one engine with canned filters — not separate backends. dmesg and
`~/.xsession-errors` are fallback sources only if journalctl is absent;
`/var/log/*.log` file parsing is out of scope for v1 (journald is universal
on Mint/Debian).

## Interface

Provides: a log view = (source preset, filter set, loaded window, follow
state); rendered by the same typed TreeModel + `set_cell_data_func` machinery
as the process table. Priority coloring is theme-derived: err/alert red,
warning amber, notice/info default, debug dimmed.

Consumes: `journalctl` subprocess; filter/search model shared with the table
layer's substring/regex matcher (regex = stdlib `re`, toggleable, case toggle
`text-aa`).

## journalctl subprocess contract (security boundary)

- **argv list only, never `shell=True`.** User input enters exclusively in
  `=`-form flags: `--grep=…`, `--unit=…`, `--since=…`, `--until=…` — a value
  can never be reparsed as a flag (`-n`, `-D /path`, `--merge`).
- Spawn: `GLib.spawn_async_with_pipes` + `GLib.io_add_watch` on stdout;
  **line reassembly buffer** (JSON lines can split across chunk boundaries);
  child reaped via `GLib.child_watch_add`; killed on page switch/window
  close; respawned if journald restarts (exit-with-nonzero + cursor known).
- **Bounded fetch:** initial load `--no-pager -n 2000` max; older history via
  `--cursor=` paging on demand ("load older" row); hard cap on retained lines
  in the view model (default 20k, drop-oldest with a dropped counter).
- **Follow mode:** `-f -o json --cursor=<last>`; cancel-in-flight when the
  query changes (kill + respawn) — never two writers into one view.
- Burst handling: coalesce appends per idle tick, cap per-tick insert count,
  drop-oldest beyond the cap (a crash-looping service must not freeze the UI).

## Row context menu (right-click, r040)

Every log row opens a context menu; items act on the row:

| Item | Icon | Action |
|---|---|---|
| Copy message | `copy` | raw MESSAGE to clipboard |
| Copy entry as JSON | `file-text` | the full journalctl JSON object |
| Flag this entry | `flag` | cursor-anchored flag (organize model above) |
| Filter by this unit | `funnel` | sets `unit:` chip to the entry's unit |
| Focus this message pattern | `crosshair` | filters the view to the normalized pattern |
| **Frequency…** | `chart-bar` | opens the frequency analysis view — [log-frequency.md](log-frequency.md); offered on all rows, self-tuned for warning/err |
| Export current view… | `download-simple` | CSV/text export |

Keyboard: Menu key opens it on the cursor row. The Frequency entry shows the
resolved pattern as its submenu label ("Frequency of 'I/O error, dev P,
sector N'…") so the heuristic is visible before committing.

## Search & organize

- **Search:** case-insensitive substring default; regex toggle; time-jump
  (`--since/--until` via `calendar-blank` popover); matches highlight, count
  in the status line; Enter cycles through matches.
- **Organize = Saved Views + Flags.** A Saved View is a named filter set
  `{preset, units[], priorities[], since, query, regex, case}` persisted in
  settings.json (persistence-config.md) and shown as submenu children
  (`notebook`); create from the current view with `bookmark-simple`. A Flag
  is a cursor-anchored bookmark on one entry, collected in a "Flags" view
  (`flag`) — jump back to that point in the journal. No line tagging, no
  local database, v1.
- **Export:** current view to CSV/text via FileChooser (download icon) — the
  one sanctioned user-directed write outside the XDG config dir.

## Permissions & degradation (probe, never elevate)

Capability probe at startup per source: `os.access` + trial run/read.
This machine (verified 2026-09-26): user in `adm`, journalctl and
/var/log/syslog readable, `dmesg_restrict=0`. On other Mint/Debian boxes a
user outside `adm`/`systemd-journal` sees only their own user journal, and
`dmesg_restrict=1` blocks the kernel fallback. Restricted sources render a
`lock` row with the exact remedy text ("add user to adm or systemd-journal")
— never a sudo/pkexec hint, per build-principles §5. **Empty ≠ locked
(r042):** a source that probes OK but returns zero entries shows "no
entries match / none in retention" — it must never tell a user who already
has access to go join a group. Volatile-only journals
(no /var/log/journal) lose history on reboot — stated in the empty view.

## Tests

argv-builder units (user input always lands in `=`-form values, no flag
injection), JSON line reassembly across splits, drop-oldest cap, saved-view
serialize/round-trip, permission-probe degradation table, follow
respawn/cancel state machine.
