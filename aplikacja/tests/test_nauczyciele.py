from wolnesale.core.model import Lesson, Period, Timetable
from wolnesale.core.nauczyciele import hours_by_teacher, teacher_week


def _tt():
    per = [Period(i, f"{7 + i}:00", f"{7 + i}:45") for i in range(1, 8)]
    L = lambda d, p, room, t, cls="1A", grp="": Lesson(d, p, room, "mat", cls, grp, t)
    lessons = [L(0, 1, "12", "Nowak Jan"), L(0, 4, "12", "Nowak Jan"), L(0, 5, "14", "Nowak Jan", "2B"),
               L(1, 2, "12", "Nowak Jan", "1A", "gr1"), L(1, 2, "12", "Nowak Jan", "1A", "gr2"),
               L(0, 1, "14", "Kowalska Ewa")]
    return Timetable(per, [0, 1, 2, 3, 4], lessons, teachers=["Nowak Jan", "Kowalska Ewa", "Zieliński Adam"])


def test_teacher_week():
    w = teacher_week(_tt(), "Nowak Jan")
    assert w.hours == 4                       # dwie grupy w tym samym slocie = jedna lekcja
    assert w.day_range(0) == (1, 5)
    assert w.gaps(0) == [2, 3]
    assert w.gaps(1) == [] and w.day_range(2) is None
    assert w.rooms[0] == ("12", 3)
    assert dict(w.classes) == {"1A": 3, "2B": 1}
    assert len(w.slots[(1, 2)]) == 2


def test_hours_by_teacher():
    h = hours_by_teacher(_tt())
    assert h == {"Nowak Jan": 4, "Kowalska Ewa": 1, "Zieliński Adam": 0}


def test_atrybuty_teraz():
    from wolnesale.web.theme import tattr
    tt = _tt()
    a = tattr(tt, 0, 2)
    assert 'data-d="0"' in a and 'data-s="540"' in a and 'data-e="585"' in a and 'data-prev="525"' in a
    assert "data-prev" not in tattr(tt, "*", 1)
