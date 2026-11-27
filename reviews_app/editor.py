"""Вкладка «Ввод отзывов»."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .storage import Review, Store
from .widgets import NAME_ROLE, PATH_ROLE, DropImageList, ReviewTextEdit

FILE_FILTER = "Картинки (*.webp *.jpg *.jpeg *.png *.bmp *.gif);;Все файлы (*)"


def review_title(store: Store, r: Review) -> str:
    first = r.text.strip().splitlines()[0] if r.text.strip() else "(без текста)"
    if len(first) > 40:
        first = first[:40] + "…"
    return f"№{store.number(r)}  {first}  [{len(r.images)} фото]"


class EditorTab(QWidget):
    changed = Signal()

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.current: Review | None = None

        # --- слева: список отзывов ---
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        btn_new = QPushButton("+ Новый отзыв")
        btn_new.clicked.connect(self.next_review)
        btn_del = QPushButton("Удалить отзыв")
        btn_del.clicked.connect(self.delete_review)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Отзывы"))
        ll.addWidget(self.list, 1)
        lb = QHBoxLayout()
        lb.addWidget(btn_new)
        lb.addWidget(btn_del)
        ll.addLayout(lb)

        # --- справа: редактор ---
        self.header = QLabel()
        self.header.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.text = ReviewTextEdit()
        self.text.setPlaceholderText("Текст отзыва…")
        self.text.textChanged.connect(self._on_text_changed)
        self.text.filesDropped.connect(self.add_images)

        self.images = DropImageList(140)
        self.images.filesDropped.connect(self.add_images)
        self.images.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(PATH_ROLE)))
        )
        hint = QLabel("Перетащите сюда картинки (.webp и др.) или нажмите «Добавить картинки». Delete — удалить выбранные.")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)

        btn_add = QPushButton("Добавить картинки…")
        btn_add.clicked.connect(self.pick_images)
        btn_rm = QPushButton("Удалить выбранные картинки")
        btn_rm.clicked.connect(self.remove_selected_images)
        self.btn_next = QPushButton("Сохранить и следующий отзыв  ▶   (Ctrl+Enter)")
        self.btn_next.setStyleSheet("font-weight: bold; padding: 8px 16px;")
        self.btn_next.clicked.connect(self.next_review)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.header)
        rl.addWidget(self.text, 2)
        rl.addWidget(hint)
        rl.addWidget(self.images, 3)
        rb = QHBoxLayout()
        rb.addWidget(btn_add)
        rb.addWidget(btn_rm)
        rb.addStretch(1)
        rb.addWidget(self.btn_next)
        rl.addLayout(rb)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 800])
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self, self.next_review, context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence.Delete, self.images, self.remove_selected_images, context=Qt.WidgetShortcut)

        self._save_timer = QTimer(self, singleShot=True, interval=700)
        self._save_timer.timeout.connect(self.commit)

        self.reload()
        # начинаем с нового пустого отзыва
        self.next_review()

    # ---------- список ----------
    def reload(self, select: Review | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.store.reviews:
            it = QListWidgetItem(review_title(self.store, r))
            it.setData(Qt.UserRole, r.id)
            self.list.addItem(it)
            if select is not None and r.id == select.id:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _refresh_current_title(self) -> None:
        if not self.current:
            return
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == self.current.id:
                it.setText(review_title(self.store, self.current))
        self.header.setText(f"Отзыв №{self.store.number(self.current)} из {len(self.store.reviews)}")

    def _on_select(self, item: QListWidgetItem | None, _prev=None) -> None:
        if item is None:
            return
        r = self.store.get(item.data(Qt.UserRole))
        if r is None or r is self.current:
            return
        self._leave_current(keep=r)
        self.reload(select=r)
        self.load(r)

    # ---------- текущий отзыв ----------
    def load(self, r: Review) -> None:
        self.current = r
        self.text.blockSignals(True)
        self.text.setPlainText(r.text)
        self.text.blockSignals(False)
        self._fill_images()
        self._refresh_current_title()
        self.text.setFocus()
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)

    def _fill_images(self) -> None:
        self.images.clear()
        if not self.current:
            return
        for i, name in enumerate(self.current.images, 1):
            self.images.add_image(self.store.source_path(self.current, name), f"{i}. {name}", name)

    def commit(self) -> None:
        self._save_timer.stop()
        if self.current is None:
            return
        text = self.text.toPlainText()
        if text != self.current.text:
            self.current.text = text
            self.store.save()
            self.changed.emit()
        self._refresh_current_title()

    def _on_text_changed(self) -> None:
        self._save_timer.start()

    def _leave_current(self, keep: Review | None = None) -> None:
        """Сохранить текущий отзыв; пустой — выбросить."""
        self.commit()
        if self.current is not None and self.current.is_empty() and self.current is not keep:
            self.store.delete(self.current)
            self.changed.emit()
        self.current = None

    def next_review(self) -> None:
        self.commit()
        if self.current is not None and self.current.is_empty():
            self.text.setFocus()  # уже стоим на пустом отзыве
            return
        self._leave_current()
        r = self.store.create()
        self.reload(select=r)
        self.load(r)
        self.changed.emit()

    def delete_review(self) -> None:
        if self.current is None:
            return
        if not self.current.is_empty():
            ans = QMessageBox.question(
                self, "Удалить отзыв", f"Удалить отзыв №{self.store.number(self.current)} вместе с картинками?"
            )
            if ans != QMessageBox.Yes:
                return
        self._save_timer.stop()
        idx = self.store.number(self.current) - 1
        self.store.delete(self.current)
        self.current = None
        self.changed.emit()
        if self.store.reviews:
            r = self.store.reviews[min(idx, len(self.store.reviews) - 1)]
            self.reload(select=r)
            self.load(r)
        else:
            self.next_review()

    # ---------- картинки ----------
    def add_images(self, paths: list[str]) -> None:
        if self.current is None:
            self.next_review()
        self.commit()
        added = self.store.add_images(self.current, paths)
        if added:
            self._fill_images()
            self._refresh_current_title()
            self.changed.emit()

    def pick_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите картинки", "", FILE_FILTER)
        if paths:
            self.add_images(paths)

    def remove_selected_images(self) -> None:
        if self.current is None:
            return
        names = [it.data(NAME_ROLE) for it in self.images.selectedItems()]
        if not names:
            return
        for n in names:
            self.store.remove_image(self.current, n)
        self._fill_images()
        self._refresh_current_title()
        self.changed.emit()
