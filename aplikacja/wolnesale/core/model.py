"""Model planu lekcji — niezależny od źródła (PDF teraz, XML może kiedyś)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from functools import cached_property

from .sale import sort_key

DAY_NAMES = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
DAY_SHORT = ["Pn", "Wt", "Śr", "Czw", "Pt", "So", "Nd"]


@dataclass(frozen=True)
class Period:
    nr: int
    start: str  # "7:30"
    end: str    # "8:15"

    @property
    def label(self) -> str:
        return f"{self.start}–{self.end}"


@dataclass(frozen=True)
class Lesson:
    day: int            # 0 = poniedziałek
    period: int         # numer lekcji (1..)
    room: str | None    # znormalizowana sala, None gdy brak
    subject: str
    cls: str            # klasa, np. "2TM"
    group: str          # grupa, np. "gr1"
    teacher: str

    def describe(self) -> str:
        parts = [self.subject, self.cls]
        if self.group:
            parts.append(self.group)
        return " · ".join(p for p in parts if p) + f" — {self.teacher}"


@dataclass
class Timetable:
    periods: list[Period]
    days: list[int]
    lessons: list[Lesson]
    source: str = ""        # nazwa pliku źródłowego
    generated: str = ""     # data wygenerowania planu w aSc
    teachers: list[str] = field(default_factory=list)

    # --- zapytania -------------------------------------------------------

    @cached_property
    def rooms(self) -> list[str]:
        return sorted({l.room for l in self.lessons if l.room}, key=sort_key)

    @cached_property
    def occupancy(self) -> dict[tuple[str, int, int], list[Lesson]]:
        occ: dict[tuple[str, int, int], list[Lesson]] = defaultdict(list)
        for l in self.lessons:
            if l.room:
                occ[(l.room, l.day, l.period)].append(l)
        return dict(occ)

    @cached_property
    def period_by_nr(self) -> dict[int, Period]:
        return {p.nr: p for p in self.periods}

    def lessons_at(self, room: str, day: int, period: int) -> list[Lesson]:
        return self.occupancy.get((room, day, period), [])

    def is_free(self, room: str, day: int, period: int) -> bool:
        return (room, day, period) not in self.occupancy

    def busy_count(self, room: str) -> int:
        return sum(1 for (r, _, _) in self.occupancy if r == room)

    # --- zapis / odczyt JSON ---------------------------------------------

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "generated": self.generated,
            "days": self.days,
            "teachers": self.teachers,
            "periods": [asdict(p) for p in self.periods],
            "lessons": [asdict(l) for l in self.lessons],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Timetable":
        return cls(
            periods=[Period(**p) for p in d["periods"]],
            days=list(d["days"]),
            lessons=[Lesson(**l) for l in d["lessons"]],
            source=d.get("source", ""),
            generated=d.get("generated", ""),
            teachers=list(d.get("teachers", [])),
        )
