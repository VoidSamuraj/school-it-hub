"""Parser PDF-a z planami nauczycieli wydrukowanego z aSc Plan Lekcji.

Struktura nie jest wpisana na sztywno — z każdej tabeli czytamy:
  * tytuł nad tabelą ("Nauczyciel Nazwisko Imię"),
  * wiersz nagłówka z numerami lekcji i godzinami ("1 / 7:30 - 8:15"),
  * etykiety dni w pierwszej kolumnie ("Pn", "Wt", ...; wiersz bez etykiety = podzielona komórka
    poprzedniego dnia),
  * komórki: 1. linia małą czcionką "przedmiot sala", większą czcionką klasa, małą — grupa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .model import Lesson, Period, Timetable
from .sale import looks_like_room, normalize_room

DAY_LABELS = {
    "pn": 0, "pon": 0,
    "wt": 1, "wto": 1,
    "śr": 2, "sr": 2, "śro": 2,
    "czw": 3, "cz": 3,
    "pt": 4, "pi": 4, "pią": 4, "pia": 4,
    "so": 5, "sob": 5,
    "nd": 6, "nie": 6,
}
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")
GENERATED_RE = re.compile(r"wygenerowany:\s*([\d.]+)")
TITLE_MIN_SIZE = 12.0


@dataclass
class ParseReport:
    pages: int = 0
    tables: int = 0
    teachers: list[str] = field(default_factory=list)
    lessons: int = 0
    lessons_without_room: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Plan wygląda wiarygodnie: są lekcje, mało problemów."""
        return self.lessons > 0 and len(self.warnings) <= max(5, self.lessons * 0.05)


class PlanParseError(Exception):
    pass


def _words_in(words: list[dict], bbox: tuple[float, float, float, float]) -> list[dict]:
    x0, top, x1, bottom = bbox
    out = []
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2
        cy = (w["top"] + w["bottom"]) / 2
        if x0 <= cx < x1 and top <= cy < bottom:
            out.append(w)
    return out


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])))


def parse_pdf(path: str | Path) -> tuple[Timetable, ParseReport]:
    path = Path(path)
    report = ParseReport()
    periods: dict[int, Period] = {}
    lessons: set[Lesson] = set()
    days_seen: set[int] = set()
    generated = ""

    try:
        pdf = pdfplumber.open(path)
    except Exception as e:  # noqa: BLE001
        raise PlanParseError(f"Nie da się otworzyć PDF-a: {e}") from e

    with pdf:
        report.pages = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(extra_attrs=["size"])
            if not generated:
                for w in words:
                    m = GENERATED_RE.search(w["text"])
                    if m:
                        generated = m.group(1)
                        break
            for table in page.find_tables():
                _parse_table(pno, table, words, periods, lessons, days_seen, report)

    if not lessons:
        raise PlanParseError(
            "Nie znaleziono żadnych lekcji. Czy to PDF z planami nauczycieli wydrukowany z aSc?"
        )

    ordered = sorted(lessons, key=lambda l: (l.day, l.period, l.room or "", l.teacher))
    report.lessons = len(ordered)
    report.lessons_without_room = sum(1 for l in ordered if not l.room)
    tt = Timetable(
        periods=[periods[k] for k in sorted(periods)],
        days=sorted(days_seen),
        lessons=ordered,
        source=path.name,
        generated=generated,
        teachers=list(dict.fromkeys(report.teachers)),
    )
    return tt, report


def _parse_table(pno, table, words, periods, lessons, days_seen, report: ParseReport) -> None:
    x0, top, x1, _ = table.bbox
    rows = table.rows
    hi = None
    # wiersz nagłówka = ten, w którym są godziny lekcji
    for i, row in enumerate(rows):
        n = sum(1 for c in row.cells if c is not None and TIME_RE.search(_text(_words_in(words, c))))
        if n >= 2:
            hi = i
            break
    if hi is None:
        return  # to nie jest tabela planu

    report.tables += 1

    # tytuł nad tabelą
    title_words = [
        w for w in words
        if w["size"] >= TITLE_MIN_SIZE and x0 - 3 <= w["x0"] <= x1 and top - 35 <= w["top"] <= top + 1
    ]
    title = _text(sorted(title_words, key=lambda w: w["x0"]))
    kind, _, name = title.partition(" ")
    if kind.lower() != "nauczyciel":
        report.warnings.append(
            f"str. {pno}: tabela „{title or '?'}” — oczekiwano planu nauczyciela, pomijam"
        )
        return
    teacher = name.strip()
    report.teachers.append(teacher)

    # kolumny lekcji
    columns: list[tuple[float, float, int]] = []
    for c in rows[hi].cells[1:]:
        if c is None:
            continue
        txt = _text(_words_in(words, c))
        m_time = TIME_RE.search(txt)
        m_nr = re.match(r"\s*(\d{1,2})\b", txt)
        if not (m_time and m_nr):
            continue
        nr = int(m_nr.group(1))
        p = Period(nr, m_time.group(1), m_time.group(2))
        if nr in periods and periods[nr] != p:
            report.warnings.append(f"str. {pno}: lekcja {nr} ma różne godziny ({periods[nr].label} / {p.label})")
        periods.setdefault(nr, p)
        columns.append((c[0], c[2], nr))
    if not columns:
        report.warnings.append(f"str. {pno}: {teacher} — brak kolumn lekcji")
        return

    day = None
    for row in rows[hi + 1:]:
        cells = row.cells
        label = cells[0]
        if label is not None:
            key = _text(_words_in(words, label)).strip().lower()
            if key in DAY_LABELS:
                day = DAY_LABELS[key]
            elif key:
                report.warnings.append(f"str. {pno}: {teacher} — nieznana etykieta dnia „{key}”")
                day = None
        if day is None:
            continue
        days_seen.add(day)

        for c in cells[1:]:
            if c is None:
                continue
            inside = _words_in(words, c)
            if not inside:
                continue
            covered = [nr for (cx0, cx1, nr) in columns if c[0] - 1 <= (cx0 + cx1) / 2 <= c[2] + 1]
            if not covered:
                continue
            _parse_cell(pno, teacher, day, covered, inside, lessons, report)


def _parse_cell(pno, teacher, day, covered, inside, lessons, report: ParseReport) -> None:
    first_top = min(w["top"] for w in inside)
    line1 = sorted([w for w in inside if abs(w["top"] - first_top) < 1.5], key=lambda w: w["x0"])
    rest = [w for w in inside if abs(w["top"] - first_top) >= 1.5]
    small_size = max(w["size"] for w in line1)
    cls_words = [w for w in rest if w["size"] > small_size * 1.3]
    grp_words = [w for w in rest if w["size"] <= small_size * 1.3]

    tokens = [w["text"] for w in line1]
    room = None
    if len(tokens) >= 2 and looks_like_room(tokens[-1]):
        room = normalize_room(tokens[-1])
        subject = " ".join(tokens[:-1])
    else:
        subject = " ".join(tokens)
        report.warnings.append(
            f"str. {pno}: {teacher}, dzień {day + 1}, lekcja {covered[0]} — nie rozpoznano sali w „{_text(inside)}”"
        )

    for nr in covered:
        lessons.add(Lesson(
            day=day, period=nr, room=room, subject=subject,
            cls=_text(cls_words), group=_text(grp_words), teacher=teacher,
        ))
