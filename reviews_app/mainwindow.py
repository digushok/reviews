"""Главное окно."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QTabWidget,
    QToolBar,
)

from .editor import EditorTab
from .imaging import convert_to_jpeg
from .storage import Store
from .viewer import ViewerTab

APP_NAME = "Отзывы"


def default_data_dir() -> Path:
    """Папка «ReviewsData» рядом с программой; если туда писать нельзя — в Документах."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    candidate = base / "ReviewsData"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except OSError:
        return Path.home() / "Documents" / "ReviewsData"


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self.store = Store(data_dir or default_data_dir())
        self.setWindowTitle(APP_NAME)
        self.resize(1150, 780)

        self.editor = EditorTab(self.store)
        self.viewer = ViewerTab(self.store)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.editor, "1. Ввод отзывов")
        self.tabs.addTab(self.viewer, "2. Просмотр (JPEG)")
        self.tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(self.tabs)

        tb = QToolBar()
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addAction("⟳  Преобразовать в JPEG", self.convert_all)
        tb.addSeparator()
        tb.addAction("Открыть папку с данными", self.open_data_dir)
        self.addToolBar(tb)

        self.editor.changed.connect(self._update_status)
        self._update_status()

    def _update_status(self) -> None:
        n = sum(1 for r in self.store.reviews if not r.is_empty())
        imgs = sum(len(r.images) for r in self.store.reviews)
        pending = len(self.store.pending_conversions())
        msg = f"Отзывов: {n}   Картинок: {imgs}"
        if pending:
            msg += f"   Не преобразовано: {pending}"
        msg += f"   Данные: {self.store.root}"
        self.statusBar().showMessage(msg)

    def _on_tab(self, idx: int) -> None:
        if self.tabs.widget(idx) is self.viewer:
            self.editor.commit()
            self.viewer.refresh()
        self._update_status()

    def convert_all(self) -> None:
        self.editor.commit()
        jobs = self.store.pending_conversions()
        errors = []
        if jobs:
            dlg = QProgressDialog("Преобразование в JPEG…", "Отмена", 0, len(jobs), self)
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(0)
            for i, (src, dst) in enumerate(jobs):
                if dlg.wasCanceled():
                    break
                dlg.setValue(i)
                dlg.setLabelText(f"Преобразование {i + 1} из {len(jobs)}: {src.name}")
                QApplication.processEvents()
                try:
                    convert_to_jpeg(src, dst)
                except Exception as e:  # битый файл не должен ронять всё
                    errors.append(f"{src}: {e}")
            dlg.setValue(len(jobs))
        self._update_status()
        if errors:
            QMessageBox.warning(self, APP_NAME, "Не удалось преобразовать:\n\n" + "\n".join(errors[:20]))
        elif not jobs:
            self.statusBar().showMessage("Все картинки уже преобразованы", 4000)
        self.tabs.setCurrentWidget(self.viewer)
        self.viewer.refresh()

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))

    def closeEvent(self, e) -> None:
        self.editor._leave_current()
        super().closeEvent(e)


def main() -> int:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("reviews.app")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    w = MainWindow(data_dir)
    w.show()
    return app.exec()
