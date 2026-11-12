"""Zadania: pojedyncze (w sali / przy sprzęcie) i globalne (to samo na wielu komputerach lub w wielu salach).

Arkusze w zasoby.xlsx:
    Zadania           — pojedyncze zadania
    Zadania globalne  — zadanie + zakres (np. wszystkie komputery w salach IT)
    Postęp zadań      — odhaczenia: zadanie globalne × cel (sprzęt albo sala)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sprzet import Inventory, Item

SHEET_TASKS, SHEET_GLOBAL, SHEET_PROGRESS = "Zadania", "Zadania globalne", "Postęp zadań"

DO_ZROBIENIA, W_TRAKCIE, ZROBIONE = "do zrobienia", "w trakcie", "zrobione"
TASK_STATUSES = [DO_ZROBIENIA, W_TRAKCIE, ZROBIONE]
PRIORITIES = ["niski", "normalny", "pilny"]

CEL_SPRZET, CEL_SALE = "sprzęt", "sale"
ZAKRES_WSZYSTKIE, ZAKRES_IT = "wszystkie", "sale IT"

TASK_COLUMNS = [("id", "ID"), ("tytul", "Tytuł"), ("sala", "Sala"), ("sprzet", "Sprzęt"),
                ("termin", "Termin"), ("priorytet", "Priorytet"), ("status", "Status"),
                ("opis", "Opis"), ("utworzono", "Utworzono"), ("zrobiono", "Zrobiono")]
GLOBAL_COLUMNS = [("id", "ID"), ("tytul", "Tytuł"), ("cel", "Cel"), ("kategorie", "Kategorie"),
                  ("sale", "Sale"), ("opis", "Opis"), ("utworzono", "Utworzono"), ("zamkniete", "Zamknięte")]
PROGRESS_COLUMNS = [("zadanie", "Zadanie"), ("cel", "Cel"), ("data", "Data"), ("uwagi", "Uwagi")]


@dataclass
class Task:
    id: str
    tytul: str
    sala: str = ""
    sprzet: str = ""          # ID sprzętu (opcjonalnie)
    termin: str = ""          # RRRR-MM-DD
    priorytet: str = "normalny"
    status: str = DO_ZROBIENIA
    opis: str = ""
    utworzono: str = ""
    zrobiono: str = ""

    @property
    def done(self) -> bool:
        return self.status == ZROBIONE

    def overdue(self, today: date | None = None) -> bool:
        if self.done or not self.termin:
            return False
        try:
            return date.fromisoformat(self.termin[:10]) < (today or date.today())
        except ValueError:
            return False


@dataclass
class GlobalTask:
    id: str
    tytul: str
    cel: str = CEL_SPRZET                # "sprzęt" albo "sale"
    kategorie: str = "Komputer, Laptop, Chromebook"   # dla celu "sprzęt"
    sale: str = ZAKRES_WSZYSTKIE         # "wszystkie", "sale IT" albo lista: "11W, 24, 33"
    opis: str = ""
    utworzono: str = ""
    zamkniete: str = ""                  # "tak" = zadanie zakończone (ukryte z aktywnych)

    @property
    def category_set(self) -> set[str]:
        return {c.strip() for c in re.split(r"[,;]", self.kategorie) if c.strip()}

    @property
    def room_list(self) -> list[str]:
        from .sale import normalize_room
        if self.sale.strip().lower() in (ZAKRES_WSZYSTKIE, ZAKRES_IT.lower(), ""):
            return []
        return [normalize_room(s) for s in re.split(r"[,;]", self.sale) if s.strip()]

    @property
    def active(self) -> bool:
        return self.zamkniete.strip().lower() not in ("tak", "1", "true")

    def scope_label(self) -> str:
        where = self.sale if self.sale else ZAKRES_WSZYSTKIE
        if self.cel == CEL_SALE:
            return f"sale: {where}"
        return f"{self.kategorie or 'cały sprzęt'} · {where}"


@dataclass
class Progress:
    zadanie: str
    cel: str          # ID sprzętu albo nazwa sali
    data: str = ""
    uwagi: str = ""


# --- zakres i postęp -----------------------------------------------------------------
def _room_ok(inv: "Inventory", g: GlobalTask, room: str) -> bool:
    from .sale import base_room
    sale = g.sale.strip().lower()
    if not room:
        return False
    if room.endswith("-ZAPL"):
        return False
    if sale in (ZAKRES_WSZYSTKIE, ""):
        return True
    if sale == ZAKRES_IT.lower():
        return inv.room_kind(room) == "it"
    return base_room(room) in g.room_list


def targets(inv: "Inventory", g: GlobalTask, plan_rooms: list[str] | None = None) -> list:
    """Cele zadania: lista Item (cel=sprzęt) albo nazw sal (cel=sale)."""
    from .sale import sort_key
    from .sprzet import WYCOFANY
    if g.cel == CEL_SALE:
        rooms = set(plan_rooms or []) | {r.get("Sala") for r in inv.rooms if r.get("Sala")}
        rooms |= {i.sala for i in inv.items.values() if i.sala}
        rooms = {str(r) for r in rooms if _room_ok(inv, g, str(r)) and _is_real_room(str(r))}
        return sorted(rooms, key=sort_key)
    cats = g.category_set
    out = [i for i in inv.items.values()
           if i.status != WYCOFANY and (not cats or i.kategoria in cats) and _room_ok(inv, g, i.sala)]
    out.sort(key=lambda i: (sort_key(i.sala), i.kategoria, i.id))
    return out


def _is_real_room(r: str) -> bool:
    from .sale import is_room
    return is_room(r)


def target_key(t) -> str:
    return t if isinstance(t, str) else t.id


def target_room(t) -> str:
    return t if isinstance(t, str) else t.sala


def done_map(inv: "Inventory", task_id: str) -> dict[str, Progress]:
    return {p.cel: p for p in inv.progress if p.zadanie == task_id}


def set_done(inv: "Inventory", task_id: str, target: str, done: bool, uwagi: str = "") -> None:
    inv.progress = [p for p in inv.progress if not (p.zadanie == task_id and p.cel == target)]
    if done:
        inv.progress.append(Progress(task_id, target, datetime.now().strftime("%Y-%m-%d %H:%M"), uwagi))


@dataclass
class RoomProgress:
    room: str
    done: int
    total: int


def progress_summary(inv: "Inventory", g: GlobalTask, plan_rooms=None) -> tuple[int, int, list[RoomProgress]]:
    ts = targets(inv, g, plan_rooms)
    dm = done_map(inv, g.id)
    by_room: dict[str, list[int]] = {}
    for t in ts:
        r = target_room(t)
        d = by_room.setdefault(r, [0, 0])
        d[1] += 1
        d[0] += target_key(t) in dm
    rooms = [RoomProgress(r, d, n) for r, (d, n) in by_room.items()]
    return sum(r.done for r in rooms), len(ts), rooms


def next_id(prefix: str, existing) -> str:
    nums = [int(m.group(1)) for x in existing if (m := re.match(rf"{prefix}(\d+)$", str(x)))]
    return f"{prefix}{max(nums, default=0) + 1}"


# --- odczyt / zapis -----------------------------------------------------------------
def _load(ws, rows_fn, cls, columns):
    by_h = {h: a for a, h in columns}
    out = []
    for row in rows_fn(ws):
        kw = {}
        for h, v in row.items():
            a = by_h.get(h)
            if not a:
                continue
            if isinstance(v, (datetime, date)):
                v = v.strftime("%Y-%m-%d")
            kw[a] = "" if v is None else str(v).strip()
        first = columns[0][0]
        if kw.get(first):
            out.append(cls(**kw))
    return out


def load_all(wb, rows_fn) -> tuple[list[Task], list[GlobalTask], list[Progress]]:
    tasks = _load(wb[SHEET_TASKS], rows_fn, Task, TASK_COLUMNS) if SHEET_TASKS in wb.sheetnames else []
    gl = _load(wb[SHEET_GLOBAL], rows_fn, GlobalTask, GLOBAL_COLUMNS) if SHEET_GLOBAL in wb.sheetnames else []
    pr = _load(wb[SHEET_PROGRESS], rows_fn, Progress, PROGRESS_COLUMNS) if SHEET_PROGRESS in wb.sheetnames else []
    return tasks, gl, pr


def write_all(wb, inv: "Inventory", style_fn, validation_fn) -> None:
    ws = wb.create_sheet(SHEET_TASKS)
    ws.append([h for _, h in TASK_COLUMNS])
    for t in inv.tasks:
        ws.append([getattr(t, a) for a, _ in TASK_COLUMNS])
    style_fn(ws, widths={"Tytuł": 40, "Opis": 40, "Sprzęt": 16, "Status": 13})
    validation_fn(ws, 7, TASK_STATUSES, len(inv.tasks))
    validation_fn(ws, 6, PRIORITIES, len(inv.tasks))

    wg = wb.create_sheet(SHEET_GLOBAL)
    wg.append([h for _, h in GLOBAL_COLUMNS])
    for g in inv.global_tasks:
        wg.append([getattr(g, a) for a, _ in GLOBAL_COLUMNS])
    style_fn(wg, widths={"Tytuł": 40, "Kategorie": 30, "Sale": 22, "Opis": 40})

    wp = wb.create_sheet(SHEET_PROGRESS)
    wp.append([h for _, h in PROGRESS_COLUMNS])
    for p in inv.progress:
        wp.append([getattr(p, a) for a, _ in PROGRESS_COLUMNS])
    style_fn(wp, widths={"Cel": 18, "Data": 17, "Uwagi": 40})
