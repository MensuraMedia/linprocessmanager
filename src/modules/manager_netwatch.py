"""Net watch — per-process network tracking, marks, and pattern classes.

Core, UI-free, stdlib only. Three jobs for the Network page (r133):

1. **Importance marks** — user-assigned low/medium/high per process name,
   persisted to ``~/.config/linprocman/netwatch.json`` (survives restarts;
   keyed by process NAME so marks follow the program, not the pid).
2. **Tracking rings** — ``track(key, name)`` starts a bounded sample ring
   for one process: every snapshot the page appends ``(ts, rx, tx, conns)``.
   Ring law: bounded deque, gaps are gaps, no interpolation.
3. **Pattern classification** — :func:`classify_activity` turns a ring into
   a verdict: ``regular-intervals``, ``irregular-spikes``, ``quiet``,
   ``telemetry-like`` (a SUB-PATTERN of regular: steady small uploads —
   labelled "telemetry-like", never "telemetry": the r055 honesty rule —
   a heuristic pattern match is not proof), or ``insufficient-data``.

Every verdict carries its evidence (numbers, not adjectives) — the r055
lesson: category names describe measured reality, and the UI states that
classification is heuristic.
"""

import json
import os
import statistics
from collections import deque

try:  # app layout: python3 src/main.py (src on sys.path)
    from modules import procfs
except ImportError:  # standalone/test layout (src/modules on sys.path)
    import procfs

RING_MAX = 180          # samples per tracked process (~6 min at 2 s)
MIN_SAMPLES = 12        # classification needs at least this much history
STORE_NAME = "netwatch.json"

CATEGORIES = ("regular-intervals", "telemetry-like", "irregular-spikes",
              "quiet", "insufficient-data")


def _default_store_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "linprocman", STORE_NAME)


def classify_activity(samples, *, cadence_s=2.0, min_samples=MIN_SAMPLES):
    """Classify a chronological sample ring ``[(ts, rx, tx), …]``.

    Returns ``{"category": str, "evidence": str, "active_fraction": float,
    "median_interval_s": float|None, "spikes": int}``. Pure + deterministic.

    Categories (measured, heuristic):
      regular-intervals — activity in ≥ half the ring at a steady cadence
                          (interval CV < 0.35).
      telemetry-like    — regular AND the median active volume is small
                          (≤ 4 KB) AND tx-leaning or balanced. A PATTERN
                          name, not an accusation.
      irregular-spikes  — activity is sparse (active fraction < 0.5) but
                          present, with ≥ 2 burst samples (≥ 3× the median
                          active volume).
      quiet             — tracked, but (nearly) no traffic in the window.
    """
    totals = [max(0.0, (rx or 0.0) + (tx or 0.0)) for _ts, rx, tx in samples]
    active = [v for v in totals if v > 0]
    active_fraction = (len(active) / len(totals)) if totals else 0.0
    if len(totals) < min_samples:
        return {"category": "insufficient-data",
                "evidence": "only %d samples tracked (need %d)"
                            % (len(totals), min_samples),
                "active_fraction": active_fraction,
                "median_interval_s": None, "spikes": 0}
    if not active:
        return {"category": "quiet",
                "evidence": "no traffic in the tracked window",
                "active_fraction": 0.0, "median_interval_s": None,
                "spikes": 0}

    # gaps between ACTIVE samples, in samples (× cadence = seconds)
    gaps = [b - a for a, b in zip([i for i, v in enumerate(totals) if v > 0],
                                  [i for i, v in enumerate(totals) if v > 0][1:])]
    median_gap = statistics.median(gaps) if gaps else None
    median_interval_s = (median_gap * cadence_s) if median_gap is not None else None
    mean_gap = statistics.fmean(gaps) if gaps else 0.0
    cv = (statistics.pstdev(gaps) / mean_gap) if mean_gap else 1.0
    median_volume = statistics.median(active)
    # In the sparse branch every active sample IS a burst — counting them
    # against a 3× median threshold zeroed the count on homogeneous bursts.
    spikes = len(active)

    tx_share = statistics.fmean(
        [(tx or 0.0) / (rx + tx) if (rx + tx) else 0.5
         for _ts, rx, tx in samples if (rx or tx)])

    if active_fraction >= 0.5 and cv < 0.35:
        category = "regular-intervals"
        evidence = ("active in %d of %d samples at a steady %.0f s cadence"
                    % (len(active), len(totals), median_interval_s or 0))
        if median_volume <= 4096.0 and tx_share >= 0.4:
            category = "telemetry-like"
            evidence += (" · steady small uploads (median %s/s) — "
                         "telemetry-like PATTERN, not proof"
                         % _human(median_volume))
        return {"category": category, "evidence": evidence,
                "active_fraction": active_fraction,
                "median_interval_s": median_interval_s, "spikes": spikes}
    if active_fraction < 0.5 and spikes >= 2:
        category = "irregular-spikes"
        evidence = ("sparse bursts: %d of %d samples active (%s/s median "
                    "volume)" % (len(active), len(totals),
                                 _human(median_volume)))
        return {"category": category, "evidence": evidence,
                "active_fraction": active_fraction,
                "median_interval_s": median_interval_s, "spikes": spikes}
    category = "irregular-spikes" if active_fraction < 0.5 else \
        "regular-intervals"
    return {"category": category,
            "evidence": "active in %d of %d samples, irregular cadence "
                        "(CV %.2f)" % (len(active), len(totals), cv),
            "active_fraction": active_fraction,
            "median_interval_s": median_interval_s, "spikes": spikes}


def _human(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f GB" % size


class NetWatch:
    """Marks + tracking rings for the Network page (persisted marks)."""

    def __init__(self, store_path=None, ring_max=RING_MAX):
        self.store_path = store_path or _default_store_path()
        self.ring_max = ring_max
        self.marks = {}        # process name -> "low" | "medium" | "high"
        self.rings = {}        # key -> deque[(ts, rx, tx, conns)]
        self.names = {}        # key -> display name (last seen)
        self._load()

    # -- persistence (marks only; rings are session state) ----------------

    def _load(self):
        try:
            with open(self.store_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and isinstance(data.get("marks"), dict):
                self.marks = {k: v for k, v in data["marks"].items()
                              if v in ("low", "medium", "high")}
        except (OSError, ValueError):
            pass

    def save(self):
        directory = os.path.dirname(self.store_path)
        os.makedirs(directory, exist_ok=True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"marks": self.marks}, fh, indent=2)
        os.replace(tmp, self.store_path)

    # -- marks -------------------------------------------------------------

    def mark(self, name, level):
        """Set/clear an importance mark; ``level`` None clears. Persists."""
        if level is None:
            self.marks.pop(name, None)
        else:
            if level not in ("low", "medium", "high"):
                raise ValueError("importance must be low/medium/high")
            self.marks[name] = level
        self.save()

    def mark_for(self, name):
        return self.marks.get(name)

    # -- tracking -----------------------------------------------------------

    def track(self, key, name):
        """Start tracking a process key; returns True when newly tracked."""
        if key in self.rings:
            return False
        self.rings[key] = deque(maxlen=self.ring_max)
        self.names[key] = name
        return True

    def untrack(self, key):
        return self.rings.pop(key, None) is not None

    def is_tracked(self, key):
        return key in self.rings

    def tracked(self):
        return list(self.rings)

    def sample(self, key, ts, rx, tx, conns):
        """Append one snapshot sample to a tracked ring (bounded deque)."""
        ring = self.rings.get(key)
        if ring is not None:
            ring.append((ts, rx or 0.0, tx or 0.0, conns or 0))

    def classify(self, key, *, cadence_s=2.0):
        """Pattern verdict for a tracked key (see classify_activity)."""
        ring = self.rings.get(key)
        samples = [(ts, rx, tx) for ts, rx, tx, _c in (ring or [])]
        return classify_activity(samples, cadence_s=cadence_s)
