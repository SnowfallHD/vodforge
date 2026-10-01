"""Bounded Library card windows that retain delegates for surviving owners."""

from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Slot,
)
from PySide6.QtQml import qmlRegisterType

_registered = False
_ROOT_INDEX = QModelIndex()


def register_window_model() -> None:
    global _registered
    if not _registered:
        # PySide's runtime accepts a string name; its stub incorrectly requires bytes.
        qmlRegisterType(LibraryWindowModel, "VODForge.Models", 1, 0, "OwnerWindowModel")  # type: ignore[call-overload]
        _registered = True


class LibraryWindowModel(QAbstractListModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX
    ) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self):
        return {int(Qt.ItemDataRole.UserRole): b"modelData"}

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if role == int(Qt.ItemDataRole.UserRole) and 0 <= index.row() < len(self._rows):
            return self._rows[index.row()]
        return None

    @Slot("QVariantList")
    def replace(self, rows: list[dict[str, Any]]) -> None:
        """Remove departed owners, insert newcomers, and retain surviving cards."""
        next_rows = [dict(row) for row in rows]
        owners = [str(row["owner"]) for row in next_rows]
        # Scene projections have unique owners. Refuse ambiguous identity rather
        # than accidentally reassigning an existing card's artwork or actions.
        if len(set(owners)) != len(owners):
            raise ValueError("Library window owners must be unique")
        retained = set(owners)
        for index in range(len(self._rows) - 1, -1, -1):
            if str(self._rows[index]["owner"]) not in retained:
                self.beginRemoveRows(QModelIndex(), index, index)
                self._rows.pop(index)
                self.endRemoveRows()
        for index, row in enumerate(next_rows):
            owner = owners[index]
            existing = next(
                (
                    position
                    for position in range(index, len(self._rows))
                    if str(self._rows[position]["owner"]) == owner
                ),
                None,
            )
            if existing is None:
                self.beginInsertRows(QModelIndex(), index, index)
                self._rows.insert(index, row)
                self.endInsertRows()
            else:
                if existing != index:
                    self.beginMoveRows(
                        QModelIndex(), existing, existing, QModelIndex(), index
                    )
                    self._rows.insert(index, self._rows.pop(existing))
                    self.endMoveRows()
                if self._rows[index] != row:
                    self._rows[index] = row
                    self.dataChanged.emit(
                        self.index(index),
                        self.index(index),
                        [int(Qt.ItemDataRole.UserRole)],
                    )
