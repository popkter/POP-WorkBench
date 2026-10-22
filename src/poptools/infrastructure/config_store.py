from __future__ import annotations

import json
import math
import re
import shutil
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from poptools.infrastructure.json_file_storage import JsonFileStorage
from poptools.paths import AppPaths

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "app": {
        "theme": "system",
        "language": "zh-CN",
        "last_section": "custom",
        "console_expanded": True,
        "terminal_enabled": False,
        "floating_launcher_enabled": True,
        "floating_launcher_position": {"screen": "", "vertical_ratio": 0.5},
        "user_guide_seen": False,
        "skipped_update_version": "",
        "prerelease_updates_enabled": False,
        "last_update_check_at": 0.0,
        "last_auto_update_check_at": 0.0,
        "pending_update": None,
    },
    "execution": {
        "max_parallel": 3,
        "default_timeout_seconds": 300,
        "confirm_untrusted_commands": True,
    },
    "android": {"selected_device": "", "adb_source": "bundled"},
    "bash": {"provider": "auto", "custom_executable": None},
    "python": {"provider": "managed", "custom_executable": None},
    "powershell": {"provider": "managed", "custom_executable": None},
    "custom_tools": {
        "sort_mode": "added_time",
        "order": [],
        "added_at": {},
        "usage_count": {},
        "recent_tools": [],
    },
}

TOOL_SORT_MODES = ("added_time", "name", "usage", "custom")
THEME_MODES = ("system", "light", "dark", "decade")
THEME_STYLE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
LOCAL_SCRIPT_ENTRIES = ("tools", "scripts")


class ConfigStore:
    """JSON adapter for small application settings only.

    Tool persistence is intentionally separated into ToolRepository so it can
    migrate to SQLite without changing this settings format.
    """

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.ensure()
        self.files = JsonFileStorage(paths.backups_dir)
        self._snapshot: dict[str, Any] | None = None
        self._signature: tuple[int, int, int] | None = None

    def _file_signature(self) -> tuple[int, int, int] | None:
        try:
            stat = self.paths.config_file.stat()
            return stat.st_mtime_ns, stat.st_size, stat.st_ino
        except FileNotFoundError:
            return None

    def load_config(self) -> dict[str, Any]:
        signature = self._file_signature()
        if self._snapshot is not None and signature == self._signature:
            return deepcopy(self._snapshot)
        if not self.paths.config_file.exists():
            self.save_config(DEFAULT_CONFIG)
            return self._copy_default()
        try:
            config = cast(
                dict[str, Any],
                json.loads(self.paths.config_file.read_text(encoding="utf-8")),
            )
            app = config.get("app")
            if isinstance(app, dict):
                changed = False
                for key in (
                    "window_width",
                    "window_height",
                    "window_centered",
                    "middle_panel_color",
                ):
                    if key in app:
                        app.pop(key)
                        changed = True
                if changed:
                    self.save_config(config)
            self._snapshot = deepcopy(config)
            self._signature = signature
            return config
        except (OSError, json.JSONDecodeError):
            self.files.backup(self.paths.config_file, suffix="corrupt")
            self.save_config(DEFAULT_CONFIG)
            return self._copy_default()

    def save_config(self, value: dict[str, Any]) -> None:
        self.files.write(self.paths.config_file, value)
        self._snapshot = deepcopy(value)
        self._signature = self._file_signature()

    def max_parallel(self) -> int:
        config = self.load_config()
        execution = config.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            config["execution"] = execution
        value = execution.get("max_parallel", 3)
        if not isinstance(value, int) or isinstance(value, bool):
            value = 3
        value = max(2, min(value, 64))
        if execution.get("max_parallel") != value:
            execution["max_parallel"] = value
            self.save_config(config)
        return value

    def android_selected_device(self) -> str:
        android = self.load_config().get("android", {})
        value = android.get("selected_device", android.get("preferred_device", ""))
        return value if isinstance(value, str) else ""

    def set_android_selected_device(self, serial: str) -> None:
        config = self.load_config()
        android = config.setdefault("android", {})
        android["selected_device"] = serial
        android.pop("tool_devices", None)
        android.pop("preferred_device", None)
        self.save_config(config)

    def android_tool_devices(self) -> dict[str, str]:
        config = self.load_config()
        value = config.get("android", {}).get("tool_devices", {})
        if not isinstance(value, dict):
            return {}
        return {key: serial for key, serial in value.items()
                if isinstance(key, str) and isinstance(serial, str) and serial}

    def set_android_tool_device(self, tool_id: str, serial: str) -> None:
        config = self.load_config()
        android = config.setdefault("android", {})
        selections = self.android_tool_devices()
        if serial:
            selections[tool_id] = serial
        else:
            selections.pop(tool_id, None)
        android["tool_devices"] = selections
        self.save_config(config)

    def user_guide_seen(self) -> bool:
        config = self.load_config()
        app = config.get("app")
        return bool(app.get("user_guide_seen", False)) if isinstance(app, dict) else False

    def set_user_guide_seen(self, seen: bool = True) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["user_guide_seen"] = bool(seen)
        self.save_config(config)

    def skipped_update_version(self) -> str:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            return ""
        value = app.get("skipped_update_version", "")
        return str(value).strip() if isinstance(value, str) else ""

    def set_skipped_update_version(self, version: str) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["skipped_update_version"] = version.strip()
        self.save_config(config)

    def pending_update(self) -> object | None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            return None
        value = app.get("pending_update")
        return dict(value) if isinstance(value, dict) else value

    def set_pending_update(
        self,
        version: str,
        file_name: str,
        size: int,
        sha256: str,
    ) -> None:
        if not version.strip():
            raise ValueError("待安装更新缺少版本号")
        if (
            not file_name
            or file_name in {".", ".."}
            or "/" in file_name
            or "\\" in file_name
        ):
            raise ValueError("待安装更新文件名无效")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("待安装更新文件大小无效")
        if re.fullmatch(r"[0-9a-fA-F]{64}", sha256.strip()) is None:
            raise ValueError("待安装更新校验值无效")
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["pending_update"] = {
            "version": version.strip(),
            "file_name": file_name,
            "size": int(size),
            "sha256": sha256.strip().lower(),
        }
        self.save_config(config)

    def clear_pending_update(self) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        if app.get("pending_update") is None:
            return
        app["pending_update"] = None
        self.save_config(config)

    def prerelease_updates_enabled(self) -> bool:
        config = self.load_config()
        app = config.get("app")
        return (
            bool(app.get("prerelease_updates_enabled", False))
            if isinstance(app, dict)
            else False
        )

    def set_prerelease_updates_enabled(self, enabled: bool) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["prerelease_updates_enabled"] = bool(enabled)
        self.save_config(config)

    def last_update_check_at(self) -> float:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            return 0.0
        value = app.get("last_update_check_at", 0.0)
        if not self._is_valid_timestamp(value):
            return 0.0
        return float(value)

    def last_auto_update_check_at(self) -> float:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app

        if "last_auto_update_check_at" not in app:
            legacy_value = app.get("last_update_check_at", 0.0)
            value = float(legacy_value) if self._is_valid_timestamp(legacy_value) else 0.0
            app["last_auto_update_check_at"] = value
            self.save_config(config)
            return value

        stored_value = app.get("last_auto_update_check_at")
        if not self._is_valid_timestamp(stored_value):
            app["last_auto_update_check_at"] = 0.0
            self.save_config(config)
            return 0.0
        return float(cast(int | float, stored_value))

    def update_check_frequency(self) -> str:
        app = self.load_config().get("app", {})
        value = app.get("update_check_frequency", "weekly") if isinstance(app, dict) else "weekly"
        return value if value in {"daily", "weekly", "never", "startup"} else "weekly"

    def set_update_check_frequency(self, value: str) -> None:
        if value not in {"daily", "weekly", "never", "startup"}:
            raise ValueError("Invalid update frequency")
        config = self.load_config()
        if not isinstance(config.get("app"), dict):
            config["app"] = {}
        config["app"]["update_check_frequency"] = value
        self.save_config(config)

    def set_last_update_check_at(self, value: float) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["last_update_check_at"] = max(0.0, float(value))
        self.save_config(config)

    def set_last_auto_update_check_at(self, value: float) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        timestamp = float(value)
        app["last_auto_update_check_at"] = (
            timestamp if self._is_valid_timestamp(timestamp) else 0.0
        )
        self.save_config(config)

    @staticmethod
    def _is_valid_timestamp(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        )

    def floating_launcher_enabled(self) -> bool:
        app = self.load_config().get("app", {})
        value = app.get("floating_launcher_enabled", True) if isinstance(app, dict) else True
        return value if isinstance(value, bool) else True

    def set_floating_launcher_enabled(self, enabled: bool) -> None:
        config = self.load_config()
        if not isinstance(config.get("app"), dict):
            config["app"] = {}
        config["app"]["floating_launcher_enabled"] = bool(enabled)
        self.save_config(config)

    def floating_launcher_position(self) -> tuple[str, float]:
        app = self.load_config().get("app", {})
        position = app.get("floating_launcher_position", {}) if isinstance(app, dict) else {}
        if not isinstance(position, dict):
            return "", 0.5
        screen = position.get("screen", "")
        ratio = position.get("vertical_ratio", 0.5)
        if not self._is_valid_timestamp(ratio):
            ratio = 0.5
        return screen if isinstance(screen, str) else "", min(1.0, float(ratio))

    def set_floating_launcher_position(self, screen: str, vertical_ratio: float) -> None:
        if not self._is_valid_timestamp(vertical_ratio) or vertical_ratio > 1:
            raise ValueError("悬浮入口位置无效")
        config = self.load_config()
        if not isinstance(config.get("app"), dict):
            config["app"] = {}
        config["app"]["floating_launcher_position"] = {
            "screen": screen, "vertical_ratio": vertical_ratio,
        }
        self.save_config(config)

    def terminal_enabled(self) -> bool:
        config = self.load_config()
        app = config.get("app")
        return bool(app.get("terminal_enabled", False)) if isinstance(app, dict) else False

    def set_terminal_enabled(self, enabled: bool) -> None:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["terminal_enabled"] = bool(enabled)
        self.save_config(config)

    def custom_script_concurrency(self) -> int:
        config = self.load_config()
        execution = config.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            config["execution"] = execution
        value = execution.get("custom_script_concurrency")
        if not isinstance(value, int) or isinstance(value, bool):
            legacy_total = execution.get("max_parallel", 3)
            if not isinstance(legacy_total, int) or isinstance(legacy_total, bool):
                legacy_total = 3
            value = legacy_total - 1
        value = max(1, min(value, 5))
        if execution.get("custom_script_concurrency") != value:
            execution["custom_script_concurrency"] = value
            self.save_config(config)
        return value

    def set_custom_script_concurrency(self, value: int) -> None:
        if not 1 <= value <= 5:
            raise ValueError("客制脚本同时运行数需为 1–5")
        config = self.load_config()
        execution = config.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            config["execution"] = execution
        execution["custom_script_concurrency"] = value
        execution["max_parallel"] = value + 1
        self.save_config(config)

    def theme_mode(self) -> str:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        value = app.get("theme", "system")
        if value not in THEME_MODES:
            value = "system"
        if app.get("theme") != value:
            app["theme"] = value
            self.save_config(config)
        return str(value)

    def set_theme_mode(self, mode: str) -> None:
        if mode not in THEME_MODES:
            raise ValueError("未知的界面主题")
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["theme"] = mode
        self.save_config(config)

    def theme_style(self) -> str:
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        value = app.get("theme_style", "material3")
        if not isinstance(value, str) or THEME_STYLE_PATTERN.fullmatch(value) is None:
            value = "material3"
        if app.get("theme_style") != value:
            app["theme_style"] = value
            self.save_config(config)
        return str(value)

    def set_theme_style(self, style: str) -> None:
        if THEME_STYLE_PATTERN.fullmatch(style) is None:
            raise ValueError("未知的主题风格")
        config = self.load_config()
        app = config.get("app")
        if not isinstance(app, dict):
            app = {}
            config["app"] = app
        app["theme_style"] = style
        self.save_config(config)

    def tool_sort_mode(self) -> str:
        config, settings = self._custom_tool_settings()
        value = settings.get("sort_mode", "added_time")
        if value not in TOOL_SORT_MODES:
            value = "added_time"
        if settings.get("sort_mode") != value:
            settings["sort_mode"] = value
            self.save_config(config)
        return str(value)

    def set_tool_sort_mode(self, mode: str) -> None:
        if mode not in TOOL_SORT_MODES:
            raise ValueError("未知的脚本排序方式")
        config, settings = self._custom_tool_settings()
        settings["sort_mode"] = mode
        self.save_config(config)

    def tool_order(self) -> list[str]:
        config, settings = self._custom_tool_settings()
        raw = settings.get("order", [])
        value = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
        value = list(dict.fromkeys(value))
        if raw != value:
            settings["order"] = value
            self.save_config(config)
        return value

    def set_tool_order(self, tool_ids: list[str]) -> None:
        config, settings = self._custom_tool_settings()
        settings["order"] = list(dict.fromkeys(tool_ids))
        self.save_config(config)

    def tool_added_times(self, tool_ids: list[str]) -> dict[str, float]:
        config, settings = self._custom_tool_settings()
        raw = settings.get("added_at")
        values = dict(raw) if isinstance(raw, dict) else {}
        changed = not isinstance(raw, dict)
        now = time.time()
        for offset, tool_id in enumerate(tool_ids):
            value = values.get(tool_id)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                values[tool_id] = self._tool_file_timestamp(tool_id, now + offset * 0.000001)
                changed = True
        if changed:
            settings["added_at"] = values
            self.save_config(config)
        return {tool_id: float(values[tool_id]) for tool_id in tool_ids}

    def tool_usage_counts(self) -> dict[str, int]:
        config, settings = self._custom_tool_settings()
        raw = settings.get("usage_count")
        source = raw if isinstance(raw, dict) else {}
        values = {
            str(tool_id): count
            for tool_id, count in source.items()
            if isinstance(tool_id, str)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        }
        if raw != values:
            settings["usage_count"] = values
            self.save_config(config)
        return values

    def increment_tool_usage(self, tool_id: str) -> int:
        config, settings = self._custom_tool_settings()
        raw = settings.get("usage_count")
        values = dict(raw) if isinstance(raw, dict) else {}
        current = values.get(tool_id, 0)
        if not isinstance(current, int) or isinstance(current, bool) or current < 0:
            current = 0
        values[tool_id] = current + 1
        settings["usage_count"] = values
        self.save_config(config)
        return current + 1

    def record_tool_recent(self, tool_id: str) -> None:
        config, settings = self._custom_tool_settings()
        raw = settings.get("recent_tools")
        items = list(raw) if isinstance(raw, list) else []
        items = [item for item in items if isinstance(item, str)]
        if tool_id in items:
            items.remove(tool_id)
        items.insert(0, tool_id)
        items = items[:10]
        settings["recent_tools"] = items
        self.save_config(config)

    def record_tool_use(self, tool_id: str) -> None:
        """Persist recent history and usage as one atomic settings update."""
        config, settings = self._custom_tool_settings()
        raw = settings.get("recent_tools")
        recent = raw if isinstance(raw, list) else []
        settings["recent_tools"] = [tool_id, *[
            item for item in recent if isinstance(item, str) and item != tool_id
        ]][:10]
        raw_counts = settings.get("usage_count")
        counts = dict(raw_counts) if isinstance(raw_counts, dict) else {}
        count = counts.get(tool_id, 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            count = 0
        counts[tool_id] = count + 1
        settings["usage_count"] = counts
        self.save_config(config)

    def recent_tools(self) -> list[str]:
        config, settings = self._custom_tool_settings()
        raw = settings.get("recent_tools")
        items = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
        return items[:10]

    def _custom_tool_settings(self) -> tuple[dict[str, Any], dict[str, Any]]:
        config = self.load_config()
        settings = config.get("custom_tools")
        if not isinstance(settings, dict):
            settings = {}
            config["custom_tools"] = settings
        return config, settings

    def _tool_file_timestamp(self, tool_id: str, fallback: float) -> float:
        for directory in (self.paths.custom_dir, self.paths.overrides_dir):
            source = directory / f"{tool_id}.json"
            try:
                if source.is_file():
                    return source.stat().st_mtime
            except OSError:
                pass
        return fallback

    def python_environment(self) -> tuple[str, str]:
        provider, executable, _ = self.runtime_environment("python")
        return provider, executable

    def runtime_environment(self, plugin: str) -> tuple[str, str, str]:
        if plugin not in {"python", "powershell", "android"}:
            raise ValueError("未知运行环境")
        section = self.load_config().get(plugin, {})
        if not isinstance(section, dict):
            return "managed", "", ""
        provider = "custom" if section.get("provider") == "custom" else "managed"
        return (provider, str(section.get("custom_executable") or ""),
                str(section.get("custom_scrcpy") or ""))

    def set_runtime_environment(
        self, plugin: str, provider: str, executable: str = "", scrcpy: str = "",
        version: str = "",
    ) -> None:
        self.runtime_environment(plugin)  # Validate the configuration section name.
        if provider not in {"managed", "custom"}:
            raise ValueError("未知运行环境来源")
        if provider == "custom" and not executable:
            raise ValueError("请选择本地可执行文件")
        config = self.load_config()
        section = config.setdefault(plugin, {})
        section.update(provider=provider, custom_executable=executable or None,
                       custom_scrcpy=scrcpy or None, custom_version=version)
        self.save_config(config)

    @staticmethod
    def _copy_default() -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(DEFAULT_CONFIG)))

    def import_user_configuration(self, source_directory: Path) -> Path:
        source = source_directory.resolve()
        destination = self.paths.data_dir.resolve()
        self._validate_transfer_source(source, destination)
        entries = self._configuration_entries(source)
        if not entries:
            raise ValueError("所选目录不包含 PopTools 本地脚本")

        backup = self.paths.backups_dir / (
            "import-before-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        )
        current_entries = self._configuration_entries(destination)
        if current_entries:
            backup.mkdir(parents=True, exist_ok=False)
            for entry in current_entries:
                self._copy_entry(entry, backup / entry.name)

        # Import is additive: retain current tools/scripts and merge the selected
        # export into them. Files with the same relative path are updated from the
        # import, while unrelated local entries remain in place and recoverable in
        # the pre-import backup above.
        destination.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            self._copy_entry(entry, destination / entry.name)
        return backup

    def export_user_configuration(self, documents_directory: Path) -> Path:
        source = self.paths.data_dir.resolve()
        entries = self._configuration_entries(source)
        if not entries:
            self.load_config()
            entries = self._configuration_entries(source)

        documents = documents_directory.resolve()
        documents.mkdir(parents=True, exist_ok=True)
        destination = documents / (
            "PopTools本地脚本-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        )
        destination.mkdir(parents=False, exist_ok=False)
        for entry in entries:
            self._copy_entry(entry, destination / entry.name)
        return destination

    @staticmethod
    def _configuration_entries(directory: Path) -> list[Path]:
        return [directory / name for name in LOCAL_SCRIPT_ENTRIES if (directory / name).exists()]

    @staticmethod
    def _validate_transfer_source(source: Path, destination: Path) -> None:
        if not source.is_dir():
            raise ValueError("请选择有效的本地脚本目录")
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError("导入目录不能与应用本地脚本目录相同或互相包含")

    @staticmethod
    def _copy_entry(source: Path, destination: Path) -> None:
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
