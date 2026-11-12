"""Wspólne elementy GUI: kolory, filtr sal, pomocnicze funkcje tabel."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QTableWidget, QTableWidgetItem, QWidget)

from ..core.model import DAY_NAMES, Lesson, Timetable
from ..core.sale import BUILDINGS, building

FREE = QColor("#d8f3dc")
FREE_ALT = QColor("#c3e9cb")
BUSY = QColor("#f6c6c0")
BUSY_ALT = QColor("#efb1a9")
ALL_BUILDINGS = "Wszystkie budynki"


class RoomFilter(QWidget):
    """Filtr: budynek + fragment nazwy sali."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.building = QComboBox()
        self.building.addItems([ALL_BUILDINGS, *BUILDINGS])
        self.text = QLineEdit()
        self.text.setPlaceholderText("Sala, np. 11w")
        self.text.setClearButtonEnabled(True)
        self.text.setMaximumWidth(140)
        lay.addWidget(QLabel("Budynek:"))
        lay.addWidget(self.building)
        lay.addWidget(QLabel("Sala:"))
        lay.addWidget(self.text)
        self.building.currentIndexChanged.connect(self.changed)
        self.text.textChanged.connect(self.changed)

    def apply(self, rooms: list[str]) -> list[str]:
        b = self.building.currentText()
        t = self.text.text().strip().upper()
        return [r for r in rooms
                if (b == ALL_BUILDINGS or building(r) == b) and (not t or t in r.upper())]


def make_table() -> QTableWidget:
    t = QTableWidget()
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setWordWrap(True)
    t.setAlternatingRowColors(False)
    return t


def slot_tooltip(tt: Timetable, room: str, day: int, period: int, lessons: list[Lesson]) -> str:
    p = tt.period_by_nr.get(period)
    head = f"Sala {room} · {DAY_NAMES[day]} · lekcja {period}" + (f" ({p.label})" if p else "")
    if not lessons:
        return head + "\n✅ wolna"
    return head + "\n" + "\n".join("⛔ " + l.describe() for l in lessons)


def item(text: str = "", color: QColor | None = None, tooltip: str = "", data=None,
         align=Qt.AlignCenter) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(align)
    if color is not None:
        it.setBackground(color)
        it.setForeground(QColor("#1b1b1b"))
    if tooltip:
        it.setToolTip(tooltip)
    if data is not None:
        it.setData(Qt.UserRole, data)
    return it
