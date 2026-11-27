"""Оформление: светлая тема с акцентным цветом, скруглениями и карточками."""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

ACCENT = "#4f6bed"
ACCENT_HOVER = "#3f59d6"
ACCENT_SOFT = "#e9edfd"
BG = "#f3f4f8"
CARD = "#ffffff"
BORDER = "#e2e5ee"
TEXT = "#1f2330"
MUTED = "#6b7280"
DANGER = "#d64545"

QSS = f"""
QWidget {{ color: {TEXT}; }}
QMainWindow, #Page {{ background: {BG}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 4px 8px; border-radius: 6px; }}

#Header {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
#AppTitle {{ font-size: 17pt; font-weight: 700; color: {TEXT}; }}
#AppDot {{ background: {ACCENT}; border-radius: 6px; }}

#Segment {{ background: {BG}; border-radius: 10px; }}
#Segment QPushButton {{
    background: transparent; border: none; border-radius: 8px;
    padding: 7px 18px; font-weight: 600; color: {MUTED};
}}
#Segment QPushButton:hover {{ color: {TEXT}; }}
#Segment QPushButton:checked {{ background: {CARD}; color: {ACCENT}; }}

#ProductBar {{ background: {BG}; border-radius: 10px; }}

#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Title {{ font-size: 18pt; font-weight: 700; }}
#Section {{ font-weight: 700; color: {TEXT}; font-size: 10.5pt; }}
#Muted {{ color: {MUTED}; }}
#Badge {{ background: {ACCENT_SOFT}; color: {ACCENT}; border-radius: 9px; padding: 2px 9px; font-weight: 600; }}

QPushButton {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:disabled {{ color: #b6bac6; border-color: {BORDER}; background: #fafbfc; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; padding: 9px 18px; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; color: white; }}
QPushButton[kind="primary"]:disabled {{ background: #aab6f3; border-color: #aab6f3; color: white; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {MUTED}; }}
QPushButton[kind="ghost"]:hover {{ background: {BG}; color: {TEXT}; }}
QPushButton[kind="danger"] {{ background: transparent; border: 1px solid transparent; color: {DANGER}; }}
QPushButton[kind="danger"]:hover {{ background: #fdeeee; }}
QPushButton[kind="round"] {{ border-radius: 20px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; padding: 0; font-size: 14pt; }}

QPushButton[kind="icon"] {{ background: transparent; border: 1px solid transparent; color: {MUTED};
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; font-size: 12pt; border-radius: 8px; }}
QPushButton[kind="icon"]:hover {{ background: {CARD}; color: {ACCENT}; border-color: {BORDER}; }}

#ProductBox {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 10px; font-weight: 600; }}
#ProductBox:hover {{ border-color: {ACCENT}; }}
#ProductBox::drop-down {{ border: none; width: 22px; }}
#ProductBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: none; }}

QPlainTextEdit, QTextEdit {{
    background: #fbfbfd; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 10px; font-size: 11pt; selection-background-color: {ACCENT};
}}
QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; background: white; }}

#ReviewList {{ background: transparent; border: none; outline: none; }}
#ReviewList::item {{ padding: 9px 10px; margin: 2px 0; border-radius: 9px; color: {TEXT}; }}
#ReviewList::item:hover {{ background: {BG}; }}
#ReviewList::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

#DropZone {{ background: #fafbff; border: 2px dashed #c9d0ea; border-radius: 12px; outline: none; }}
#DropZone[dragOver="true"] {{ background: {ACCENT_SOFT}; border: 2px dashed {ACCENT}; }}
#Gallery {{ background: transparent; border: none; outline: none; }}
#DropZone::item, #Gallery::item {{ border-radius: 10px; padding: 4px; color: {MUTED}; }}
#DropZone::item:hover, #Gallery::item:hover {{ background: {BG}; }}
#DropZone::item:selected, #Gallery::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

QSplitter::handle {{ background: transparent; width: 10px; }}
QStatusBar {{ background: {CARD}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #d3d7e2; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #b9bfcf; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QProgressDialog {{ background: {CARD}; }}
QProgressBar {{ border: none; background: {BG}; border-radius: 6px; height: 12px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, CARD),
        (QPalette.AlternateBase, BG), (QPalette.Text, TEXT), (QPalette.Button, CARD),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#ffffff"),
        (QPalette.ToolTipBase, TEXT), (QPalette.ToolTipText, "#ffffff"), (QPalette.PlaceholderText, "#9aa0ad"),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    font = QFont("Segoe UI" if sys.platform == "win32" else app.font().family())
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(QSS)


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()
