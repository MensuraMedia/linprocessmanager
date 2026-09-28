"""Tests for src/modules/manager_netattr.py (r053 socket-owner attribution).

The honest model has two testable layers:

1. ``attribute`` — the pure step: exact own-process (one socket -> full total),
   Yama restriction -> ``None``, proportional-by-open-duration split, equal
   split among a socket's holders, and the honest-zero / unknown edges.
2. ``NetAttributor.poll`` — the stateful pass over injected fake ``/proc`` trees
   (there is no way to build symlink fd fixtures without a live kernel, so the
   seam is dependency injection, matching the sampler's reader pattern): exact
   attribution, Yama -> ``None``, the incremental fd-rescan cache, and the
   socket-family read-back for the preview.
"""

import pytest

import manager_netattr as na


# --- open_weight ------------------------------------------------------------

def test_open_weight_full_partial_and_new():
    assert na.open_weight(100.0, 50.0, None) == 1.0          # no interval
    assert na.open_weight(100.0, 90.0, 2.0) == pytest.approx(1.0)   # >= interval
    assert na.open_weight(100.0, 99.0, 2.0) == pytest.approx(0.5)   # half
    assert na.open_weight(100.0, 100.0, 2.0) == 0.0          # brand new


# --- pure attribution -------------------------------------------------------

def test_attribute_exact_own_process_gets_full_total():
    res = na.attribute({45678: {100}}, {45678}, {45678: 1.0},
                       1000.0, 200.0, {100: 111}, set())
    assert res[(100, 111)] == (pytest.approx(1000.0), pytest.approx(200.0))


def test_attribute_yama_restricted_is_none():
    res = na.attribute({}, set(), {}, 1000.0, 200.0, {100: 111}, {100})
    assert res[(100, 111)] is None


def test_attribute_proportional_by_open_duration():
    # pid 100's socket was open twice as long as pid 200's -> 2:1 split.
    res = na.attribute({1: {100}, 2: {200}}, {1, 2}, {1: 2.0, 2: 1.0},
                       300.0, 30.0, {100: 11, 200: 22}, set())
    assert res[(100, 11)][0] == pytest.approx(200.0)
    assert res[(200, 22)][0] == pytest.approx(100.0)
    assert res[(100, 11)][1] == pytest.approx(20.0)
    assert res[(200, 22)][1] == pytest.approx(10.0)


def test_attribute_shared_socket_splits_equally_among_holders():
    res = na.attribute({1: {100, 200}}, {1}, {1: 1.0},
                       1000.0, 0.0, {100: 11, 200: 22}, set())
    assert res[(100, 11)][0] == pytest.approx(500.0)
    assert res[(200, 22)][0] == pytest.approx(500.0)


def test_attribute_no_total_leaves_pids_unknown():
    # first sample / counter reset -> total None -> pids absent (record -> None).
    res = na.attribute({45678: {100}}, {45678}, {45678: 1.0},
                       None, None, {100: 11}, set())
    assert res == {}


def test_attribute_no_socket_is_honest_zero():
    res = na.attribute({}, set(), {}, 1000.0, 200.0, {100: 11}, set())
    assert res[(100, 11)] == (0.0, 0.0)


def test_attribute_all_new_sockets_fall_back_to_equal_split():
    # every weight 0 (brand new) -> equal split so the interval isn't dropped.
    res = na.attribute({1: {100}, 2: {200}}, {1, 2}, {1: 0.0, 2: 0.0},
                       200.0, 0.0, {100: 11, 200: 22}, set())
    assert res[(100, 11)][0] == pytest.approx(100.0)
    assert res[(200, 22)][0] == pytest.approx(100.0)


# --- NetAttributor.poll (injected fake /proc trees) -------------------------

def _make(fd_map, net, restricted=(), mtimes=None):
    restricted = set(restricted)

    def scan_fds(pid):
        if pid in restricted:
            raise PermissionError("Yama")
        return set(fd_map.get(pid, ()))

    return na.NetAttributor(
        scan_fds=scan_fds,
        read_net=lambda: dict(net),
        fd_mtime=lambda pid: (mtimes or {}).get(pid))


def test_poll_exact_own_process():
    attr = _make({100: {45678}}, {45678: "tcp"})
    res = attr.poll(now=100.0, interval=None, total_rx=1000.0, total_tx=200.0,
                    pid_start={100: 111})
    assert res[(100, 111)] == (pytest.approx(1000.0), pytest.approx(200.0))


def test_poll_yama_restricted_is_none():
    attr = _make({}, {45678: "tcp"}, restricted={100})
    res = attr.poll(now=1.0, interval=None, total_rx=1000.0, total_tx=1.0,
                    pid_start={100: 111})
    assert res[(100, 111)] is None


def test_poll_non_network_fd_is_ignored():
    # pid holds an fd inode that is NOT in /proc/net/* -> not an active socket.
    attr = _make({100: {99999}}, {45678: "tcp"})
    res = attr.poll(now=1.0, interval=None, total_rx=1000.0, total_tx=10.0,
                    pid_start={100: 111})
    assert res[(100, 111)] == (0.0, 0.0)


def test_poll_incremental_cache_skips_rescan_on_unchanged_mtime():
    calls = {"n": 0}

    def scan_fds(pid):
        calls["n"] += 1
        return {45678}

    attr = na.NetAttributor(scan_fds=scan_fds,
                            read_net=lambda: {45678: "tcp"},
                            fd_mtime=lambda pid: 12345.0)
    attr.poll(1.0, None, 100.0, 10.0, {100: 111})
    attr.poll(2.0, 1.0, 100.0, 10.0, {100: 111})
    assert calls["n"] == 1  # second poll reused the cached inode set


def test_poll_rescans_when_mtime_changes():
    calls = {"n": 0}
    mt = {"v": 1.0}

    def scan_fds(pid):
        calls["n"] += 1
        return {45678}

    attr = na.NetAttributor(scan_fds=scan_fds,
                            read_net=lambda: {45678: "tcp"},
                            fd_mtime=lambda pid: mt["v"])
    attr.poll(1.0, None, 100.0, 10.0, {100: 111})
    mt["v"] = 2.0
    attr.poll(2.0, 1.0, 100.0, 10.0, {100: 111})
    assert calls["n"] == 2


def test_families_for_reports_held_socket_families():
    attr = _make({100: {45678, 45679}}, {45678: "tcp", 45679: "udp"})
    attr.poll(1.0, None, 100.0, 10.0, {100: 111})
    assert attr.families_for([100]) == ["tcp", "udp"]
