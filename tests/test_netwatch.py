"""Net watch (r133): importance marks (persistence), tracking rings, and
the pattern classifier (regular-intervals / telemetry-like /
irregular-spikes / quiet / insufficient-data). Pure + headless."""

import json

import pytest

from ui.compat import Gtk  # noqa: F401  (ui-side import first)
from modules import manager_netwatch as nw


def _ring(activity, *, cadence=2.0, start=1000.0):
    """Build [(ts, rx, tx)] from a 0/1 activity pattern; active samples
    carry `vol` bytes/s total (split half/half)."""
    out = []
    ts = start
    for flag in activity:
        vol = 6000.0 if flag == 1 else (flag if isinstance(flag, float) else 0.0)
        if isinstance(flag, float) and flag > 1:
            vol = flag
        rx = vol / 2 if vol else 0.0
        tx = vol / 2 if vol else 0.0
        out.append((ts, rx, tx))
        ts += cadence
    return out


REGULAR = [1] * 20                       # active every sample
SPARSE_SPIKES = [0, 0, 0, 2.0, 0, 0, 0, 0, 3.0, 0, 0, 0, 0, 5.0, 0, 0, 0,
                 4.0, 0, 0]


def test_marks_persist_and_validate(tmp_path):
    store = str(tmp_path / "netwatch.json")
    watch = nw.NetWatch(store_path=store)
    watch.mark("steam", "high")
    watch.mark("nemo", "low")
    watch.mark("bad", "extreme") if False else None
    with pytest.raises(ValueError):
        watch.mark("x", "extreme")
    reloaded = nw.NetWatch(store_path=store)
    assert reloaded.mark_for("steam") == "high"
    assert reloaded.mark_for("nemo") == "low"
    assert reloaded.mark_for("unknown") is None


def test_mark_clear(tmp_path):
    store = str(tmp_path / "netwatch.json")
    watch = nw.NetWatch(store_path=store)
    watch.mark("steam", "medium")
    watch.mark("steam", None)
    assert nw.NetWatch(store_path=store).mark_for("steam") is None


def test_track_sample_classify_regular():
    watch = nw.NetWatch(store_path=None)
    key = ("steam", 1)
    assert watch.track(key, "steam") is True
    assert watch.track(key, "steam") is False          # already tracked
    samples = _ring(REGULAR)
    for ts, rx, tx in samples:
        watch.sample(key, ts, rx, tx, 2)
    verdict = watch.classify(key, cadence_s=2.0)
    assert verdict["category"] == "regular-intervals"
    assert "steady" in verdict["evidence"]
    assert watch.untrack(key) is True
    assert watch.is_tracked(key) is False


def test_classify_telemetry_like_small_regular_uploads():
    # steady cadence, LOW volume, tx-leaning — the telemetry-like PATTERN
    samples = [(1000.0 + i * 2.0, 100.0, 2400.0) for i in range(20)]
    verdict = nw.classify_activity(samples, cadence_s=2.0)
    assert verdict["category"] == "telemetry-like"
    assert "not proof" in verdict["evidence"]


def test_classify_irregular_spikes():
    samples = _ring(SPARSE_SPIKES)
    verdict = nw.classify_activity(samples, cadence_s=2.0)
    assert verdict["category"] == "irregular-spikes"
    assert verdict["spikes"] >= 2


def test_classify_quiet_and_insufficient():
    watch = nw.NetWatch(store_path=None)
    key = ("quiet", 1)
    watch.track(key, "quiet")
    quiet = [(1000.0 + i * 2.0, 0.0, 0.0) for i in range(20)]
    for ts, rx, tx in quiet:
        watch.sample(key, ts, rx, tx, 0)
    assert watch.classify(key)["category"] == "quiet"

    verdict = nw.classify_activity(_ring(REGULAR)[:5])
    assert verdict["category"] == "insufficient-data"
    assert "12" in verdict["evidence"]


def test_ring_is_bounded():
    watch = nw.NetWatch(store_path=None, ring_max=5)
    key = ("k", 1)
    watch.track(key, "k")
    for i in range(20):
        watch.sample(key, 1000.0 + i, 1.0, 0.0, 0)
    assert len(watch.rings[key]) == 5
