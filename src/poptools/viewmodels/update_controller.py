from __future__ import annotations

import logging
import os
import sys
import time
import urllib.error
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Property, QCoreApplication, QObject, QThread, QTimer, Signal, Slot

from poptools import __version__
from poptools.infrastructure.app_updater import (
    GitHubReleaseClient,
    UpdateInstaller,
    UpdateRelease,
    file_sha256,
    is_newer_version,
    validate_pending_update,
)
from poptools.infrastructure.config_store import ConfigStore

logger = logging.getLogger(__name__)


class UpdateCheckThread(QThread):
    completed = Signal(object, str)

    def __init__(
        self,
        client: GitHubReleaseClient,
        include_prereleases: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.include_prereleases = include_prereleases

    def run(self) -> None:
        try:
            self.completed.emit(
                self.client.latest_release(self.include_prereleases), ""
            )
        except urllib.error.HTTPError as exc:
            self.completed.emit(None, f"检查更新失败：GitHub 返回 HTTP {exc.code}")
        except urllib.error.URLError as exc:
            self.completed.emit(None, f"检查更新失败：{exc.reason}")
        except Exception as exc:
            self.completed.emit(None, f"检查更新失败：{exc}")


class UpdateDownloadThread(QThread):
    progressChanged = Signal(int, int)
    completed = Signal(bool, str, str, str)

    def __init__(
        self,
        client: GitHubReleaseClient,
        release: UpdateRelease,
        destination: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.release = release
        self.destination = destination

    def run(self) -> None:
        try:
            result = self.client.download(
                self.release,
                self.destination,
                self._report_progress,
                self.isInterruptionRequested,
            )
            checksum = file_sha256(result)
        except InterruptedError:
            self.completed.emit(False, "更新下载已取消", "", "")
        except urllib.error.URLError as exc:
            self.completed.emit(False, f"更新下载失败：{exc.reason}", "", "")
        except Exception as exc:
            self.completed.emit(False, f"更新下载失败：{exc}", "", "")
        else:
            self.completed.emit(
                True,
                "更新下载完成，可以安装并重启。",
                str(result),
                checksum,
            )

    def _report_progress(self, received: int, total: int) -> None:
        self.progressChanged.emit(received, total)


class UpdateController(QObject):
    stateChanged = Signal()
    updateAvailable = Signal()

    def __init__(
        self,
        config_store: ConfigStore,
        client: GitHubReleaseClient | None = None,
        current_version: str = __version__,
        auto_check_enabled: bool | None = None,
        clock: Callable[[], float] = time.time,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_store = config_store
        self.client = client or GitHubReleaseClient()
        self._current_version = current_version
        self._clock = clock
        self._startup_check_started = False
        self._auto_check_enabled = (
            getattr(sys, "frozen", False)
            or os.environ.get("POPTOOLS_ENABLE_UPDATE_CHECK") == "1"
            if auto_check_enabled is None
            else auto_check_enabled
        )
        self._state = "idle"
        self._status = ""
        self._release: UpdateRelease | None = None
        self._progress = 0
        self._received_bytes = 0
        self._total_bytes = 0
        self._downloaded_path = ""
        self._downloaded_sha256 = ""
        self._pending_version = ""
        self._check_thread: UpdateCheckThread | None = None
        self._download_thread: UpdateDownloadThread | None = None
        self._check_is_manual = False
        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(60_000)
        self._schedule_timer.timeout.connect(self.checkForUpdatesAutomatically)
        self._schedule_timer.start()
        self._restore_pending_update()

    @Property(str, notify=stateChanged)
    def updateCheckFrequency(self) -> str:
        return self.config_store.update_check_frequency()

    @Slot(str)
    def setUpdateCheckFrequency(self, value: str) -> None:
        if value not in {"daily", "weekly", "never", "startup"}:
            return
        self.config_store.set_update_check_frequency(value)
        self.stateChanged.emit()

    @Property(str, constant=True)
    def currentVersion(self) -> str:
        return self._current_version

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    @Property(str, notify=stateChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=stateChanged)
    def availableVersion(self) -> str:
        return self._release.version if self._release else self._pending_version

    @Property(str, notify=stateChanged)
    def releaseName(self) -> str:
        return self._release.name if self._release else ""

    @Property(str, notify=stateChanged)
    def releaseNotes(self) -> str:
        return self._release.notes if self._release else ""

    @Property(str, notify=stateChanged)
    def releasePageUrl(self) -> str:
        return self._release.page_url if self._release else ""

    @Property(int, notify=stateChanged)
    def downloadProgress(self) -> int:
        return self._progress

    @Property(str, notify=stateChanged)
    def downloadedSize(self) -> str:
        return self._format_size(self._received_bytes)

    @Property(str, notify=stateChanged)
    def totalSize(self) -> str:
        return self._format_size(self._total_bytes)

    @Property(bool, notify=stateChanged)
    def prereleaseUpdatesEnabled(self) -> bool:
        return bool(self.config_store.prerelease_updates_enabled())

    @Property(bool, notify=stateChanged)
    def canChangeUpdateChannel(self) -> bool:
        return self._check_thread is None and self._state not in {
            "checking",
            "downloading",
            "downloaded",
            "installing",
        }

    @Slot(result=bool)
    def checkForUpdates(self) -> bool:
        return self._start_check(manual=True)

    @Slot(result=bool)
    def checkForUpdatesAutomatically(self) -> bool:
        frequency = self.config_store.update_check_frequency()
        if not self._auto_check_enabled or frequency == "never":
            return False
        now = self._clock()
        period_start = self._auto_check_period_start(now, frequency)
        if frequency == "startup":
            if self._startup_check_started:
                return False
        elif self.config_store.last_auto_update_check_at() >= period_start:
            return False
        started = self._start_check(manual=False)
        if started:
            self._startup_check_started = True
            self.config_store.set_last_auto_update_check_at(now)
        return started

    @Slot(bool, result=bool)
    def setPrereleaseUpdatesEnabled(self, enabled: bool) -> bool:
        if not self.canChangeUpdateChannel:
            return False
        enabled = bool(enabled)
        if enabled == self.config_store.prerelease_updates_enabled():
            return True
        self.config_store.set_prerelease_updates_enabled(enabled)
        self.config_store.set_last_update_check_at(0.0)
        self.config_store.set_last_auto_update_check_at(0.0)
        self._release = None
        channel = "测试版本" if enabled else "正式版本"
        self._set_state("idle", f"已切换为接收{channel}，可立即检查更新。")
        return True

    def _start_check(self, manual: bool) -> bool:
        if self._check_thread is not None or self._download_thread is not None:
            return False
        if self._state in {"downloaded", "installing"}:
            return False
        self._check_is_manual = manual
        self._release = None
        self._set_state("checking", "正在检查更新…")
        thread = UpdateCheckThread(
            self.client,
            self.config_store.prerelease_updates_enabled(),
            self,
        )
        self._check_thread = thread
        thread.completed.connect(self._on_check_completed)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    @Slot(result=bool)
    def downloadUpdate(self) -> bool:
        release = self._release
        if release is None or self._download_thread is not None:
            return False
        safe_version = re_safe_filename(release.version)
        suffix = Path(release.asset_name).suffix or ".bin"
        destination = self.config_store.paths.updates_dir / f"PopTools-{safe_version}{suffix}"
        self._progress = 0
        self._received_bytes = 0
        self._total_bytes = release.asset_size
        self._downloaded_path = ""
        self._downloaded_sha256 = ""
        self._pending_version = ""
        self._set_state("downloading", "正在下载更新…")
        thread = UpdateDownloadThread(self.client, release, destination, self)
        self._download_thread = thread
        thread.progressChanged.connect(self._on_download_progress)
        thread.completed.connect(self._on_download_completed)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    @Slot(result=bool)
    def cancelDownload(self) -> bool:
        thread = self._download_thread
        if thread is None:
            return False
        thread.requestInterruption()
        self._status = "正在取消下载…"
        self.stateChanged.emit()
        return True

    @Slot()
    def skipVersion(self) -> None:
        if self._release is not None:
            self.config_store.set_skipped_update_version(self._release.version)
        self._set_state("idle", "")

    @Slot(result=bool)
    def installAndRestart(self) -> bool:
        if self._state != "downloaded" or not self._downloaded_path:
            return False
        if not self._persist_downloaded_update():
            return False
        try:
            launched = UpdateInstaller.launch(Path(self._downloaded_path))
        except OSError as exc:
            self._set_state("error", f"无法启动更新程序：{exc}")
            return False
        if not launched:
            self._set_state("error", "无法启动更新程序，请手动下载最新版本。")
            return False
        self._set_state("installing", "正在退出并安装更新…")
        QCoreApplication.quit()
        return True

    @Slot(result=bool)
    def installLater(self) -> bool:
        if self._state != "downloaded" or not self._downloaded_path:
            return False
        if not self._persist_downloaded_update():
            return False
        self._status = "更新将在下次启动时自动安装。"
        self.stateChanged.emit()
        return True

    @Slot(result=bool)
    def retryUpdate(self) -> bool:
        if self._downloaded_path:
            self._set_state("downloaded", "更新已准备好，可以重新尝试安装。")
            return self.installAndRestart()
        return self.downloadUpdate()

    @Slot()
    def shutdown(self) -> None:
        self._schedule_timer.stop()
        for thread in (self._check_thread, self._download_thread):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.wait(3_000)

    @Slot(object, str)
    def _on_check_completed(self, release: object, error: str) -> None:
        self._check_thread = None
        manual = self._check_is_manual
        self._check_is_manual = False
        if error:
            logger.warning("%s", error)
            self._set_state("error" if manual else "idle", error if manual else "")
            return
        self.config_store.set_last_update_check_at(self._clock())
        if not isinstance(release, UpdateRelease):
            self._set_state("idle", "当前已是最新版本" if manual else "")
            return
        if not is_newer_version(release.version, self._current_version):
            self._set_state("idle", "当前已是最新版本" if manual else "")
            return
        if not manual and release.version == self.config_store.skipped_update_version():
            self._set_state("idle", "")
            return
        self._release = release
        self._set_state("available", f"发现新版本 {release.version}")
        self.updateAvailable.emit()

    @staticmethod
    def _auto_check_period_start(timestamp: float, frequency: str) -> float:
        local_now = datetime.fromtimestamp(timestamp)
        if frequency == "weekly":
            local_now -= timedelta(days=local_now.weekday())
        return local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    @Slot(int, int)
    def _on_download_progress(self, received: int, total: int) -> None:
        self._received_bytes = received
        self._total_bytes = total or self._total_bytes
        self._progress = (
            min(100, int(received * 100 / self._total_bytes))
            if self._total_bytes
            else 0
        )
        self._status = (
            f"正在下载… {self._progress}%"
            if self._total_bytes
            else f"正在下载… {self._format_size(received)}"
        )
        self.stateChanged.emit()

    @Slot(bool, str, str, str)
    def _on_download_completed(
        self,
        success: bool,
        message: str,
        path: str,
        checksum: str = "",
    ) -> None:
        self._download_thread = None
        if success:
            self._progress = 100
            self._downloaded_path = path
            self._downloaded_sha256 = checksum
            self._pending_version = self._release.version if self._release else ""
            self._set_state("downloaded", message)
        elif message == "更新下载已取消":
            self._set_state("available", message)
        else:
            self._set_state("error", message)

    def _set_state(self, state: str, status: str) -> None:
        self._state = state
        self._status = status
        self.stateChanged.emit()

    def _persist_downloaded_update(self) -> bool:
        path = Path(self._downloaded_path)
        version = self._release.version if self._release else self._pending_version
        try:
            size = path.stat().st_size
            checksum = self._downloaded_sha256 or file_sha256(path)
            self.config_store.set_pending_update(
                version,
                path.name,
                size,
                checksum,
            )
        except (OSError, ValueError) as exc:
            self._set_state("error", f"无法保存待安装更新：{exc}")
            return False
        self._downloaded_sha256 = checksum
        self._pending_version = version
        return True

    def _restore_pending_update(self) -> None:
        result, pending = validate_pending_update(
            self.config_store,
            self._current_version,
        )
        if result != "ready" or pending is None:
            return
        self._downloaded_path = str(pending.path)
        self._downloaded_sha256 = pending.sha256
        self._pending_version = pending.version
        self._progress = 100
        self._received_bytes = pending.size
        self._total_bytes = pending.size
        self._state = "downloaded"
        self._status = "更新已下载，将在下次启动时自动安装。"

    @staticmethod
    def _format_size(value: int) -> str:
        if value <= 0:
            return ""
        if value >= 1024 * 1024:
            return f"{value / (1024 * 1024):.1f} MB"
        if value >= 1024:
            return f"{value / 1024:.1f} KB"
        return f"{value} B"


def re_safe_filename(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in ".-_" else "_"
        for character in value
    )
