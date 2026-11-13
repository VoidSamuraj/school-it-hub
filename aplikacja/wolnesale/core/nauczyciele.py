"""Plan konkretnego nauczyciela: lekcje, okienka, sale i klasy."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .model import Lesson, Timetable
from .sale import sort_key


@dataclass
class TeacherWeek:
    teacher: str
    slots: dict[tuple[int, int], list[Lesson]]      # (dzień, lekcja) -> lekcje
    hours: int                                      # liczba zajętych lekcji w tygodniu
    rooms: list[tuple[str, int]]                    # sala -> ile lekcji (malejąco)
    classes: list[tuple[str, int]]                  # klasa -> ile lekcji
    subjects: list[tuple[str, int]]

    def day_range(self, day: int) -> tuple[int, int] | None:
        """Pierwsza i ostatnia lekcja w danym dniu (None, gdy wolny dzień)."""
        nrs = [p for (d, p) in self.slots if d == day]
        return (min(nrs), max(nrs)) if nrs else None

    def gaps(self, day: int) -> list[int]:
        """Okienka: wolne lekcje między pierwszą a ostatnią lekcją dnia."""
        r = self.day_range(day)
        if not r:
            return []
        return [p for p in range(r[0], r[1] + 1) if (day, p) not in self.slots]


def teacher_week(tt: Timetable, teacher: str) -> TeacherWeek:
    slots: dict[tuple[int, int], list[Lesson]] = defaultdict(list)
    for l in tt.lessons:
        if l.teacher == teacher:
            slots[(l.day, l.period)].append(l)
    flat = [ls[0] for ls in slots.values()]          # jedna lekcja na slot do statystyk
    rooms = Counter(l.room for l in flat if l.room)
    classes = Counter(l.cls for l in flat if l.cls)
    subjects = Counter(l.subject for l in flat if l.subject)
    return TeacherWeek(
        teacher=teacher,
        slots=dict(slots),
        hours=len(slots),
        rooms=sorted(rooms.items(), key=lambda kv: (-kv[1], sort_key(kv[0]))),
        classes=classes.most_common(),
        subjects=subjects.most_common(),
    )


def hours_by_teacher(tt: Timetable) -> dict[str, int]:
    """Nauczyciel -> liczba lekcji w tygodniu (także ci bez lekcji: 0)."""
    seen: dict[str, set] = {t: set() for t in tt.teachers}
    for l in tt.lessons:
        seen.setdefault(l.teacher, set()).add((l.day, l.period))
    return {t: len(s) for t, s in seen.items() if t}
