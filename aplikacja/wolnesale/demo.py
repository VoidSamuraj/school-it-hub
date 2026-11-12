"""Dane demonstracyjne — w pełni fikcyjne (bez nazwisk i prawdziwych numerów inwentarzowych).

Użycie (w folderze aplikacja):
    python -m wolnesale.demo ../demo-dane          # tworzy folder z danymi demo
    WOLNESALE_DANE=../demo-dane python -m wolnesale  # uruchamia program na danych demo
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .core.ewidencja import merge
from .core.model import Lesson, Period, Timetable
from .core.moj_plan import WorkHours
from .core.plany import PlanStore
from .core.sprzet import NIEPEWNA, SERWIS, Inventory, Item
from .core.zadania import GlobalTask, Task, set_done, targets
from .core.zaplecze import Material, stock_change
from .ustawienia import Paths

PERIODS = [Period(1, "7:30", "8:15"), Period(2, "8:20", "9:05"), Period(3, "9:10", "9:55"),
           Period(4, "10:00", "10:45"), Period(5, "10:50", "11:35"), Period(6, "11:50", "12:35"),
           Period(7, "12:40", "13:25"), Period(8, "13:30", "14:15"), Period(9, "14:20", "15:05"),
           Period(10, "15:20", "16:05")]
ROOMS = ["1", "2", "3", "4", "12", "14", "15", "24", "24A", "33", "36", "37",
         "5W", "8W", "10W", "11W", "12W", "20W", "26W", "2B", "6B", "D1", "M1"]
SUBJECTS = ["mat", "inf", "jpol", "jang", "fiz", "his", "geo", "bio", "chem", "wf", "pracownia", "elektr"]
CLASSES = ["1A", "1B", "2A", "2TI", "3TI", "3TE", "4TM", "4TB", "5TI"]


def make_timetable(rnd: random.Random) -> Timetable:
    teachers = [f"Nauczyciel {i:02d}" for i in range(1, 25)]
    lessons = []
    for room in ROOMS:
        busy = rnd.uniform(0.35, 0.85)
        for d in range(5):
            last = 10 if d < 4 else 7
            for p in range(1, last + 1):
                if rnd.random() < busy:
                    subj = "wf" if room in ("D1", "M1") else rnd.choice(SUBJECTS)
                    lessons.append(Lesson(d, p, room, subj, rnd.choice(CLASSES),
                                          rnd.choice(["", "", "gr1", "gr2"]), rnd.choice(teachers)))
    return Timetable(PERIODS, [0, 1, 2, 3, 4], lessons, source="plan-demo.pdf", generated="01.09.2026",
                     teachers=teachers)


def make_items(rnd: random.Random) -> list[Item]:
    items: list[Item] = []
    n = 0

    def add(kat, nazwa, sala, k=1, **kw):
        nonlocal n
        for _ in range(k):
            n += 1
            items.append(Item(id=f"DEMO/{n:04d}", inv=f"DEMO/{n:04d}", kategoria=kat, nazwa=nazwa, sala=sala,
                              sala_ewid=kw.pop("ewid", sala), opis_ewid=sala, projekt=kw.pop("projekt", "PŚT"),
                              data="2024-09-01", wartosc=kw.pop("cena", 2500.0), **kw))

    add("Komputer", "Komputer Dell OptiPlex 7010", "11W", 16)
    add("Komputer", "Komputer Lenovo ThinkCentre M70q", "24", 20, projekt="KPO")
    add("Komputer", "Komputer Dell OptiPlex 3080", "33", 18)
    add("Laptop", "Laptop HP ProBook 450 G9", "4", 16, projekt="KPO")
    add("Chromebook", "Chromebook Acer 314", "12", 15, projekt="KPO")
    add("Laptop", "Laptop HP ProBook 450 G9", "36-ZAPL", 24, projekt="KPO")
    for r in ["1", "2", "3", "14", "15", "37", "5W", "8W", "2B"]:
        add("Komputer", "Komputer Dell OptiPlex 3000 (nauczyciel)", r)
        add("Projektor", "Projektor Epson EB-W51", r, cena=2100.0)
    for r in ["11W", "24", "33", "4", "12"]:
        add("Tablica / monitor interaktywny", "Monitor interaktywny 65\"", r, cena=7800.0)
    add("Drukarka", "Drukarka HP LaserJet Pro M404dn", "11W")
    add("Drukarka", "Drukarka HP LaserJet Pro M404dn", "16")
    add("Urządzenie wielofunkcyjne", "Urządzenie wielofunkcyjne Brother DCP-L5500DN", "24", 1)
    add("Urządzenie wielofunkcyjne", "Urządzenie wielofunkcyjne Brother DCP-L5500DN", "5W")
    add("Urządzenie wielofunkcyjne", "Urządzenie wielofunkcyjne Brother DCP-L5500DN", "12W")
    add("Urządzenie wielofunkcyjne", "Brother MFC-L8690CDW (kolor)", "20")
    add("Urządzenie wielofunkcyjne", "Brother MFC-L8690CDW (kolor)", "26W")
    add("Kserokopiarka", "Kserokopiarka Canon iR 2520", "1W")
    add("Kserokopiarka", "Kserokopiarka Canon iR 2520", "4W")
    add("Drukarka", "Drukarka Brother MFC-T920DW InkBenefit", "37")
    add("Monitor", "Monitor Dell P2422H", "11W", 4)
    # kilka „życiowych” przypadków
    items[3].sala, items[3].pewnosc = "10W", NIEPEWNA            # ktoś przeniósł
    items[40].status = SERWIS
    items[60].sala, items[60].sala_ewid = "", "16"               # nie wiadomo, gdzie jest
    for it in items[:5]:
        it.sprawdzono = "2026-09-15"
    return items


def build(root: Path, seed: int = 7) -> Paths:
    rnd = random.Random(seed)
    p = Paths(Path(root)).ensure()
    tt = make_timetable(rnd)
    pdf = p.zrodla_plany / "plan-demo.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% plik demonstracyjny\n")
    PlanStore(p.plan, p.kopie_plany, p.zrodla_plany).activate(tt, pdf)

    inv = Inventory(p.zasoby)
    merge(inv, make_items(rnd))
    inv.ensure_rooms(tt.rooms + inv.locations())

    inv.materials = {
        "CF259X": Material("CF259X", "Toner HP 59X", "toner", "czarny", "M404", 2, 2, "16 – szafa"),
        "TN-3480": Material("TN-3480", "Toner Brother TN-3480", "toner", "czarny", "DCP-L5500", 1, 2, "16 – szafa"),
        "TN-423BK": Material("TN-423BK", "Toner Brother TN-423 czarny", "toner", "czarny", "MFC-L8690", 2, 1),
        "TN-423C": Material("TN-423C", "Toner Brother TN-423 cyan", "toner", "cyan", "MFC-L8690", 0, 1),
        "TN-423M": Material("TN-423M", "Toner Brother TN-423 magenta", "toner", "magenta", "MFC-L8690", 1, 1),
        "C-EXV33": Material("C-EXV33", "Toner Canon C-EXV33", "toner", "czarny", "2520", 3, 1),
        "BT5000": Material("BT5000", "Tusz Brother BT5000 (zestaw)", "tusz", "kolor (zestaw)", "MFC-T920", 1, 1),
    }
    inv.model_schemes.update({"M404DN": "tylko czarny", "DCP-L5500DN": "tylko czarny",
                              "MFC-L8690CDW": "CMYK (4 osobne)", "2520": "tylko czarny",
                              "MFC-T920DW": "czarny + kolor"})
    start = datetime(2026, 3, 1, 10, 0)
    for kod, every, rooms in (("TN-3480", 40, ["24", "5W", "12W"]), ("CF259X", 55, ["11W", "16"]),
                              ("C-EXV33", 70, ["1W", "4W"])):
        t = start
        i = 0
        while t.date() < date(2026, 11, 1):
            stock_change(inv, kod, -1, rooms[i % len(rooms)], when=t, change_stock=False)
            t += timedelta(days=every + rnd.randint(-8, 8))
            i += 1

    inv.tasks = [
        Task("Z1", "Wymienić toner w drukarce", "24", termin="2026-11-10", priorytet="pilny"),
        Task("Z2", "Podłączyć nowy monitor interaktywny", "33", termin="2026-11-20"),
        Task("Z3", "Sprawdzić projektor — gaśnie po 10 min", "14", priorytet="pilny"),
        Task("Z4", "Uporządkować kable w pracowni", "11W", status="w trakcie"),
        Task("Z5", "Inwentaryzacja zaplecza", "36", status="zrobione", zrobiono="2026-10-02 12:00"),
    ]
    g1 = GlobalTask("G1", "Aktualizacja Windows 11 24H2", kategorie="Komputer, Laptop, Chromebook", sale="sale IT")
    g2 = GlobalTask("G2", "Sprawdzić projektor i nagłośnienie", cel="sale", kategorie="", sale="wszystkie")
    inv.global_tasks = [g1, g2]
    for t in targets(inv, g1)[:41]:
        set_done(inv, "G1", t.id, True)
    for r in targets(inv, g2, tt.rooms)[:9]:
        set_done(inv, "G2", r, True)

    wh = WorkHours()
    for d in range(4):
        wh.set_text(d, "7:30-15:30")
    wh.set_text(4, "7:30-13:00")
    inv.work_hours = wh
    inv.save()
    return p


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo-dane")
    paths = build(target)
    print(f"Dane demo: {paths.root.resolve()}")
