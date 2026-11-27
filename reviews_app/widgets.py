"""Общие виджеты: списки картинок с перетаскиванием внутрь и наружу."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDrag, QIcon, QPixmap
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem, QPlainTextEdit

from .imaging import load_qimage
from .storage import is_image_file

PATH_ROLE = Qt.UserRole
NAME_ROLE = Qt.UserRole + 1

_thumb_cache: dict[tuple[str, float, int], QPixmap] = {}


def thumbnail(path: Path, size: int) -> QPixmap:
    try:
        key = (str(path), path.stat().st_mtime, size)
    except OSError:
        return QPixmap()
    if key not in _thumb_cache:
        try:
            _thumb_cache[key] = QPixmap.fromImage(load_qimage(path, size))
        except Exception:
            _thumb_cache[key] = QPixmap()
    return _thumb_cache[key]


def image_paths_from_mime(mime: QMimeData) -> list[str]:
    if not mime.hasUrls():
        return []
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and is_image_file(u.toLocalFile())]


class ImageList(QListWidget):
    """Сетка миниатюр."""

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(parent)
        self.thumb_size = thumb_size
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setIconSize(QSize(thumb_size, thumb_size))
        self.setGridSize(QSize(thumb_size + 24, thumb_size + 34))
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)

    def add_image(self, path: Path, label: str, name: str = "") -> QListWidgetItem:
        item = QListWidgetItem(QIcon(thumbnail(path, self.thumb_size)), label)
        item.setData(PATH_ROLE, str(path))
        item.setData(NAME_ROLE, name)
        item.setToolTip(str(path))
        self.addItem(item)
        return item


class DropImageList(ImageList):
    """Список картинок, в который можно бросать файлы из проводника."""

    filesDropped = Signal(list)

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(thumb_size, parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def dragEnterEvent(self, e):
        if image_paths_from_mime(e.mimeData()):
            e.acceptProposedAction()
        else:
            e.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        paths = image_paths_from_mime(e.mimeData())
        if paths:
            e.acceptProposedAction()
            self.filesDropped.emit(paths)


class DragOutImageList(ImageList):
    """Список картинок, которые можно перетащить наружу как файлы (.jpg)."""

    def __init__(self, thumb_size: int, parent=None):
        super().__init__(thumb_size, parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragOnly)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def startDrag(self, actions):
        items = self.selectedItems()
        if not items:
            return
        paths = [it.data(PATH_ROLE) for it in items]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = items[0].icon().pixmap(self.thumb_size)
        if not pm.isNull():
            pm = pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(pm)
            drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.CopyAction, Qt.CopyAction)


class ReviewTextEdit(QPlainTextEdit):
    """Поле текста: если в него бросить картинки, они уходят в отзыв, а не вставляются путём."""

    filesDropped = Signal(list)

    def dragEnterEvent(self, e):
        if image_paths_from_mime(e.mimeData()):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if image_paths_from_mime(e.mimeData()):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        paths = image_paths_from_mime(e.mimeData())
        if paths:
            e.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            super().dropEvent(e)
