from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

THEME_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
DEFAULT_THEME_ID = "material3"

REQUIRED_COLOR_KEYS = frozenset(
    {
        "primary",
        "primaryForeground",
        "primaryHover",
        "primaryContainer",
        "primaryContainerHover",
        "primaryText",
        "secondary",
        "secondaryForeground",
        "secondaryHover",
        "secondaryContainer",
        "secondaryContainerHover",
        "secondaryText",
        "tertiary",
        "tertiaryForeground",
        "tertiaryHover",
        "tertiaryContainer",
        "tertiaryContainerHover",
        "tertiaryText",
        "surface",
        "surfaceContainerLow",
        "surfaceContainer",
        "surfaceContainerHigh",
        "outline",
        "outlineVariant",
        "textPrimary",
        "textSecondary",
        "success",
        "successForeground",
        "successContainer",
        "tealContainer",
        "teal",
        "errorColor",
        "errorContainer",
        "middlePanel",
        "consoleBackground",
        "consoleText",
        "consoleMuted",
        "consoleHeaderBackground",
        "consoleTag",
        "consoleWarning",
        "consoleError",
        "consoleDivider",
        "buttonDefault",
        "buttonHover",
        "buttonPressed",
        "buttonDisabled",
        "buttonShadow",
        "buttonHighlight",
        "cardSelected",
    }
)
REQUIRED_RADIUS_KEYS = frozenset(
    {"none", "tiny", "small", "medium", "large", "xlarge", "full"}
)
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")


@dataclass(frozen=True)
class ThemeEntry:
    theme_id: str
    name: str
    config_json: str


class ThemeCatalog:
    """Discover and validate UI themes without coupling them to app settings."""

    def __init__(self, config_dir: Path, user_config_dir: Path | None = None) -> None:
        self.config_dir = config_dir
        self.user_config_dir = user_config_dir
        self._entries: dict[str, ThemeEntry] = {}

    def refresh(self) -> bool:
        entries: dict[str, ThemeEntry] = {}
        config_dirs = (self.config_dir, self.user_config_dir)
        for config_dir in config_dirs:
            if config_dir is None or not config_dir.is_dir():
                continue
            paths = sorted(
                config_dir.glob("*.json"),
                key=lambda path: (path.stem != DEFAULT_THEME_ID, path.stem.casefold()),
            )
            for path in paths:
                if path.stem in {"decade", "zio"}:
                    continue  # Former app themes are now independent launcher styles.
                entry = self._load_entry(path)
                if entry is not None:
                    # User themes are scanned last and intentionally override a
                    # bundled theme with the same ID.
                    entries[entry.theme_id] = entry
        changed = entries != self._entries
        self._entries = entries
        return changed

    def theme_items(self) -> list[dict[str, str]]:
        return [
            {"label": self._entries[theme_id].name, "value": theme_id}
            for theme_id in sorted(
                self._entries,
                key=lambda value: (value != DEFAULT_THEME_ID, value.casefold()),
            )
        ]

    def contains(self, theme_id: str) -> bool:
        return theme_id in self._entries

    def config_json(self, theme_id: str) -> str:
        entry = self._entries.get(theme_id)
        return entry.config_json if entry is not None else ""

    def resolve(self, theme_id: str) -> str:
        if theme_id in self._entries:
            return theme_id
        if DEFAULT_THEME_ID in self._entries:
            return DEFAULT_THEME_ID
        return next(iter(self._entries), DEFAULT_THEME_ID)

    def _load_entry(self, path: Path) -> ThemeEntry | None:
        theme_id = path.stem
        if not THEME_ID_PATTERN.fullmatch(theme_id):
            logger.warning("忽略主题配置 %s：文件名不是有效的主题 ID", path)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._validate_config(data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("忽略无效主题配置 %s：%s", path, exc)
            return None
        name = str(data["name"]).strip()
        return ThemeEntry(
            theme_id=theme_id,
            name=name,
            config_json=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _validate_config(data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("根节点必须是对象")
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("缺少有效的 name")
        for section_name in ("colors", "darkColors"):
            section = data.get(section_name)
            if not isinstance(section, dict):
                raise ValueError(f"缺少 {section_name}")
            missing = sorted(REQUIRED_COLOR_KEYS.difference(section))
            if missing:
                raise ValueError(f"{section_name} 缺少字段：{', '.join(missing)}")
            invalid = sorted(
                key
                for key in REQUIRED_COLOR_KEYS
                if not isinstance(section[key], str)
                or COLOR_PATTERN.fullmatch(section[key]) is None
            )
            if invalid:
                raise ValueError(f"{section_name} 包含无效颜色：{', '.join(invalid)}")
        radius = data.get("radius")
        if not isinstance(radius, dict):
            raise ValueError("缺少 radius")
        missing_radius = sorted(REQUIRED_RADIUS_KEYS.difference(radius))
        if missing_radius:
            raise ValueError(f"radius 缺少字段：{', '.join(missing_radius)}")
        invalid_radius = sorted(
            key
            for key in REQUIRED_RADIUS_KEYS
            if not isinstance(radius[key], (int, float))
            or isinstance(radius[key], bool)
            or radius[key] < 0
        )
        if invalid_radius:
            raise ValueError(f"radius 包含无效值：{', '.join(invalid_radius)}")
