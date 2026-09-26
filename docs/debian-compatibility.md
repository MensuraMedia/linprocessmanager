# linprocman — Debian-family compatibility

Status: planning document (r045, 2026-09-26). Third leg of the trilogy:
[gtk4-port.md](gtk4-port.md) (the port) · [upgrade-architecture.md](upgrade-architecture.md)
(the upgrade structure) · this document (the distribution matrix those must
hold across). Collaborator-reviewed before commit.

## 1. The target matrix — version ground truth

| Base (representative distros) | Python | GTK3 | GTK4 | PyGObject | Confidence |
|---|---|---|---|---|---|
| Ubuntu 22.04 jammy (Mint 21.x, Pop!_OS 22.04) | 3.10 | 3.24.33 | 4.6 | 3.42 | knowledge, stable |
| Debian 12 bookworm (LMDE 6) | 3.11 | 3.24.3x | **4.8.3** | 3.42 | knowledge + review |
| Ubuntu 24.04 noble (Mint 22.x — **this machine**) | 3.12 | 3.24.41 | 4.14.5 | 3.48 | **verified locally** |
| Debian 13 trixie (LMDE 7) | 3.13 | 3.24.4x | **4.18.6** | **3.50.0** | **verified via packages.debian.org (r045)** |
| Ubuntu 26.04 LTS (next Mint base) | **3.14** | 3.24.x | 4.18+ (exact unconfirmed) | 3.50+ | partially verified (search) |

Policy: **support the current + previous LTS bases** (today: noble + jammy,
trixie + bookworm; 26.04-era when Mint 23 lands). Older bases run at their
own risk — nothing forbids it; nothing tests it.

## 2. Version floors (the contract)

| Component | Floor | Why |
|---|---|---|
| Python | **3.10** (jammy) | core is stdlib-only; 3.10 syntax covers the whole matrix |
| GTK3 (v1) | **3.24** | every base ships it; event controllers exist here |
| GTK4 (port era) | **4.6** (jammy — the only 4.6 base; bookworm is 4.8) | everything the port needs exists at 4.6; **≥4.10 conveniences (AlertDialog) sit behind feature probes, never bare calls** |
| PyGObject | **3.42** (jammy) | GTK4 bindings floor; 3.48+ on noble |
| kernel | **4.20** effectively | PSI (all supported bases qualify); smaps_rollup ≥4.14 |

Feature-probe pattern: `compat/gtk_env.py` exports `HAS_*` capability flags
(minor-version checks) the same way it exports `GTK_MAJOR` — UI code asks
the flag, never the version number. The port doc's "AlertDialog only
behind a version check" becomes the general rule.

## 3. Python-syntax discipline

- Core (procfs/sysfs/sampler/actions/frequency) stays **3.10-compatible
  syntax + stdlib only**: no 3.11+-only syntax (except*-groups, Self,
  tomllib) and no 3.11+-only stdlib modules without a guarded fallback.
  With a stdlib-only core this is nearly free.
- The gate can't fully prove 3.10 syntax from a 3.12 interpreter (it
  accepts everything newer); enforcement is: contract rule in every
  executor task + `python3.10 -m py_compile` over `src/modules/` whenever
  a 3.10 interpreter exists on the machine (jammy-era chroot or CI guest).

## 4. Dependency truth across the matrix

The entire runtime need is four system packages, present by that name in
every base above:

| Need | Package (all bases) |
|---|---|
| GTK bindings | `python3-gi` + `gir1.2-gtk-3.0` (port era: `gir1.2-gtk-4.0`; this also provides the freedesktop typelib pycairo does NOT pull — review correction) |
| cairo | `python3-cairo` (depends only on `libcairo2` + `python3`) |
| icon tint | `python3-pil` |
| interpreter | `python3` (≥3.10) |

No pip, no venv, no compiled extensions of ours, `Architecture: all`.
That is the whole compatibility surface — by mandate.

## 5. Kernel-feature reality across bases

| Feature | Variance | Behavior |
|---|---|---|
| systemd journal | universal on all targets | primary logs source |
| `/proc/pressure` (PSI) | needs kernel ≥4.20 **and `CONFIG_PSI` enabled** (some kernels ship it default-disabled; `psi=1` boot arg) | chips; absent → hidden |
| `smaps_rollup` | present ≥4.14 | selected-process PSS |
| cgroup v2 | unified default since Debian 11 | `parse_cgroup` fallback already handles hybrid/no-v2 |
| `hidepid` | varies by admin, not distro | locked-row taxonomy (r039) |
| **Yama `ptrace_scope=1`** (Ubuntu/Mint default — review addition) | blocks reading `/proc/<pid>/{smaps_rollup,environ,mem}` of non-owned processes without CAP_SYS_PTRACE | same locked/"—" degrade path as hidepid — the details pane shows `lock` for other users' PSS on stock Ubuntu/Mint; rule added to the r039 taxonomy |
| `dmesg_restrict` | 0 on Mint, 1 on hardened Ubuntu | probe-and-degrade (r039) |
| hwmon/fans/GPU sysfs | hardware variance | chips hide themselves (r039/r042) |

The degrade-never-fail rules built in r039 are exactly the Debian-matrix
strategy: every variance above already has a defined graceful path.

## 6. Packaging & desktop integration

- **v1: `install.sh`** (the linfilesearch-proven pattern) — icons to
  `~/.local/share/icons/hicolor/`, launcher to `~/.local/bin/`, `.desktop`
  to `~/.local/share/applications/` with `StartupWMClass`, `--uninstall`
  preserves config. Pure-user, works identically on every base above.
- **Later: `.deb`** (roadmap Phase 8 candidate): `Architecture: all`,
  built with `dh_python3` so `${python3:Depends}` is generated (Debian
  Python Policy) plus `${misc:Depends}`; hand-listed runtime needs per §4;
  files land in `/usr/lib/linprocman` + `/usr/share/{applications,icons}`;
  packaged launcher shebang is `#!/usr/bin/python3` — never
  `/usr/bin/env python3` (Lintian `wrong-path-for-interpreter`).
  **No maintainer-script cache calls:** the `hicolor-icon-theme` dpkg
  trigger handles icon cache, and with no `MimeType=` there is nothing for
  `update-desktop-database` to do (if a MimeType is ever added,
  desktop-file-utils ships its own trigger). Optional store visibility:
  AppStream metainfo in `/usr/share/metainfo/`. Lintian-clean hygiene:
  `debian/copyright`, Debian-format changelog, a manpage. The legacy
  Debian menu system was removed in bookworm — `.desktop` only, by design.
  usrmerge is a non-issue for a pure-Python `Architecture: all` package.
- **Explicitly rejected: snap and flatpak.** Honest grounds (review
  correction): snap strict confinement *could* technically observe and
  signal host processes via the `system-observe` + `process-control`
  interfaces (and classic runs unconfined) — the real objections are the
  offline/no-store-runtime mandate plus manual interface-connection
  friction. Flatpak is a hard technical no: its own PID namespace with no
  host-process portal is incompatible with a process manager's purpose.
  Deb-native only.
- **Desktop shells:** Cinnamon/MATE/XFCE/GNOME/KDE/budgie all honor the
  same `.desktop` + StartupWMClass + hicolor contract; no shell-specific
  code (and no libadwaita — decided in gtk4-port.md §6).

## 7. Display servers & security contexts

- X11 and Wayland both supported (GTK-native); the one Wayland gap
  (occlusion-aware backoff) is documented in sampling-pipeline.md.
- AppArmor (Ubuntu/Mint default profiles) does not restrict an
  unprivileged reader of /proc or sender of signals to own processes — no
  profile shipped; nothing to conflict with distro policy.

## 8. Gate additions (compat tier)

1. `.desktop` file lint (Desktop Entry spec keys, StartupWMClass present,
   icon names resolve to installed hicolor files).
2. `install.sh` round-trip test (install → uninstall → reinstall,
   config-preservation assertion) — the linfilesearch r022 pattern.
3. Deps-comment sync: `requirements.txt` names exactly the four packages
   of §4 (drift fails).
4. The banned-API and import-law gates from the companion docs already
   police the toolkit matrix; this tier polices the *distribution* matrix.

## 9. Test honesty

Verified on this machine: Mint 22.3/noble only. The matrix above is
documented, not continuously tested; opportunistic verification happens
when other bases are at hand (jammy-era chroot, an LMDE box). The floors
are chosen precisely so the gap between "documented" and "tested" stays
boring.

## 10. Not verified

- Exact GTK4 version in Ubuntu 26.04 (only "GTK4-era apps" confirmed;
  check packages.ubuntu.com when it matters).
- GTK3 3.24.x micro version in trixie (irrelevant at our API level).
- `.deb` buildability (Phase 8 item; spec above is the design).
- Behavior under Debian's stricter defaults for `dmesg_restrict` in some
  derivatives (degradation path is designed and unit-tested, not
  machine-tested).
