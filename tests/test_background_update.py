from threading import Event

import pytest
from PySide6.QtCore import QTimer

from poptools.infrastructure.app_updater import UpdateInstaller, UpdateRelease, apply_pending_update
from poptools.infrastructure.config_store import ConfigStore
from poptools.paths import AppPaths
from poptools.viewmodels import update_controller
from poptools.viewmodels.update_controller import UpdateController


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
@pytest.mark.parametrize("background", [False, True])
def test_download_keeps_event_loop_available_and_requests_background_result(
    qapp, qtbot, tmp_path, outcome, background,
):
    finish = Event()

    class Client:
        def download(self, release, destination, progress, cancelled):
            progress(5, 10)
            if not finish.wait(5):
                raise TimeoutError("test download timed out")
            if cancelled():
                raise InterruptedError
            if outcome == "failure":
                raise OSError("connection lost")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"installer")
            return destination

    store = ConfigStore(AppPaths(tmp_path))
    controller = UpdateController(
        store, client=Client(), current_version="1.0.0", auto_check_enabled=False,
    )
    controller._release = UpdateRelease(
        "2.0.0", "v2.0.0", "Version 2", "notes", "", "", "setup.exe", 10,
    )
    notifications = []
    controller.backgroundDownloadFinished.connect(lambda: notifications.append(controller.state))
    try:
        assert not controller.downloadInBackground()
        assert controller.downloadUpdate()
        qtbot.waitUntil(lambda: controller.downloadProgress == 50)
        if background:
            assert controller.downloadInBackground()
        assert not controller.downloadUpdate()
        assert not controller.checkForUpdates()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
        assert controller.state == "downloading"
        assert not notifications
        if outcome == "cancelled":
            assert controller.cancelDownload()
        finish.set()
        qtbot.waitUntil(lambda: controller.state != "downloading")
        expected = {"success": "downloaded", "failure": "error", "cancelled": "available"}[outcome]
        assert controller.state == expected
        assert notifications == ([expected] if background and outcome != "cancelled" else [])
        assert not controller.downloadInBackground()
        assert store.pending_update() is None
        if outcome == "success":
            assert controller.installLater()
            launched = []
            assert apply_pending_update(
                ConfigStore(AppPaths(tmp_path)), "1.0.0",
                launcher=lambda path: launched.append(path) or True,
            ) == "launched"
            assert launched == [tmp_path / "updates" / "PopTools-2.0.0.exe"]
    finally:
        finish.set()
        controller.shutdown()


def test_completed_background_download_restarts_only_after_user_choice(
    qapp, tmp_path, monkeypatch,
):
    store = ConfigStore(AppPaths(tmp_path))
    store.paths.updates_dir.mkdir(parents=True, exist_ok=True)
    installer = store.paths.updates_dir / "setup.exe"
    installer.write_bytes(b"installer")
    controller = UpdateController(store, current_version="1.0.0", auto_check_enabled=False)
    controller._release = UpdateRelease(
        "2.0.0", "v2.0.0", "Version 2", "notes", "", "", "setup.exe", 9,
    )
    controller._background_download = True
    actions = []
    monkeypatch.setattr(UpdateInstaller, "launch", lambda path: actions.append(path) or True)
    monkeypatch.setattr(update_controller.QCoreApplication, "quit", lambda: actions.append("quit"))
    try:
        controller._on_download_completed(True, "下载完成", str(installer))
        assert controller.state == "downloaded"
        assert not actions
        assert controller.installAndRestart()
        assert actions == [installer, "quit"]
        assert controller.state == "installing"
        assert store.pending_update()["version"] == "2.0.0"
    finally:
        controller.shutdown()
