from __future__ import annotations

import os
import signal


class FakeProcess:
    def __init__(self, pid, cmdline, children=None):
        self.pid = pid
        self.info = {"pid": pid, "cmdline": cmdline}
        self._children = children or []
        self.signals_received = []
        self.killed = False

    def children(self, recursive=False):
        return self._children

    def send_signal(self, sig):
        self.signals_received.append(sig)

    def kill(self):
        self.killed = True


def _patch_process_iter(monkeypatch, procs):
    import backend.__main__ as main_module

    monkeypatch.setattr(main_module.psutil, "process_iter", lambda fields: iter(procs))


def _patch_wait_procs_all_gone(monkeypatch):
    import backend.__main__ as main_module

    monkeypatch.setattr(main_module.psutil, "wait_procs", lambda procs, timeout=None: (list(procs), []))


def test_stop_never_signals_its_own_process(monkeypatch, capsys):
    """The `stop` invocation's own cmdline also contains "backend-api"; it must
    never match itself, or it would SIGTERM itself before reaching the real
    server process (the bug this test guards against)."""
    from backend.__main__ import _stop_backend

    own_pid = os.getpid()
    self_proc = FakeProcess(own_pid, ["/venv/bin/python", "/venv/bin/backend-api", "stop"])
    server_proc = FakeProcess(99999, ["/venv/bin/python", "/venv/bin/backend-api", "run"])

    _patch_process_iter(monkeypatch, [self_proc, server_proc])
    _patch_wait_procs_all_gone(monkeypatch)

    _stop_backend()

    assert self_proc.signals_received == []
    assert server_proc.signals_received == [signal.SIGTERM]

    out = capsys.readouterr().out
    assert "Stopped 1 backend-api process(es)" in out
    assert str(own_pid) not in out


def test_stop_reports_nothing_running_when_only_self_matches(monkeypatch, capsys):
    from backend.__main__ import _stop_backend

    self_proc = FakeProcess(os.getpid(), ["/venv/bin/backend-api", "stop"])
    _patch_process_iter(monkeypatch, [self_proc])
    _patch_wait_procs_all_gone(monkeypatch)

    _stop_backend()

    assert self_proc.signals_received == []
    assert "No running backend-api processes found" in capsys.readouterr().out


def test_stop_also_signals_debug_reload_child_process(monkeypatch, capsys):
    """A --debug run's reload supervisor spawns a worker subprocess that actually
    holds the listening socket; stopping must reach that child too."""
    from backend.__main__ import _stop_backend

    worker = FakeProcess(222, ["/venv/bin/python", "-c", "multiprocessing spawn"])
    supervisor = FakeProcess(111, ["/venv/bin/backend-api", "run", "--debug"], children=[worker])

    _patch_process_iter(monkeypatch, [supervisor])
    _patch_wait_procs_all_gone(monkeypatch)

    _stop_backend()

    assert supervisor.signals_received == [signal.SIGTERM]
    assert worker.signals_received == [signal.SIGTERM]
    assert "Stopped 2 backend-api process(es)" in capsys.readouterr().out


def test_stop_escalates_to_kill_when_process_ignores_sigterm(monkeypatch, capsys):
    from backend.__main__ import _stop_backend
    import backend.__main__ as main_module

    stubborn = FakeProcess(333, ["/venv/bin/backend-api", "run"])
    _patch_process_iter(monkeypatch, [stubborn])

    # First wait_procs call: nobody exited yet. Second call (after kill()): gone.
    calls = {"n": 0}

    def fake_wait_procs(procs, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ([], list(procs))
        return (list(procs), [])

    monkeypatch.setattr(main_module.psutil, "wait_procs", fake_wait_procs)

    _stop_backend()

    assert stubborn.killed is True
    out = capsys.readouterr().out
    assert "did not stop in time; killing it" in out


def test_matches_backend_api_ignores_unrelated_substring_paths():
    from backend.__main__ import _matches_backend_api

    assert _matches_backend_api(["/venv/bin/backend-api", "run"]) is True
    assert _matches_backend_api(["/venv/bin/python", "/venv/bin/backend-api", "stop"]) is True
    assert _matches_backend_api(["/some/other-backend-api-tool/run.sh"]) is False
    assert _matches_backend_api(None) is False
    assert _matches_backend_api([]) is False
