"""Mój plan (moje wizyty w salach) i moje godziny pracy.

Arkusze w zasoby.xlsx:
    Mój plan       — wpisy: co, gdzie, kiedy (co tydzień albo jednorazowo), lekcje od–do
    Godziny pracy  — Dzień | Od | Do (kilka wierszy na dzień = kilka przedziałów)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Timetable
    from .sprzet import Inventory

SHEET_PLAN, SHEET_HOURS = "Mój plan", "Godziny pracy"
CO_TYDZIEN, JEDNORAZOWO = "co tydzień", "jednorazowo"
DAY_NAMES_PL = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]

ENTRY_COLUMNS = [("id", "ID"), ("tytul", "Co"), ("sala", "Sala"), ("powtarzanie", "Powtarzanie"),
                 ("dzien", "Dzień tygodnia"), ("data", "Data"), ("od", "Lekcja od"), ("do", "Lekcja do"),
                 ("zadanie", "Zadanie"), ("uwagi", "Uwagi")]


@dataclass
class Entry:
    id: str
    tytul: str
    sala: str = ""
    powtarzanie: str = CO_TYDZIEN
    dzien: int | None = None          # 0 = poniedziałek (dla „co tydzień”)
    data: str = ""                    # RRRR-MM-DD (dla „jednorazowo”)
    od: int = 1
    do: int = 1
    zadanie: str = ""                 # ID zadania (opcjonalnie)
    uwagi: str = ""

    @property
    def weekday(self) -> int | None:
        if self.powtarzanie == JEDNORAZOWO and self.data:
            try:
                return date.fromisoformat(self.data[:10]).weekday()
            except ValueError:
                return None
        return self.dzien

    def occurs_on(self, d: date) -> bool:
        if self.powtarzanie == JEDNORAZOWO:
            return self.data[:10] == d.isoformat()
        return self.dzien == d.weekday()

    def periods(self) -> range:
        lo, hi = sorted((int(self.od), int(self.do)))
        return range(lo, hi + 1)

    def when_label(self) -> str:
        if self.powtarzanie == JEDNORAZOWO:
            return self.data
        return f"co {DAY_NAMES_PL[self.dzien]}" if self.dzien is not None else "?"


# --- godziny pracy ---------------------------------------------------------------------
def _hm(s: str) -> tuple[int, int] | None:
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", str(s))
    return (int(m.group(1)), int(m.group(2))) if m else None


@dataclass
class WorkHours:
    days: dict[int, list[tuple[str, str]]] = field(default_factory=dict)   # dzień -> [(od, do)]

    @property
    def defined(self) -> bool:
        return any(self.days.values())

    def text(self, day: int) -> str:
        return ", ".join(f"{a}-{b}" for a, b in self.days.get(day, []))

    def set_text(self, day: int, text: str) -> str | None:
        """'7:30-15:30, 16:00-18:00' -> przedziały. Zwraca błąd albo None."""
        out = []
        for part in [p for p in re.split(r"[,;]", text or "") if p.strip()]:
            m = re.match(r"^\s*(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})\s*$", part)
            if not m:
                return f"Nie rozumiem „{part.strip()}” — wpisz np. 7:30-15:30"
            a, b = m.group(1).replace(".", ":"), m.group(2).replace(".", ":")
            if _hm(a) >= _hm(b):
                return f"„{part.strip()}”: koniec musi być po początku"
            out.append((a, b))
        self.days[day] = out
        return None

    def covers(self, day: int, start: str, end: str) -> bool:
        """Czy odcinek start–end mieści się w godzinach pracy tego dnia."""
        s, e = _hm(start), _hm(end)
        return any(_hm(a) <= s and e <= _hm(b) for a, b in self.days.get(day, []))

    def lesson_in_hours(self, tt: "Timetable", day: int, nr: int) -> bool:
        p = tt.period_by_nr.get(nr)
        if not p or not self.defined:
            return True
        return self.covers(day, p.start, p.end)


def split_window_by_hours(tt: "Timetable", wh: WorkHours, day: int, first: int, last: int) -> list[tuple[int, int, bool]]:
    """Dzieli okno lekcji first..last na odcinki (od, do, w_godzinach_pracy)."""
    out: list[list] = []
    for nr in range(first, last + 1):
        inside = wh.lesson_in_hours(tt, day, nr)
        if out and out[-1][2] == inside and out[-1][1] == nr - 1:
            out[-1][1] = nr
        else:
            out.append([nr, nr, inside])
    return [tuple(x) for x in out]


HOURS_OFF, HOURS_SHOW, HOURS_ONLY = "off", "show", "only"


def free_segments(tt: "Timetable", wh: WorkHours, room: str, day: int, lo: int, hi: int,
                  min_len: int, mode: str = HOURS_OFF) -> list[tuple[int, int, bool]]:
    """Wolne odcinki sali w dniu: [(od, do, w_godzinach_pracy)].

    HOURS_OFF  — godziny pracy pomijamy; okno musi mieć min_len lekcji.
    HOURS_SHOW — jak wyżej, ale okno dzielimy na część w godzinach i 🌙 po godzinach.
    HOURS_ONLY — zostają tylko części w godzinach pracy i to one muszą mieć min_len lekcji.
    """
    from .wolne import free_windows
    ws = free_windows(tt, room, day, lo, hi)
    use_hours = wh.defined and mode != HOURS_OFF
    out: list[tuple[int, int, bool]] = []
    for w in ws:
        if mode == HOURS_ONLY and use_hours:
            out += [s for s in split_window_by_hours(tt, wh, day, w.first, w.last)
                    if s[2] and s[1] - s[0] + 1 >= min_len]
        elif w.length >= min_len:
            out += split_window_by_hours(tt, wh, day, w.first, w.last) if use_hours else [(w.first, w.last, True)]
    return out


# --- kolizje -----------------------------------------------------------------------------
def conflicts(tt: "Timetable | None", e: Entry) -> list[tuple[int, list]]:
    """Lekcje w sali wpisu w jego czasie: [(nr_lekcji, [Lesson…])]."""
    from .sale import base_room
    day = e.weekday
    if not tt or day is None or not e.sala:
        return []
    room = base_room(e.sala)
    out = []
    for nr in e.periods():
        ls = tt.lessons_at(room, day, nr)
        if ls:
            out.append((nr, ls))
    return out


def week_dates(ref: date) -> list[date]:
    monday = ref - timedelta(days=ref.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def next_id(existing) -> str:
    nums = [int(m.group(1)) for x in existing if (m := re.match(r"P(\d+)$", str(x)))]
    return f"P{max(nums, default=0) + 1}"


# --- odczyt / zapis ----------------------------------------------------------------------
def load(wb, rows_fn) -> tuple[list[Entry], WorkHours]:
    entries: list[Entry] = []
    if SHEET_PLAN in wb.sheetnames:
        by_h = {h: a for a, h in ENTRY_COLUMNS}
        for row in rows_fn(wb[SHEET_PLAN]):
            kw = {}
            for h, v in row.items():
                a = by_h.get(h)
                if not a:
                    continue
                if isinstance(v, (datetime, date)):
                    v = v.strftime("%Y-%m-%d")
                kw[a] = v
            if not kw.get("id"):
                continue
            d = kw.get("dzien")
            if isinstance(d, str) and d.strip().lower() in DAY_NAMES_PL:
                d = DAY_NAMES_PL.index(d.strip().lower())
            try:
                kw["dzien"] = int(d) if d not in (None, "") else None
            except (TypeError, ValueError):
                kw["dzien"] = None
            for k in ("od", "do"):
                try:
                    kw[k] = int(float(kw.get(k) or 1))
                except (TypeError, ValueError):
                    kw[k] = 1
            for k in ("id", "tytul", "sala", "powtarzanie", "data", "zadanie", "uwagi"):
                kw[k] = "" if kw.get(k) is None else str(kw[k]).strip()
            kw["powtarzanie"] = kw["powtarzanie"] or CO_TYDZIEN
            entries.append(Entry(**kw))
    wh = WorkHours()
    if SHEET_HOURS in wb.sheetnames:
        for row in rows_fn(wb[SHEET_HOURS]):
            d = str(row.get("Dzień") or "").strip().lower()
            if d not in DAY_NAMES_PL:
                continue
            a, b = row.get("Od"), row.get("Do")
            a = a.strftime("%H:%M") if hasattr(a, "strftime") else str(a or "").strip()
            b = b.strftime("%H:%M") if hasattr(b, "strftime") else str(b or "").strip()
            if _hm(a) and _hm(b):
                wh.days.setdefault(DAY_NAMES_PL.index(d), []).append((a, b))
    return entries, wh


def write(wb, inv: "Inventory", style_fn) -> None:
    ws = wb.create_sheet(SHEET_PLAN)
    ws.append([h for _, h in ENTRY_COLUMNS])
    for e in inv.my_plan:
        vals = []
        for a, _ in ENTRY_COLUMNS:
            v = getattr(e, a)
            if a == "dzien":
                v = DAY_NAMES_PL[v] if v is not None else ""
            vals.append(v)
        ws.append(vals)
    style_fn(ws, widths={"Co": 36, "Uwagi": 30, "Dzień tygodnia": 14, "Powtarzanie": 13})
    wh = wb.create_sheet(SHEET_HOURS)
    wh.append(["Dzień", "Od", "Do"])
    for d in sorted(inv.work_hours.days):
        for a, b in inv.work_hours.days[d]:
            wh.append([DAY_NAMES_PL[d], a, b])
    style_fn(wh, widths={"Dzień": 14})
