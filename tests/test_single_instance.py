import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from poptools.infrastructure import single_instance as module


@pytest.mark.parametrize("platform,pid,granted", [
    ("win32", 1234, True), ("win32", 0, False), ("linux", 1234, False),
])
def test_activation_grants_only_lock_owner_foreground_before_sending(
    tmp_path, monkeypatch, platform, pid, granted,
):
    instance = module.SingleInstanceLock(tmp_path / "app.lock")
    instance._lock = SimpleNamespace(getLockInfo=lambda: (pid, "host", "app"))
    events = []

    class AllowForeground:
        def __call__(self, target):
            events.append(("allow", target))
            return True

    class Socket:
        LocalSocketState = module.QLocalSocket.LocalSocketState

        def connectToServer(self, name):
            pass

        def waitForConnected(self, timeout):
            return True

        def write(self, data):
            events.append(("send", json.loads(data)))

        def waitForBytesWritten(self, timeout):
            return True

        def disconnectFromServer(self):
            pass

        def state(self):
            return self.LocalSocketState.UnconnectedState

    def load_api(*args, **kwargs):
        assert granted, "Must not grant foreground access without a Windows lock owner"
        return SimpleNamespace(AllowSetForegroundWindow=AllowForeground())

    monkeypatch.setattr(module, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(module.ctypes, "WinDLL", load_api, raising=False)
    monkeypatch.setattr(module, "QLocalSocket", Socket)
    payload = {"action": "open_terminal", "cwd": "C:/项目/目录"}
    assert instance.activate_running_instance(payload)
    assert events == ([("allow", pid)] if granted else []) + [("send", payload)]


def test_second_launch_delivers_terminal_request_to_existing_instance(tmp_path, qtbot):
    path = tmp_path / "app.lock"
    owner = module.SingleInstanceLock(path)
    launcher = module.SingleInstanceLock(path)
    received = []
    try:
        assert owner.try_acquire()
        assert owner.start_activation_server()
        owner.set_activation_handler(received.append)
        assert not launcher.try_acquire()
        payload = {"action": "open_terminal", "cwd": str(tmp_path)}
        script = """
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from poptools.infrastructure.single_instance import SingleInstanceLock
instance = SingleInstanceLock(Path(sys.argv[2]))
sys.exit(0 if instance.activate_running_instance(json.loads(sys.argv[3])) else 1)
"""
        with subprocess.Popen(
            [sys.executable, "-c", script, str(Path(module.__file__).parents[2]),
             str(path), json.dumps(payload)],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ) as process:
            qtbot.waitUntil(lambda: process.poll() is not None, timeout=10000)
            assert process.returncode == 0
        qtbot.waitUntil(lambda: bool(received))
        assert received == [payload]
    finally:
        launcher.release()
        owner.release()
