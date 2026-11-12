"""Spis sprzętu w pliku zasoby.xlsx (arkusze: Sprzęt, Historia, Sale).

Plik da się edytować także w Excelu — czytamy kolumny po nagłówkach, a kolumny dodane
ręcznie (nieznane programowi) są zachowywane przy zapisie.
"""
from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .sale import building, is_room, normalize_room, sort_key

# --- słowniki ---------------------------------------------------------------
PEWNA, NIEPEWNA, NIEZNANA = "pewna", "niepewna", "nieznana"
PEWNOSCI = [PEWNA, NIEPEWNA, NIEZNANA]

OK, SERWIS, WYPOZYCZONY, WYCOFANY = "OK", "serwis", "wypożyczony", "wycofany"
STATUSY = [OK, SERWIS, WYPOZYCZONY, WYCOFANY]

# przypisanie do osoby
NA_STALE, WYPOZYCZENIE = "na stałe", "wypożyczenie"
PRZYDZIALY = [NA_STALE, WYPOZYCZENIE]
POZA_SZKOLA = "Poza szkołą"          # lokalizacja: u osoby w domu / poza budynkiem
LOCATION_EVENTS = {"przeniesienie", "wydanie", "wypożyczenie", "zwrot"}

SHEET_ITEMS, SHEET_HISTORY, SHEET_ROOMS = "Sprzęt", "Historia", "Sale"

# atrybut -> nagłówek kolumny w Excelu
ITEM_COLUMNS: list[tuple[str, str]] = [
    ("id", "ID"),
    ("inv", "Nr inwentarza"),
    ("kategoria", "Kategoria"),
    ("nazwa", "Nazwa"),
    ("projekt", "Projekt"),
    ("data", "Data przyjęcia"),
    ("wartosc", "Wartość"),
    ("sala", "Sala (faktycznie)"),
    ("pewnosc", "Pewność lokalizacji"),
    ("status", "Status"),
    ("uzytkownik", "Użytkownik"),
    ("przydzial", "Przydział"),
    ("zwrot", "Zwrot do"),
    ("sprawdzono", "Sprawdzono"),
    ("uwagi", "Uwagi"),
    ("sala_ewid", "Sala (ewidencja)"),
    ("opis_ewid", "Ewidencja – opis"),
    ("w_ewidencji", "W ewidencji"),
    ("zrodlo", "Źródło"),
]
# pola, które pochodzą z ewidencji (nadpisywane przy ponownym imporcie)
EWID_FIELDS = ["inv", "kategoria", "nazwa", "projekt", "data", "wartosc", "sala_ewid", "opis_ewid",
               "w_ewidencji", "zrodlo"]
# pola prowadzone przeze mnie (import ich nie rusza)
USER_FIELDS = ["sala", "pewnosc", "status", "uzytkownik", "przydzial", "zwrot", "sprawdzono", "uwagi"]

HISTORY_COLUMNS = ["Data", "ID", "Zdarzenie", "Z", "Do", "Opis"]
ROOM_COLUMNS = ["Sala", "Budynek", "Typ", "Stanowiska", "Uwagi"]
# stanowiska komputerowe: stacjonarne + laptopy + chromebooki (tablety nie)
PC_CATEGORIES = {"Komputer", "Laptop", "Chromebook"}
IT_MIN_PCS = 6          # od tylu komputerów sala liczy się jako pracownia IT
KIND_IT, KIND_PC = "it", "pc"
ROOM_TYPES = ["komputerowa", "tylko PC nauczyciela", "zwykła", "gimnastyczna", "warsztat", "zaplecze"]


@dataclass
class Item:
    id: str
    inv: str = ""
    kategoria: str = ""
    nazwa: str = ""
    projekt: str = ""
    data: str = ""
    wartosc: float | None = None
    sala: str = ""
    pewnosc: str = PEWNA
    status: str = OK
    uzytkownik: str = ""
    przydzial: str = ""      # "" (w sali) / "na stałe" / "wypożyczenie"
    zwrot: str = ""          # planowany zwrot (RRRR-MM-DD) przy wypożyczeniu
    sprawdzono: str = ""
    uwagi: str = ""
    sala_ewid: str = ""
    opis_ewid: str = ""
    w_ewidencji: str = "tak"
    zrodlo: str = ""
    extra: dict = field(default_factory=dict)   # kolumny dodane ręcznie w Excelu

    @property
    def building(self) -> str:
        return building(self.sala) if self.sala else ""

    @property
    def with_person(self) -> bool:
        return bool(self.uzytkownik)

    @property
    def where(self) -> str:
        """Gdzie jest teraz, jednym tekstem: '12', 'Nowak J. · 12', 'Nowak J. · Poza szkołą'."""
        place = self.sala or "?"
        return f"{self.uzytkownik} · {place}" if self.uzytkownik else place

    def overdue(self, today: date | None = None) -> bool:
        if self.przydzial != WYPOZYCZENIE or not self.zwrot:
            return False
        try:
            return date.fromisoformat(self.zwrot[:10]) < (today or date.today())
        except ValueError:
            return False

    @property
    def moved(self) -> bool:
        """Faktyczna sala inna niż w ewidencji."""
        return bool(self.sala and self.sala_ewid and self.sala != self.sala_ewid)


@dataclass
class Event:
    data: str
    id: str
    zdarzenie: str
    z: str = ""
    do: str = ""
    opis: str = ""


class InventoryLockedError(Exception):
    """Plik jest otwarty w Excelu albo nie da się do niego zapisać."""


class Inventory:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.items: dict[str, Item] = {}
        self.history: list[Event] = []
        self.rooms: list[dict] = []          # wiersze arkusza Sale
        self.room_extra_cols: list[str] = []
        self.materials: dict = {}            # kod -> zaplecze.Material
        self.model_schemes: dict[str, str] = {}   # MODEL -> schemat kolorów (zaplecze.SCHEMES)
        self.model_notes: dict[str, str] = {}
        self.other_sheets: dict[str, list[list]] = {}   # arkusze dodane ręcznie — zachowujemy
        self.tasks: list = []                # zadania.Task
        self.global_tasks: list = []         # zadania.GlobalTask
        self.progress: list = []             # zadania.Progress
        from .moj_plan import WorkHours
        self.my_plan: list = []              # moj_plan.Entry
        self.work_hours = WorkHours()
        self.osoby: dict = {}                # osoby.Person — rejestr osób

    # --- odczyt -----------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "Inventory":
        inv = cls(path)
        if not inv.path.exists():
            return inv
        wb = load_workbook(inv.path, data_only=True)
        if SHEET_ITEMS in wb.sheetnames:
            inv._load_items(wb[SHEET_ITEMS])
        if SHEET_HISTORY in wb.sheetnames:
            for row in _rows(wb[SHEET_HISTORY]):
                inv.history.append(Event(*(str(row.get(c, "") or "") for c in HISTORY_COLUMNS)))
        if SHEET_ROOMS in wb.sheetnames:
            ws = wb[SHEET_ROOMS]
            inv.rooms = [{k: ("" if v is None else v) for k, v in r.items()} for r in _rows(ws)]
            hdr = [c.value for c in ws[1] if c.value]
            inv.room_extra_cols = [h for h in hdr if h not in ROOM_COLUMNS]
        from .zaplecze import SHEET_MATERIALS, SHEET_MODELS, load_materials, load_models
        if SHEET_MATERIALS in wb.sheetnames:
            inv.materials = load_materials(wb[SHEET_MATERIALS], _rows)
        if SHEET_MODELS in wb.sheetnames:
            inv.model_schemes, inv.model_notes = load_models(wb[SHEET_MODELS], _rows)
        from .zadania import SHEET_GLOBAL, SHEET_PROGRESS, SHEET_TASKS, load_all
        inv.tasks, inv.global_tasks, inv.progress = load_all(wb, _rows)
        from . import moj_plan
        inv.my_plan, inv.work_hours = moj_plan.load(wb, _rows)
        from .osoby import SHEET_PEOPLE, load_people
        if SHEET_PEOPLE in wb.sheetnames:
            inv.osoby = load_people(wb[SHEET_PEOPLE], _rows)
        known = {SHEET_ITEMS, SHEET_HISTORY, SHEET_ROOMS, SHEET_MATERIALS, SHEET_MODELS,
                 SHEET_TASKS, SHEET_GLOBAL, SHEET_PROGRESS, moj_plan.SHEET_PLAN, moj_plan.SHEET_HOURS,
                 SHEET_PEOPLE}
        for name in wb.sheetnames:
            if name not in known:
                inv.other_sheets[name] = [list(r) for r in wb[name].iter_rows(values_only=True)]
        return inv

    def _load_items(self, ws) -> None:
        by_header = {h: a for a, h in ITEM_COLUMNS}
        for row in _rows(ws):
            if not row.get("ID"):
                continue
            kw, extra = {}, {}
            for h, v in row.items():
                if h in by_header:
                    a = by_header[h]
                    if a == "wartosc":
                        kw[a] = float(v) if isinstance(v, (int, float)) else None
                    elif isinstance(v, (datetime, date)):
                        kw[a] = v.strftime("%Y-%m-%d")
                    else:
                        kw[a] = "" if v is None else str(v).strip()
                elif h:
                    extra[h] = v
            if kw.get("sala"):
                kw["sala"] = _norm_loc(kw["sala"])
            if kw.get("sala_ewid"):
                kw["sala_ewid"] = _norm_loc(kw["sala_ewid"])
            it = Item(**kw)
            it.extra = extra
            self.items[it.id] = it

    # --- zapis ------------------------------------------------------------
    def save(self, backup_dir: Path | None = None, keep: int = 30) -> None:
        if backup_dir and self.path.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            shutil.copy2(self.path, backup_dir / f"zasoby_{stamp}.xlsx")
            for old in sorted(backup_dir.glob("zasoby_*.xlsx"))[:-keep]:
                old.unlink(missing_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = SHEET_ITEMS
        extras = sorted({k for it in self.items.values() for k in it.extra})
        headers = [h for _, h in ITEM_COLUMNS] + extras
        ws.append(headers)
        for it in sorted(self.items.values(), key=lambda i: (sort_key(i.sala) if i.sala else (99,), i.kategoria, i.id)):
            ws.append([getattr(it, a) for a, _ in ITEM_COLUMNS] + [it.extra.get(k) for k in extras])
        _style(ws, widths={"ID": 16, "Nr inwentarza": 14, "Kategoria": 16, "Nazwa": 38, "Projekt": 10,
                           "Sala (faktycznie)": 12, "Pewność lokalizacji": 11, "Status": 11,
                           "Użytkownik": 20, "Uwagi": 30, "Ewidencja – opis": 34, "Źródło": 30})
        col = {h: i + 1 for i, h in enumerate(headers)}
        _validation(ws, col["Pewność lokalizacji"], PEWNOSCI, len(self.items))
        _validation(ws, col["Status"], STATUSY, len(self.items))

        wh = wb.create_sheet(SHEET_HISTORY)
        wh.append(HISTORY_COLUMNS)
        for e in self.history:
            wh.append([e.data, e.id, e.zdarzenie, e.z, e.do, e.opis])
        _style(wh, widths={"Data": 17, "ID": 16, "Zdarzenie": 16, "Opis": 50})

        wr = wb.create_sheet(SHEET_ROOMS)
        rheaders = ROOM_COLUMNS + self.room_extra_cols
        wr.append(rheaders)
        for r in sorted(self.rooms, key=lambda r: sort_key(str(r.get("Sala", "")))):
            wr.append([r.get(h, "") for h in rheaders])
        _style(wr, widths={"Sala": 10, "Budynek": 18, "Typ": 22, "Uwagi": 40})
        _validation(wr, 3, ROOM_TYPES, len(self.rooms))

        from .zaplecze import (COLORS, MATERIAL_TYPES, SCHEMES, SHEET_MATERIALS, SHEET_MODELS,
                               write_materials, write_models)
        wm = wb.create_sheet(SHEET_MATERIALS)
        write_materials(wm, self.materials)
        _style(wm, widths={"Kod": 16, "Nazwa": 34, "Pasuje do (modele)": 30, "Gdzie leży": 16, "Uwagi": 30})
        _validation(wm, 3, MATERIAL_TYPES, len(self.materials))
        _validation(wm, 4, [c for c in COLORS if c], len(self.materials))
        wmod = wb.create_sheet(SHEET_MODELS)
        write_models(wmod, self.model_schemes, self.model_notes)
        _style(wmod, widths={"Model": 22, "Kolory": 20, "Uwagi": 40})
        _validation(wmod, 2, list(SCHEMES), len(self.model_schemes) + len(self.model_notes))

        from .zadania import write_all
        write_all(wb, self, _style, _validation)
        from . import moj_plan
        moj_plan.write(wb, self, _style)
        from .osoby import SHEET_PEOPLE, write_people
        write_people(wb.create_sheet(SHEET_PEOPLE), self.osoby, _style)

        for name, rows in self.other_sheets.items():
            wo = wb.create_sheet(name[:31])
            for r in rows:
                wo.append(r)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.stem + "_zapis.tmp.xlsx")
        try:
            wb.save(tmp)
            tmp.replace(self.path)
        except PermissionError as e:
            tmp.unlink(missing_ok=True)
            raise InventoryLockedError(
                f"Nie mogę zapisać {self.path.name} — zamknij go w Excelu i spróbuj ponownie.") from e

    # --- zmiany z historią ------------------------------------------------
    def log(self, item_id: str, zdarzenie: str, z: str = "", do: str = "", opis: str = "",
            when: datetime | None = None) -> None:
        stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
        self.history.append(Event(stamp, item_id, zdarzenie, z, do, opis))

    def update(self, item_id: str, **changes) -> list[str]:
        """Zmienia pola sprzętu i dopisuje zdarzenia do historii. Zwraca opisy zmian."""
        it = self.items[item_id]
        done = []
        if "sala" in changes:
            changes["sala"] = _norm_loc(changes["sala"]) if changes["sala"] else ""
        before_where = it.where
        for k, v in changes.items():
            old = getattr(it, k)
            if old == v:
                continue
            setattr(it, k, v)
            if k == "sala":
                self.log(item_id, "przeniesienie", before_where, it.where)
            elif k == "status":
                ev = {SERWIS: "serwis", WYPOZYCZONY: "wypożyczenie", WYCOFANY: "wycofanie"}.get(v, "zmiana statusu")
                if v == OK and old in (SERWIS, WYPOZYCZONY):
                    ev = "powrót z serwisu" if old == SERWIS else "zwrot"
                self.log(item_id, ev, old, v, it.uzytkownik if v == WYPOZYCZONY else "")
            elif k in ("pewnosc", "uzytkownik"):
                self.log(item_id, f"zmiana: {k}", str(old), str(v))
            done.append(k)
        return done

    def item_history(self, item_id: str) -> list[Event]:
        return [e for e in self.history if e.id == item_id]

    # --- lokalizacja: sala albo osoba -------------------------------------
    def move_to(self, item_id: str, room: str, note: str = "") -> None:
        """Przeniesienie do innej sali/miejsca. Przypisanie do osoby (jeśli jest) zostaje."""
        it = self.items[item_id]
        room = _norm_loc(room) if room else ""
        before = it.where
        it.sala = room
        if it.where != before:
            self.log(item_id, "przeniesienie", before, it.where, note)

    def hand_over(self, item_id: str, person: str, place: str, kind: str = WYPOZYCZENIE,
                  until: str = "", note: str = "") -> None:
        """Wydanie osobie: na stałe (np. laptop służbowy) albo wypożyczenie (z datą zwrotu).

        place — gdzie urządzenie fizycznie będzie: sala albo POZA_SZKOLA.
        """
        it = self.items[item_id]
        before = it.where
        it.uzytkownik = person.strip()
        it.sala = _norm_loc(place) if place else POZA_SZKOLA
        it.przydzial = kind
        it.zwrot = until if kind == WYPOZYCZENIE else ""
        if kind == WYPOZYCZENIE:
            it.status = WYPOZYCZONY
        elif it.status == WYPOZYCZONY:
            it.status = OK
        parts = [kind] + ([f"zwrot do {until}"] if until and kind == WYPOZYCZENIE else []) + ([note] if note else [])
        self.log(item_id, "wypożyczenie" if kind == WYPOZYCZENIE else "wydanie", before, it.where, " · ".join(parts))

    def take_back(self, item_id: str, room: str, note: str = "") -> None:
        """Zwrot od osoby — urządzenie wraca do sali (bez przypisania do osoby)."""
        it = self.items[item_id]
        before = it.where
        it.uzytkownik, it.przydzial, it.zwrot = "", "", ""
        if it.status == WYPOZYCZONY:
            it.status = OK
        it.sala = _norm_loc(room) if room else ""
        self.log(item_id, "zwrot", before, it.where, note)

    def room_before_handover(self, item_id: str) -> str:
        """Sala, z której urządzenie wydano osobie (podpowiedź przy zwrocie)."""
        for e in reversed(self.item_history(item_id)):
            if e.zdarzenie in ("wydanie", "wypożyczenie"):
                return e.z if is_room(e.z) else ""
        return ""

    def location_history(self, item_id: str) -> list[Event]:
        return [e for e in self.item_history(item_id) if e.zdarzenie in LOCATION_EVENTS]

    def people(self) -> list[str]:
        """Osoby do wyboru: rejestr osób + ci, którzy mają sprzęt (gdyby nie byli w rejestrze)."""
        return sorted(set(self.osoby) | {i.uzytkownik for i in self.items.values() if i.uzytkownik})

    # --- zapytania --------------------------------------------------------
    def locations(self) -> list[str]:
        return sorted({it.sala for it in self.items.values() if it.sala}, key=sort_key)

    def in_room(self, room: str, with_zapl: bool = True) -> list[Item]:
        room = normalize_room(room)
        out = []
        for it in self.items.values():
            if it.sala == room or (with_zapl and it.sala == room + "-ZAPL"):
                out.append(it)
        return out

    def summary(self, items: list[Item]) -> str:
        c = Counter(it.kategoria for it in items)
        return ", ".join(f"{n}× {k}" for k, n in c.most_common())

    def ensure_rooms(self, rooms: list[str]) -> int:
        """Dopisuje do arkusza Sale brakujące sale (z planu i ze sprzętu). Zwraca liczbę dodanych."""
        have = {normalize_room(str(r.get("Sala", ""))) for r in self.rooms}
        added = 0
        for r in rooms:
            if not is_room(r) or r.endswith("-ZAPL"):
                continue
            n = normalize_room(r)
            if n not in have:
                self.rooms.append({"Sala": n, "Budynek": building(n), "Typ": "", "Stanowiska": "", "Uwagi": ""})
                have.add(n)
                added += 1
        return added

    def pc_breakdown(self, room: str) -> Counter:
        """Stanowiska w sali wg kategorii, np. {'Komputer': 4, 'Laptop': 12} (bez zaplecza i wycofanych)."""
        return Counter(i.kategoria for i in self.in_room(room, with_zapl=False)
                       if i.kategoria in PC_CATEGORIES and i.status != WYCOFANY)

    def pc_count(self, room: str) -> int:
        """Liczba stanowisk komputerowych w sali (PC + laptopy + chromebooki)."""
        return sum(self.pc_breakdown(room).values())

    def room_kind(self, room: str) -> str:
        """'it' (pracownia komputerowa), 'pc' (tylko PC nauczyciela) albo '' (bez komputerów).

        Typ wpisany ręcznie w arkuszu Sale ma pierwszeństwo; inaczej liczymy komputery.
        """
        typ = self.room_types().get(normalize_room(room), "").strip().lower()
        if typ.startswith("komputer"):
            return KIND_IT
        if typ.startswith("tylko pc"):
            return KIND_PC
        if typ:
            return ""
        n = self.pc_count(room)
        return KIND_IT if n >= IT_MIN_PCS else KIND_PC if n >= 1 else ""

    def room_types(self) -> dict[str, str]:
        return {normalize_room(str(r.get("Sala", ""))): str(r.get("Typ", "") or "") for r in self.rooms}


# --- pomocnicze -------------------------------------------------------------
def _norm_loc(loc: str) -> str:
    return normalize_room(loc) if is_room(loc) else loc.strip()


def _rows(ws) -> list[dict]:
    it = ws.iter_rows(values_only=True)
    try:
        hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    except StopIteration:
        return []
    out = []
    for row in it:
        if row is None or all(v is None or v == "" for v in row):
            continue
        out.append({h: v for h, v in zip(hdr, row) if h})
    return out


def _style(ws, widths: dict[str, int]) -> None:
    head_fill = PatternFill("solid", fgColor="DDE7F3")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
        if c.value in widths:
            ws.column_dimensions[c.column_letter].width = widths[c.value]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _validation(ws, col_idx: int, values: list[str], n_rows: int) -> None:
    from openpyxl.utils import get_column_letter
    letter = get_column_letter(col_idx)
    dv = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
    dv.add(f"{letter}2:{letter}{max(n_rows + 500, 1000)}")
    ws.add_data_validation(dv)


ITEM_FIELD_NAMES = [f.name for f in fields(Item)]
