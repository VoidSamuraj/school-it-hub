from datetime import date

from wolnesale.core.model import Lesson, Period, Timetable
from wolnesale.core.moj_plan import (JEDNORAZOWO, Entry, WorkHours, conflicts, split_window_by_hours,
                                     week_dates)
from wolnesale.core.sprzet import Inventory

PERIODS = [Period(1, "7:30", "8:15"), Period(2, "8:20", "9:05"), Period(3, "9:10", "9:55"),
           Period(4, "10:00", "10:45"), Period(5, "14:20", "15:05"), Period(6, "15:20", "16:05")]


def tt_with(lessons):
    return Timetable(periods=PERIODS, days=[0, 1, 2, 3, 4], lessons=lessons)


def test_work_hours_parse_and_cover():
    wh = WorkHours()
    assert wh.set_text(0, "8:00-15:00") is None
    assert wh.set_text(1, "7:30-12:00, 13.00-15:30") is None
    assert wh.set_text(2, "bzdura") and wh.set_text(2, "15:00-8:00")
    assert wh.text(1) == "7:30-12:00, 13:00-15:30"
    tt = tt_with([])
    assert not wh.lesson_in_hours(tt, 0, 1)         # 7:30 przed 8:00
    assert wh.lesson_in_hours(tt, 0, 2)
    assert wh.lesson_in_hours(tt, 1, 5) and not wh.lesson_in_hours(tt, 1, 6)
    # pon. 8:00-15:00: lekcja 5 kończy się 15:05 -> już po godzinach
    assert split_window_by_hours(tt, wh, 0, 1, 6) == [(1, 1, False), (2, 4, True), (5, 6, False)]
    assert WorkHours().lesson_in_hours(tt, 0, 1)     # brak godzin = wszystko „w godzinach”


def test_free_segments_modes():
    from wolnesale.core.moj_plan import HOURS_OFF, HOURS_ONLY, HOURS_SHOW, free_segments
    # sala wolna na lekcjach 4–6; pracuję do 15:00 -> w godzinach tylko 4 i 5 (6 kończy się 16:05)
    tt = tt_with([Lesson(0, n, "11W", "x", "1a", "", "T") for n in (1, 2, 3)])
    wh = WorkHours()
    wh.set_text(0, "7:30-15:10")
    assert free_segments(tt, wh, "11W", 0, 1, 6, 3, HOURS_OFF) == [(4, 6, True)]
    assert free_segments(tt, wh, "11W", 0, 1, 6, 3, HOURS_SHOW) == [(4, 5, True), (6, 6, False)]
    # tryb 3: po obcięciu do godzin pracy zostają 2 lekcje -> wymóg 3 lekcji niespełniony
    assert free_segments(tt, wh, "11W", 0, 1, 6, 3, HOURS_ONLY) == []
    assert free_segments(tt, wh, "11W", 0, 1, 6, 2, HOURS_ONLY) == [(4, 5, True)]
    # bez zdefiniowanych godzin tryby 2 i 3 działają jak 1
    assert free_segments(tt, WorkHours(), "11W", 0, 1, 6, 3, HOURS_ONLY) == [(4, 6, True)]


def test_entries_and_conflicts():
    tt = tt_with([Lesson(0, 3, "11W", "inf", "2TM", "", "Kowalski")])
    weekly = Entry("P1", "Instalacja", sala="11W", dzien=0, od=2, do=4)
    assert weekly.occurs_on(date(2026, 11, 9)) and not weekly.occurs_on(date(2026, 11, 10))
    assert [nr for nr, _ in conflicts(tt, weekly)] == [3]
    once = Entry("P2", "Serwis", sala="11w", powtarzanie=JEDNORAZOWO, data="2026-11-11", od=1, do=1)
    assert once.weekday == 2 and once.occurs_on(date(2026, 11, 11)) and conflicts(tt, once) == []
    assert week_dates(date(2026, 11, 12))[0] == date(2026, 11, 9)


def test_save_load(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    inv.my_plan = [Entry("P1", "Instalacja", sala="11W", dzien=3, od=2, do=4),
                   Entry("P2", "Serwis", sala="24", powtarzanie=JEDNORAZOWO, data="2026-11-20", od=5, do=6)]
    inv.work_hours.set_text(0, "7:30-15:30")
    inv.work_hours.set_text(4, "8:00-12:00, 13:00-14:00")
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx")
    assert [(e.id, e.dzien, e.od, e.do) for e in back.my_plan] == [("P1", 3, 2, 4), ("P2", None, 5, 6)]
    assert back.my_plan[1].weekday == 4
    assert back.work_hours.text(4) == "8:00-12:00, 13:00-14:00" and back.work_hours.text(0) == "7:30-15:30"
