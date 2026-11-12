"""Widoki planu: tydzień (ogólny), dzień, wolne sale (wyszukiwarka), sala (szczegóły)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..core.model import DAY_NAMES, DAY_SHORT, Timetable
from ..core.sale import building
from ..core.wolne import find_free, free_windows
from .common import BUSY, BUSY_ALT, FREE, FREE_ALT, RoomFilter, item, make_table, slot_tooltip


def _clear_layout(lay) -> None:
    """Usuwa widżety z layoutu od razu (deleteLater samo zostawiłoby je do następnej pętli)."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


def _legend() -> QLabel:
    lab = QLabel(
        f"<span style='background:{FREE.name()}'>&nbsp;&nbsp;&nbsp;&nbsp;</span> wolna &nbsp;&nbsp;"
        f"<span style='background:{BUSY.name()}'>&nbsp;&nbsp;&nbsp;&nbsp;</span> zajęta &nbsp;&nbsp;"
        "<i>— podwójne kliknięcie otwiera szczegóły sali</i>"
    )
    return lab


class _Base(QWidget):
    roomActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tt: Timetable | None = None

    def set_timetable(self, tt: Timetable | None) -> None:
        self.tt = tt
        self.on_timetable()
        self.refresh()

    def on_timetable(self) -> None:
        pass

    def refresh(self) -> None:
        pass


# ---------------------------------------------------------------------------
class WeekView(_Base):
    """Ogólny widok: sale × (dni × lekcje), same kolory."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter = RoomFilter()
        self.filter.changed.connect(self.refresh)
        self.table = make_table()
        self.table.cellDoubleClicked.connect(self._activate)
        top = QHBoxLayout()
        top.addWidget(self.filter)
        top.addStretch()
        top.addWidget(_legend())
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)

    def _activate(self, row, _col):
        room = self.table.item(row, 0).data(Qt.UserRole)
        self.roomActivated.emit(room)

    def refresh(self):
        t, tt = self.table, self.tt
        t.clear()
        if not tt:
            return
        rooms = self.filter.apply(tt.rooms)
        cols = [(d, p.nr) for d in tt.days for p in tt.periods]
        t.setRowCount(len(rooms))
        t.setColumnCount(len(cols) + 1)
        t.setHorizontalHeaderLabels(["Wolne"] + [f"{DAY_SHORT[d]}\n{nr}" for d, nr in cols])
        t.setVerticalHeaderLabels(rooms)
        for r, room in enumerate(rooms):
            free = 0
            for c, (d, nr) in enumerate(cols, start=1):
                ls = tt.lessons_at(room, d, nr)
                free += not ls
                alt = d % 2 == 1
                color = (BUSY_ALT if alt else BUSY) if ls else (FREE_ALT if alt else FREE)
                t.setItem(r, c, item("", color, slot_tooltip(tt, room, d, nr, ls)))
            t.setItem(r, 0, item(f"{free}/{len(cols)}", None,
                                 f"{room}: {free} wolnych lekcji w tygodniu", data=room))
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Fixed)
        h.setDefaultSectionSize(24)
        t.setColumnWidth(0, 62)
        t.verticalHeader().setDefaultSectionSize(22)


# ---------------------------------------------------------------------------
class DayView(_Base):
    """Jeden dzień: sale × lekcje z opisem zajęć."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.day_buttons = QButtonGroup(self)
        self.day_bar = QHBoxLayout()
        self.filter = RoomFilter()
        self.filter.changed.connect(self.refresh)
        self.table = make_table()
        self.table.cellDoubleClicked.connect(self._activate)
        top = QHBoxLayout()
        top.addLayout(self.day_bar)
        top.addSpacing(20)
        top.addWidget(self.filter)
        top.addStretch()
        top.addWidget(_legend())
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)
        self.day_buttons.idClicked.connect(lambda _id: self.refresh())

    def on_timetable(self):
        for b in self.day_buttons.buttons():
            self.day_buttons.removeButton(b)
        _clear_layout(self.day_bar)
        if not self.tt:
            return
        today = datetime.today().weekday()
        for d in self.tt.days:
            b = QPushButton(DAY_SHORT[d])
            b.setCheckable(True)
            b.setMinimumWidth(44)
            self.day_buttons.addButton(b, d)
            self.day_bar.addWidget(b)
        first = today if today in self.tt.days else self.tt.days[0]
        self.day_buttons.button(first).setChecked(True)

    def _activate(self, row, _col):
        self.roomActivated.emit(self.table.verticalHeaderItem(row).text())

    def refresh(self):
        t, tt = self.table, self.tt
        t.clear()
        if not tt or self.day_buttons.checkedId() < 0:
            return
        d = self.day_buttons.checkedId()
        rooms = self.filter.apply(tt.rooms)
        t.setRowCount(len(rooms))
        t.setColumnCount(len(tt.periods))
        t.setHorizontalHeaderLabels([f"{p.nr}\n{p.label}" for p in tt.periods])
        t.setVerticalHeaderLabels(rooms)
        for r, room in enumerate(rooms):
            for c, p in enumerate(tt.periods):
                ls = tt.lessons_at(room, d, p.nr)
                text = "\n".join(dict.fromkeys(f"{l.cls} {l.subject}" for l in ls))
                t.setItem(r, c, item(text, BUSY if ls else FREE, slot_tooltip(tt, room, d, p.nr, ls)))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setDefaultSectionSize(34)


# ---------------------------------------------------------------------------
class SearchView(_Base):
    """Wyszukiwarka wolnych okien."""

    COLS = ["Dzień", "Sala", "Budynek", "Lekcje", "Godziny", "Ile lekcji"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.day_boxes: dict[int, QCheckBox] = {}
        self.days_bar = QHBoxLayout()
        self.p_from = QComboBox()
        self.p_to = QComboBox()
        self.min_len = QSpinBox()
        self.min_len.setRange(1, 12)
        self.min_len.setValue(2)
        self.min_len.setSuffix(" lekcji")
        self.filter = RoomFilter()
        self.now_btn = QPushButton("⏱ Teraz")
        self.now_btn.setToolTip("Dzisiaj, od bieżącej lekcji do końca dnia")
        self.summary = QLabel()
        self.table = make_table()
        self.table.setColumnCount(len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.cellDoubleClicked.connect(
            lambda r, _c: self.roomActivated.emit(self.table.item(r, 1).text()))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Dni:"))
        row1.addLayout(self.days_bar)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Od lekcji:"))
        row1.addWidget(self.p_from)
        row1.addWidget(QLabel("do:"))
        row1.addWidget(self.p_to)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Co najmniej:"))
        row1.addWidget(self.min_len)
        row1.addStretch()
        row2 = QHBoxLayout()
        row2.addWidget(self.filter)
        row2.addWidget(self.now_btn)
        row2.addStretch()
        row2.addWidget(self.summary)
        lay = QVBoxLayout(self)
        lay.addLayout(row1)
        lay.addLayout(row2)
        lay.addWidget(self.table)

        for w in (self.p_from, self.p_to):
            w.currentIndexChanged.connect(self.refresh)
        self.min_len.valueChanged.connect(self.refresh)
        self.filter.changed.connect(self.refresh)
        self.now_btn.clicked.connect(self.set_now)

    def on_timetable(self):
        _clear_layout(self.days_bar)
        self.day_boxes.clear()
        for w in (self.p_from, self.p_to):
            w.blockSignals(True)
            w.clear()
        if not self.tt:
            return
        for d in self.tt.days:
            cb = QCheckBox(DAY_SHORT[d])
            cb.setChecked(True)
            cb.toggled.connect(self.refresh)
            self.day_boxes[d] = cb
            self.days_bar.addWidget(cb)
        for p in self.tt.periods:
            self.p_from.addItem(f"{p.nr} ({p.start})", p.nr)
            self.p_to.addItem(f"{p.nr} ({p.end})", p.nr)
        self.p_from.setCurrentIndex(0)
        self.p_to.setCurrentIndex(len(self.tt.periods) - 1)
        for w in (self.p_from, self.p_to):
            w.blockSignals(False)

    def set_now(self):
        if not self.tt:
            return
        now = datetime.now()
        day = now.weekday()
        hhmm = now.strftime("%H:%M")
        if day not in self.tt.days:
            self.summary.setText("Dziś nie ma lekcji — pokazuję poniedziałek.")
            day = self.tt.days[0]
            idx = 0
        else:
            idx = next((i for i, p in enumerate(self.tt.periods) if _hm(p.end) >= _hm(hhmm)), None)
            if idx is None:
                idx = 0
        for d, cb in self.day_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(d == day)
            cb.blockSignals(False)
        self.p_from.setCurrentIndex(idx)
        self.p_to.setCurrentIndex(len(self.tt.periods) - 1)
        self.min_len.setValue(1)
        self.refresh()

    def refresh(self):
        t, tt = self.table, self.tt
        t.setSortingEnabled(False)
        t.setRowCount(0)
        if not tt or self.p_from.count() == 0:
            return
        days = [d for d, cb in self.day_boxes.items() if cb.isChecked()]
        first, last = self.p_from.currentData(), self.p_to.currentData()
        rooms = self.filter.apply(tt.rooms)
        res = find_free(tt, rooms, days, first, last, self.min_len.value())
        t.setRowCount(len(res))
        for r, w in enumerate(res):
            vals = [DAY_NAMES[w.day], w.room, building(w.room), w.periods_label(),
                    w.time_label(tt), w.length]
            for c, v in enumerate(vals):
                it = item(str(v), FREE if c == 1 else None)
                if c == 0:
                    it.setData(Qt.UserRole, w.day)
                if c == 5:
                    it.setData(Qt.DisplayRole, v)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        t.setSortingEnabled(True)
        n_rooms = len({w.room for w in res})
        self.summary.setText(f"Znaleziono {len(res)} wolnych okien w {n_rooms} salach")


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


# ---------------------------------------------------------------------------
class RoomView(_Base):
    """Plan tygodnia jednej sali, jak klasyczny plan lekcji."""

    showEquipment = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(100)
        self.info = QLabel()
        self.table = make_table()
        self.free_info = QLabel()
        self.free_info.setWordWrap(True)
        self.equip_info = QLabel()
        self.equip_info.setWordWrap(True)
        self.equip_btn = QPushButton("Pokaż sprzęt w spisie →")
        self.equip_btn.clicked.connect(lambda: self.showEquipment.emit(self.combo.currentText()))
        top = QHBoxLayout()
        top.addWidget(QLabel("Sala:"))
        top.addWidget(self.combo)
        top.addWidget(self.info)
        top.addStretch()
        eq = QHBoxLayout()
        eq.addWidget(self.equip_info, 1)
        eq.addWidget(self.equip_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.free_info)
        lay.addLayout(eq)
        self.combo.currentIndexChanged.connect(self.refresh)

    def on_timetable(self):
        self.combo.blockSignals(True)
        cur = self.combo.currentText()
        self.combo.clear()
        if self.tt:
            self.combo.addItems(self.tt.rooms)
            i = self.combo.findText(cur)
            self.combo.setCurrentIndex(max(i, 0))
        self.combo.blockSignals(False)

    def show_room(self, room: str):
        i = self.combo.findText(room)
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def refresh(self):
        t, tt = self.table, self.tt
        t.clear()
        room = self.combo.currentText()
        if not tt or not room:
            return
        busy = tt.busy_count(room)
        total = len(tt.days) * len(tt.periods)
        self.info.setText(f"<b>{building(room)}</b> · zajęta {busy} z {total} lekcji w tygodniu")
        t.setRowCount(len(tt.periods))
        t.setColumnCount(len(tt.days))
        t.setHorizontalHeaderLabels([DAY_NAMES[d] for d in tt.days])
        t.setVerticalHeaderLabels([f"{p.nr}  {p.label}" for p in tt.periods])
        for r, p in enumerate(tt.periods):
            for c, d in enumerate(tt.days):
                ls = tt.lessons_at(room, d, p.nr)
                if ls:
                    text = "\n".join(
                        f"{l.subject}  {l.cls}{(' ' + l.group) if l.group else ''}\n{l.teacher}" for l in ls)
                    t.setItem(r, c, item(text, BUSY, slot_tooltip(tt, room, d, p.nr, ls)))
                else:
                    t.setItem(r, c, item("wolna", FREE, slot_tooltip(tt, room, d, p.nr, ls)))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lines = []
        for d in tt.days:
            ws = free_windows(tt, room, d)
            txt = ", ".join(f"{w.periods_label()} ({w.time_label(tt)})" for w in ws) or "brak"
            lines.append(f"<b>{DAY_SHORT[d]}</b>: {txt}")
        self.free_info.setText("Wolne okna — " + " &nbsp;|&nbsp; ".join(lines))
        self._update_equipment()

    # --- sprzęt w sali -------------------------------------------------------
    def set_inventory(self, inv) -> None:
        self.inv = inv
        self._update_equipment()

    def _update_equipment(self) -> None:
        inv = getattr(self, "inv", None)
        room = self.combo.currentText()
        if not inv or not room or not inv.items:
            self.equip_info.setText("🖥 Sprzęt: brak spisu (zakładka Sprzęt → Importuj ewidencję)")
            return
        here = inv.in_room(room, with_zapl=False)
        zapl = [i for i in inv.in_room(room) if i.sala.endswith("-ZAPL")]
        txt = f"🖥 <b>Sprzęt w sali ({len(here)}):</b> {inv.summary(here) or 'brak'}"
        if zapl:
            txt += f" &nbsp;|&nbsp; <b>zaplecze ({len(zapl)}):</b> {inv.summary(zapl)}"
        self.equip_info.setText(txt)
