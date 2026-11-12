"""Wyszukiwanie wolnych sal i wolnych okien.

Okno = ciąg kolejnych wolnych lekcji w jednej sali w jednym dniu.
Przerwy między lekcjami nie przerywają okna (wolna 3. i 4. lekcja = jedno okno).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import DAY_SHORT, Timetable


@dataclass(frozen=True)
class FreeWindow:
    room: str
    day: int
    first: int   # pierwsza wolna lekcja
    last: int    # ostatnia wolna lekcja (włącznie)

    @property
    def length(self) -> int:
        return self.last - self.first + 1

    def periods_label(self) -> str:
        return f"{self.first}" if self.first == self.last else f"{self.first}–{self.last}"

    def time_label(self, tt: Timetable) -> str:
        p1, p2 = tt.period_by_nr.get(self.first), tt.period_by_nr.get(self.last)
        if not (p1 and p2):
            return ""
        return f"{p1.start}–{p2.end}"

    def day_label(self) -> str:
        return DAY_SHORT[self.day]


def free_windows(tt: Timetable, room: str, day: int, first: int | None = None,
                 last: int | None = None) -> list[FreeWindow]:
    """Wolne okna sali w danym dniu, ograniczone do lekcji first..last."""
    nrs = [p.nr for p in tt.periods]
    if first is not None:
        nrs = [n for n in nrs if n >= first]
    if last is not None:
        nrs = [n for n in nrs if n <= last]

    windows: list[FreeWindow] = []
    start = prev = None
    for n in nrs:
        free = tt.is_free(room, day, n)
        contiguous = prev is not None and n == prev + 1
        if free and start is not None and contiguous:
            prev = n
            continue
        if start is not None:
            windows.append(FreeWindow(room, day, start, prev))
            start = None
        if free:
            start = n
        prev = n
    if start is not None:
        windows.append(FreeWindow(room, day, start, prev))
    return windows


def find_free(tt: Timetable, rooms: Iterable[str], days: Iterable[int],
              first: int | None = None, last: int | None = None,
              min_length: int = 1) -> list[FreeWindow]:
    """Wszystkie wolne okna o długości >= min_length; sortowane: dzień, długość malejąco, sala."""
    out: list[FreeWindow] = []
    room_list = list(rooms)
    for d in days:
        for r in room_list:
            out.extend(w for w in free_windows(tt, r, d, first, last) if w.length >= min_length)
    order = {r: i for i, r in enumerate(room_list)}
    out.sort(key=lambda w: (w.day, -w.length, order.get(w.room, 0), w.first))
    return out
