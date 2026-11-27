"""Вкладка «Ввод отзывов»."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .importer import DropData, extract_images, snapshot
from .storage import Product, Review, Store
from .widgets import NAME_ROLE, PATH_ROLE, DropImageList, ReviewTextEdit, button, hrow, label

FILE_FILTER = "Картинки (*.webp *.jpg *.jpeg *.png *.bmp *.gif);;Все файлы (*)"


def review_title(store: Store, r: Review) -> str:
    first = r.text.strip().splitlines()[0] if r.text.strip() else "без текста"
    if len(first) > 34:
        first = first[:34].rstrip() + "…"
    photos = f"{len(r.images)} фото" if r.images else "нет фото"
    return f"Отзыв №{store.number(r)}  ·  {photos}\n{first}"


def make_review_list() -> QListWidget:
    lst = QListWidget()
    lst.setObjectName("ReviewList")
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    lst.setTextElideMode(Qt.ElideRight)
    lst.setCursor(Qt.PointingHandCursor)
    return lst


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    return f, lay


class EditorTab(QWidget):
    changed = Signal()
    message = Signal(str)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.store = store
        self.current: Review | None = None
        self.product: Product = store.ensure_product()

        # --- слева: список отзывов ---
        left, ll = card()
        ll.setContentsMargins(12, 14, 12, 12)
        self.count_badge = label("", "Badge")
        ll.addLayout(hrow(label("Все отзывы", "Section"), self.count_badge, stretch_at=2))
        self.list = make_review_list()
        self.list.currentItemChanged.connect(self._on_select)
        ll.addWidget(self.list, 1)
        btn_new = button("＋  Новый отзыв")
        btn_new.clicked.connect(self.next_review)
        ll.addWidget(btn_new)

        # --- справа: редактор ---
        right, rl = card()
        self.title = label("", "Title")
        self.product_badge = label("", "Badge")
        self.btn_delete = button("Удалить отзыв", "danger")
        self.btn_delete.clicked.connect(self.delete_review)
        rl.addLayout(hrow(self.title, self.product_badge, self.btn_delete, stretch_at=2))

        rl.addWidget(label("Текст отзыва", "Section"))
        self.text = ReviewTextEdit()
        self.text.setPlaceholderText("Вставьте или напишите текст отзыва…")
        self.text.textChanged.connect(self._save_timer_start)
        self.text.dropped.connect(self.import_drop)
        rl.addWidget(self.text, 2)

        self.photos_label = label("Фотографии", "Section")
        btn_add = button("Добавить…", "ghost", "Выбрать картинки на компьютере")
        btn_add.clicked.connect(self.pick_images)
        self.btn_rm = button("Удалить выбранные", "ghost", "Или клавиша Delete")
        self.btn_rm.clicked.connect(self.remove_selected_images)
        rl.addSpacing(4)
        rl.addLayout(hrow(self.photos_label, btn_add, self.btn_rm, stretch_at=1, spacing=2))
        self.images = DropImageList(132)
        self.images.dropped.connect(self.import_drop)
        self.images.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(PATH_ROLE)))
        )
        self.images.itemSelectionChanged.connect(self._update_buttons)
        self.images.setContextMenuPolicy(Qt.CustomContextMenu)
        self.images.customContextMenuRequested.connect(self._image_menu)
        rl.addWidget(self.images, 3)

        self.btn_next = button("Сохранить и следующий  →", "primary")
        self.btn_next.setToolTip("Ctrl+Enter")
        self.btn_next.clicked.connect(self.next_review)
        rl.addSpacing(4)
        rl.addLayout(hrow(label("Всё сохраняется автоматически  ·  Ctrl+Enter — следующий отзыв", "Muted"),
                          self.btn_next, stretch_at=1))

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 820])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(split)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self, self.next_review, context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence.Delete, self.images, self.remove_selected_images, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence.Paste, self.images, self.paste_images, context=Qt.WidgetShortcut)

        self._save_timer = QTimer(self, singleShot=True, interval=700)
        self._save_timer.timeout.connect(self.commit)

        self.reload()
        self.next_review()  # начинаем с нового пустого отзыва

    # ---------- список ----------
    def reload(self, select: Review | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.store.reviews_of(self.product):
            it = QListWidgetItem(review_title(self.store, r))
            it.setData(Qt.UserRole, r.id)
            self.list.addItem(it)
            if select is not None and r.id == select.id:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if self.list.currentItem():
            self.list.scrollToItem(self.list.currentItem())
        self.count_badge.setText(str(len(self.store.reviews_of(self.product))))

    def _refresh_current_title(self) -> None:
        if not self.current:
            return
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == self.current.id:
                it.setText(review_title(self.store, self.current))
        self.title.setText(f"Отзыв №{self.store.number(self.current)}")
        self.product_badge.setText(self.product.name)
        n = len(self.current.images)
        self.photos_label.setText(f"Фотографии  ·  {n}" if n else "Фотографии")
        self.count_badge.setText(str(len(self.store.reviews_of(self.product))))
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.btn_rm.setVisible(bool(self.images.selectedItems()))
        self.btn_next.setEnabled(self.current is not None and not self.current.is_empty()
                                 or bool(self.text.toPlainText().strip()))

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
            self.images.add_image(self.store.source_path(self.current, name), f"Фото {i}", name)
        self.images.viewport().update()

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

    def _save_timer_start(self) -> None:
        self._save_timer.start()
        self._update_buttons()

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
        saved = self.current is not None
        self._leave_current()
        r = self.store.create(self.product)
        self.reload(select=r)
        self.load(r)
        self.changed.emit()
        if saved:
            self.message.emit("Отзыв сохранён ✓")

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
        rest = self.store.reviews_of(self.product)
        if rest:
            r = rest[min(idx, len(rest) - 1)]
            self.reload(select=r)
            self.load(r)
        else:
            self.next_review()

    def set_product(self, p: Product) -> None:
        """Переключиться на другой товар: открываем новый пустой отзыв в нём."""
        if p is self.product:
            return
        self._leave_current()
        self.product = p
        self.reload()
        self.next_review()

    def refresh_product_name(self) -> None:
        self.product_badge.setText(self.product.name)

    # ---------- картинки ----------
    def add_images(self, paths: list[str | Path]) -> int:
        if self.current is None:
            self.next_review()
        self.commit()
        added = self.store.add_images(self.current, paths)
        if added:
            self._fill_images()
            self._refresh_current_title()
            self.changed.emit()
        return added

    def import_drop(self, data: DropData) -> None:
        """Картинки из перетаскивания/буфера: файлы, браузер, данные."""
        work = Path(tempfile.mkdtemp(prefix="reviews_drop_"))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.message.emit("Получаю картинку…")
        QApplication.processEvents()
        try:
            paths, errors = extract_images(data, work)
            added = self.add_images(paths) if paths else 0
        finally:
            QApplication.restoreOverrideCursor()
            shutil.rmtree(work, ignore_errors=True)
        if added:
            self.message.emit(f"Добавлено картинок: {added} ✓")
        else:
            details = "\n".join(errors[:5])
            QMessageBox.warning(
                self, "Не получилось добавить",
                "Не удалось получить картинку из того, что перетащили.\n\n"
                "Попробуйте: правый клик по картинке в браузере → «Копировать картинку», "
                "затем Ctrl+V здесь. Или сохраните её на компьютер и перетащите файл."
                + (f"\n\nПодробности:\n{details}" if details else ""),
            )

    def paste_images(self) -> None:
        data = snapshot(QApplication.clipboard().mimeData())
        if data.has_anything():
            self.import_drop(data)
        else:
            self.message.emit("В буфере обмена нет картинки")

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

    def _image_menu(self, pos) -> None:
        menu = QMenu(self)
        item = self.images.itemAt(pos)
        if item is not None:
            if not item.isSelected():
                self.images.clearSelection()
                item.setSelected(True)
            menu.addAction("Открыть", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(PATH_ROLE))))
            menu.addAction("Удалить", self.remove_selected_images)
            menu.addSeparator()
        menu.addAction("Вставить из буфера (Ctrl+V)", self.paste_images)
        menu.addAction("Добавить с компьютера…", self.pick_images)
        menu.exec(self.images.mapToGlobal(pos))
