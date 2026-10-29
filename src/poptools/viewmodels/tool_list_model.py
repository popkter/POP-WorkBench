from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, Qt, Signal, Slot

from poptools.domain.models import ToolDefinition

_EMPTY_INDEX = QModelIndex()


class ToolListModel(QAbstractListModel):
    countChanged = Signal()
    IdRole = Qt.UserRole + 1
    TitleRole = Qt.UserRole + 2
    DescriptionRole = Qt.UserRole + 3
    IconRole = Qt.UserRole + 4
    SelectedRole = Qt.UserRole + 5
    KindRole = Qt.UserRole + 6
    RunningRole = Qt.UserRole + 7
    TagsRole = Qt.UserRole + 8

    def __init__(self) -> None:
        super().__init__()
        self._tools: list[ToolDefinition] = []
        self._display_tools: list[ToolDefinition] = []
        self._selected_id = ""
        self._running_ids: set[str] = set()
        self._filter_query = ""
        self._excluded_ids: set[str] = set()

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.IdRole: b"toolId",
            self.TitleRole: b"title",
            self.DescriptionRole: b"description",
            self.IconRole: b"iconName",
            self.SelectedRole: b"selected",
            self.KindRole: b"executorKind",
            self.RunningRole: b"running",
            self.TagsRole: b"tags",
        }

    def rowCount(self, parent: QModelIndex = _EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self._display_tools)

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._display_tools)

    @Property(int, notify=countChanged)
    def totalCount(self) -> int:
        return len(self._tools)

    @Slot(str, result=int)
    def indexOfTool(self, tool_id: str) -> int:
        return next((i for i, tool in enumerate(self._display_tools) if tool.id == tool_id), -1)

    @Slot(str, result=int)
    def countForKind(self, kind: str) -> int:
        return sum(kind == "all" or tool.executor.kind.value == kind
                   for tool in self._display_tools)

    @Slot(str, result=str)
    def lastToolId(self, kind: str) -> str:
        return next((tool.id for tool in reversed(self._display_tools)
                     if kind == "all" or tool.executor.kind.value == kind), "")

    @Slot(str, result=int)
    def insertionIndex(self, tool_id: str) -> int:
        visible = {tool.id for tool in self._display_tools}
        index = 0
        for tool in self._tools:
            if tool.id == tool_id:
                return index
            index += tool.id in visible
        return index

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._display_tools):
            return None
        tool = self._display_tools[index.row()]
        values = {
            self.IdRole: tool.id,
            self.TitleRole: tool.title,
            self.DescriptionRole: tool.description,
            self.IconRole: tool.presentation.icon,
            self.SelectedRole: tool.id == self._selected_id,
            self.KindRole: tool.executor.kind.value,
            self.RunningRole: tool.id in self._running_ids,
            self.TagsRole: list(tool.tags),
        }
        return values.get(role)

    def set_tools(
        self,
        tools: list[ToolDefinition],
        selected_id: str = "",
        running_ids: set[str] | None = None,
    ) -> None:
        previous = self._display_tools
        previous_selected = self._selected_id
        previous_running = self._running_ids
        previous_total = len(self._tools)
        self._tools = list(tools)
        updated = self._filtered_tools()
        old_ids = [tool.id for tool in previous]
        new_ids = [tool.id for tool in updated]
        structural = set(old_ids) != set(new_ids)
        reordered = old_ids != new_ids
        old_kinds = {tool.id: tool.executor.kind for tool in previous}
        kinds_changed = any(old_kinds.get(tool.id) != tool.executor.kind for tool in updated)
        persistent = []
        if structural:
            self.beginResetModel()
        elif reordered:
            self.layoutAboutToBeChanged.emit()
            persistent = self.persistentIndexList()
        self._display_tools = updated
        self._selected_id = selected_id
        self._running_ids = set(running_ids or ())
        if structural:
            self.endResetModel()
        else:
            if reordered:
                rows = {tool_id: row for row, tool_id in enumerate(new_ids)}
                self.changePersistentIndexList(
                    persistent, [self.index(rows[old_ids[index.row()]], 0)
                                 for index in persistent],
                )
                self.layoutChanged.emit()
            old_tools = {tool.id: tool for tool in previous}
            for row, tool in enumerate(updated):
                roles = []
                if tool != old_tools[tool.id]:
                    roles = list(self.roleNames())
                else:
                    if (tool.id == selected_id) != (tool.id == previous_selected):
                        roles.append(self.SelectedRole)
                    if (tool.id in self._running_ids) != (tool.id in previous_running):
                        roles.append(self.RunningRole)
                if roles:
                    index = self.index(row, 0)
                    self.dataChanged.emit(index, index, roles)
        if structural or reordered or kinds_changed or previous_total != len(tools):
            self.countChanged.emit()

    def set_filter(self, query: str) -> None:
        normalized = query.strip().casefold()
        if normalized == self._filter_query:
            return
        self.beginResetModel()
        self._filter_query = normalized
        self._display_tools = self._filtered_tools()
        self.endResetModel()
        self.countChanged.emit()

    def set_excluded_ids(self, tool_ids: set[str]) -> None:
        if tool_ids == self._excluded_ids:
            return
        self._excluded_ids = set(tool_ids)
        updated = self._filtered_tools()
        wanted = {tool.id for tool in updated}
        for row in range(len(self._display_tools) - 1, -1, -1):
            if self._display_tools[row].id not in wanted:
                self.beginRemoveRows(_EMPTY_INDEX, row, row)
                self._display_tools.pop(row)
                self.endRemoveRows()
        present = {tool.id for tool in self._display_tools}
        for row, tool in enumerate(updated):
            if tool.id not in present:
                self.beginInsertRows(_EMPTY_INDEX, row, row)
                self._display_tools.insert(row, tool)
                self.endInsertRows()
        self.countChanged.emit()

    @Slot(str)
    def select(self, tool_id: str) -> None:
        if tool_id == self._selected_id:
            return
        previous = self._selected_id
        self._selected_id = tool_id
        changed_roles = [self.SelectedRole]
        for candidate in (previous, tool_id):
            row = next(
                (i for i, tool in enumerate(self._display_tools) if tool.id == candidate),
                -1,
            )
            if row >= 0:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, changed_roles)

    @Slot(int, str, result=str)
    def adjacentToolId(self, direction: int, kind_filter: str) -> str:
        tools = [tool for tool in self._display_tools
                 if kind_filter == "all" or tool.executor.kind.value == kind_filter]
        if not tools:
            return ""
        current = next((i for i, tool in enumerate(tools) if tool.id == self._selected_id), -1)
        if current < 0:
            return tools[0 if direction > 0 else -1].id
        target = max(0, min(len(tools) - 1, current + (1 if direction > 0 else -1)))
        return tools[target].id

    def _filtered_tools(self) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._tools
            if tool.id not in self._excluded_ids and (
                not self._filter_query
                or self._filter_query in tool.title.casefold()
                or self._filter_query in tool.description.casefold()
                or self._filter_query in tool.executor.kind.value.casefold()
                or any(self._filter_query in tag.casefold() for tag in tool.tags)
            )
        ]
