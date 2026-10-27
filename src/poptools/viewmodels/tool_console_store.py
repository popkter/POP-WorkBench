"""Per-tool output storage and batched notifications shared by all windows."""
from PySide6.QtCore import QObject, QTimer, Signal


class ToolConsoleStore(QObject):
    changed = Signal(str)
    MAX_CHARS = 200_000
    RETAINED_CHARS = 150_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._texts = {"": "泡泡的工作台 已就绪\n"}
        self._pending: dict[str, list[str]] = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.flush)

    def text(self, tool_id: str = "") -> str:
        return self._texts.get(tool_id, "")

    def clear(self, tool_id: str = "") -> None:
        self._pending.pop(tool_id, None)
        if not self._pending:
            self.timer.stop()
        self._texts[tool_id] = ""
        self.changed.emit(tool_id)

    def append(self, tool_id: str, text: str) -> None:
        self._store(tool_id, text)
        self.changed.emit(tool_id)

    def queue(self, tool_id: str, text: str) -> None:
        if not text:
            return
        for key in ("", tool_id) if tool_id else ("",):
            self._pending.setdefault(key, []).append(text)
        if not self.timer.isActive():
            self.timer.start()

    def flush(self) -> None:
        pending, self._pending = self._pending, {}
        for key, chunks in pending.items():
            self.append(key, "".join(chunks))

    def _store(self, key: str, text: str) -> None:
        value = self._texts.get(key, "") + text
        self._texts[key] = value[-self.RETAINED_CHARS:] if len(value) > self.MAX_CHARS else value
