"""Import zestawień z ewidencji księgowej (.xls / .xlsx) do spisu sprzętu.

Pole „Pomieszczenie” to wolny tekst. Rozpoznajemy m.in.:
    16.0 / 04W / 24A          -> sala
    36-ZAPL                   -> zaplecze sali 36
    29/ w 12, 30W/w 21W od…   -> wg ewidencji 29, faktycznie 12
    16 (jest w 39W)           -> wg ewidencji 16, faktycznie 39W
    12W użytkuje Nowak J.     -> sala + użytkownik
    21 Wiśniewska A.            -> sala + użytkownik
    11W (w naprawie)          -> status serwis
    15, 33, 2 w 16, 32W       -> lista (gdy kilka sztuk pod jednym numerem)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .sale import normalize_room
from .sprzet import (EWID_FIELDS, NIEPEWNA, NIEZNANA, OK, PEWNA, SERWIS, WYPOZYCZONY, Inventory,
                     Item)

ROOM_TOKEN = r"\d{1,2}[WB]?A?(?:\s*-\s*ZAPL)?"
_ROOM_ANY = re.compile(rf"(?<![\d.A-Za-z])({ROOM_TOKEN})(?![\w])", re.IGNORECASE)
_SZT = re.compile(r"\b(\d{1,3})\s*szt\.?", re.IGNORECASE)
_ROOM_AFTER_W = re.compile(rf"(?:^|[\s(/])w\s*({ROOM_TOKEN})(?![\w])", re.IGNORECASE)
_JEST_W = re.compile(rf"jest\s+w\s*({ROOM_TOKEN})(?![\w])", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
_NAME_AFTER = re.compile(r"^[\s)(\-–,]*([A-ZĄĆĘŁŃÓŚŹŻ][\w\-.]*\.?(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][\w\-.]*\.?)*)")
_COUNT_IN = re.compile(r"^(\d{1,3})\s*w\s+(.+)$", re.IGNORECASE)

PL_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"


@dataclass
class Loc:
    sala: str = ""          # faktyczna lokalizacja
    sala_ewid: str = ""     # lokalizacja wg ewidencji
    pewnosc: str = PEWNA
    status: str = OK
    uzytkownik: str = ""
    uwagi_user: str = ""


def _clean(text: str) -> str:
    t = text.strip()
    t = _DATE.sub(" ", t)
    t = _SZT.sub(" ", t)
    t = re.sub(r"nr\.?\s*ser\.?\s*\S+", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bod\s*$", "", t.strip())
    # "28Zieliński Piotr" -> "28 Zieliński Piotr"
    t = re.sub(rf"(\d)([{PL_UPPER}][a-ząćęłńóśźż])", r"\1 \2", t)
    return t


def _norm(tok: str) -> str:
    return normalize_room(re.sub(r"\s+", "", tok))


def parse_single(text: str) -> Loc:
    """Lokalizacja jednej sztuki sprzętu z tekstu ewidencji."""
    raw = (text or "").strip()
    low = raw.lower()
    loc = Loc()
    if not raw:
        loc.pewnosc = NIEZNANA
        return loc
    if "napraw" in low or "serwis" in low:
        loc.status = SERWIS
    if "użycz" in low or "wypożycz" in low:
        loc.status = WYPOZYCZONY

    t = _clean(raw)
    moved_note = None
    m = re.search(r"użytkuj[eą]\s+(.+)$", t, re.IGNORECASE)
    if m:
        user = m.group(1).strip()
        t = t[: m.start()].strip()
        if "/" in user:
            # "Lewandowska Ewa/ w 16" -> dalsza historia po ukośniku: bierzemy ostatnie "w SALA"
            user, rest = user.split("/", 1)
            last = list(_ROOM_AFTER_W.finditer(" " + rest))
            moved_note = _norm(last[-1].group(1)) if last else None
            loc.pewnosc = NIEPEWNA
        loc.uzytkownik = user.strip()
        if loc.uzytkownik.lower().startswith("w burs"):   # "16/użytkują w bursie wychowawcy"
            a = _ROOM_ANY.search(t)
            loc.sala, loc.sala_ewid = "Bursa (inne)", (_norm(a.group(1)) if a else "")
            loc.uwagi_user = loc.uzytkownik
            loc.uzytkownik, loc.pewnosc = "", NIEPEWNA
            return loc

    # miejsca spoza sal
    if re.search(r"\bburs", t, re.IGNORECASE) and not _ROOM_AFTER_W.match(t):
        z = re.search(rf"\bz\s+({ROOM_TOKEN})", t, re.IGNORECASE)
        loc.sala = "Bursa (inne)"
        loc.sala_ewid = _norm(z.group(1)) if z else ""
        loc.pewnosc = NIEPEWNA
        return loc
    if "korytarz" in t.lower():
        loc.sala = "Korytarz"
        return loc

    ewid = fakt = None
    after = ""  # tekst za ostatnią rozpoznaną salą (np. nazwisko)
    if "/" in t:
        left, right = t.split("/", 1)
        a = _ROOM_ANY.search(left)
        b = _ROOM_AFTER_W.search(right)
        ewid = _norm(a.group(1)) if a else None
        fakt = _norm(b.group(1)) if b else ewid
        after = right[b.end():] if b else ""
        if loc.status == WYPOZYCZONY and not b:
            fakt = None
    elif (j := _JEST_W.search(t)):
        fakt = _norm(j.group(1))
        a = _ROOM_ANY.search(t[: j.start()])
        ewid = _norm(a.group(1)) if a else fakt
        after = t[j.end():]
    else:
        a = _ROOM_ANY.search(t)
        if a:
            ewid = fakt = _norm(a.group(1))
            after = t[a.end():]

    if not loc.uzytkownik and after:
        n = _NAME_AFTER.match(after)
        if n and not re.match(r"^(w|od|do|z)\b", n.group(1), re.IGNORECASE):
            loc.uzytkownik = n.group(1).strip().rstrip(")")

    if moved_note:
        fakt = moved_note
    loc.sala_ewid = ewid or ""
    loc.sala = fakt or ""
    if not fakt:
        loc.pewnosc = NIEZNANA if not ewid else NIEPEWNA
    return loc


def parse_location(text: str, qty: int) -> list[tuple[int, Loc]]:
    """Rozdziela lokalizacje na sztuki: [(ile, Loc), ...] — suma = qty."""
    qty = max(int(qty or 1), 1)
    raw = (text or "").strip()
    if qty == 1:
        return [(1, parse_single(raw))]
    parts = [p.strip() for p in re.split(r"[,;]", raw) if p.strip()]
    out: list[tuple[int, Loc]] = []
    for p in parts:
        m = _COUNT_IN.match(p)
        s = _SZT.search(p)
        if m and _ROOM_ANY.search(_clean(m.group(2))):
            out.append((int(m.group(1)), parse_single(m.group(2))))
        elif s:                                   # "1 szt. Kamińska Anna ..."
            loc = parse_single(p)
            if not loc.sala:
                rest = _NAME_AFTER.match(_clean(p))
                loc.uzytkownik = loc.uzytkownik or (rest.group(1) if rest else "")
                loc.pewnosc = NIEPEWNA
            out.append((int(s.group(1)), loc))
        else:
            out.append((1, parse_single(p)))
    total = sum(n for n, _ in out)
    if len(out) == 1 and total < qty:          # "16.0" przy ilości 2 -> wszystkie tam
        return [(qty, out[0][1])]
    if total == qty:
        return out
    # nie zgadza się liczba sztuk -> to, co się da, jako niepewne
    for _, l in out:
        if l.pewnosc == PEWNA:
            l.pewnosc = NIEPEWNA
    if total < qty:
        out.append((qty - total, Loc(pewnosc=NIEZNANA)))
        return out
    trimmed, left = [], qty
    for n, l in out:
        if left <= 0:
            break
        trimmed.append((min(n, left), l))
        left -= n
    return trimmed


# --- kategorie i projekty ------------------------------------------------------
_CATEGORY_RULES = [
    (r"chromebook", "Chromebook"),
    (r"laptop|notebook", "Laptop"),
    (r"tablet\s+pi[óo]rk", "Tablet piórkowy"),
    (r"tablet", "Tablet"),
    (r"monitor\s+interaktywn|tablica", "Tablica / monitor interaktywny"),
    (r"monitor", "Monitor"),
    (r"serwer", "Serwer"),
    (r"komputer|zestaw komputer|zestaw$|pc\b", "Komputer"),
    (r"kserokopiar", "Kserokopiarka"),
    (r"wielofunkcyj", "Urządzenie wielofunkcyjne"),
    (r"ploter", "Ploter"),
    (r"drukark", "Drukarka"),
    (r"projektor|rzutnik|zestaw multimedialny", "Projektor"),
    (r"niszczark", "Niszczarka"),
    (r"skaner", "Skaner"),
]
_FILE_CATEGORY = [
    ("komputer", "Komputer"), ("laptop", "Laptop"), ("monitor", "Monitor"), ("drukark", "Drukarka"),
    ("projektor", "Projektor"), ("tablic", "Tablica / monitor interaktywny"), ("tablet", "Tablet"),
    ("skaner", "Skaner"), ("niszczark", "Niszczarka"),
]


def guess_category(name: str, file_name: str, sheet_name: str) -> str:
    low = name.lower()
    for pat, cat in _CATEGORY_RULES:
        if re.search(pat, low):
            return cat
    src = f"{sheet_name} {file_name}".lower()
    for key, cat in _FILE_CATEGORY:
        if key in src:
            return cat
    return "Inne"


def guess_project(file_name: str, sheet_name: str) -> str:
    if "kpo" in sheet_name.lower() or "kpo" in file_name.lower():
        return "KPO"
    if re.search(r"\bŚT\b", file_name):
        return "ŚT"
    return "PŚT"


# --- odczyt plików ---------------------------------------------------------------
@dataclass
class SourceRow:
    inv: str
    nazwa: str
    data: str
    wartosc: float | None
    ilosc: int
    pomieszczenie: str
    zgadza: bool
    file: str
    sheet: str


@dataclass
class ImportReport:
    files: list[str] = field(default_factory=list)
    rows: int = 0
    items: int = 0
    split_rows: list[str] = field(default_factory=list)       # numery rozbite na sztuki
    duplicates: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    return str(v).strip()


def _read_book(path: Path):
    """Zwraca listę (nazwa_arkusza, wiersze, datemode) dla .xls i .xlsx."""
    if path.suffix.lower() == ".xls":
        import xlrd
        wb = xlrd.open_workbook(str(path))
        return [(sh.name, [sh.row_values(r) for r in range(sh.nrows)], wb.datemode) for sh in wb.sheets()]
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    return [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)], None) for ws in wb.worksheets]


def _to_date(v, datemode) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and datemode is not None and 20000 < v < 80000:
        import xlrd
        return xlrd.xldate_as_datetime(v, datemode).strftime("%Y-%m-%d")
    return _cell_str(v)


def read_source_rows(paths: list[Path], report: ImportReport) -> list[SourceRow]:
    out: list[SourceRow] = []
    for path in paths:
        try:
            sheets = _read_book(path)
        except Exception as e:  # noqa: BLE001
            report.warnings.append(f"{path.name}: nie da się odczytać ({e})")
            continue
        report.files.append(path.name)
        for sname, rows, datemode in sheets:
            hi = next((i for i, r in enumerate(rows[:15]) if r and _cell_str(r[0]).lower() == "lp"), None)
            if hi is None:
                continue
            hdr = [_cell_str(h).lower() for h in rows[hi]]

            def col(*prefixes):
                for i, h in enumerate(hdr):
                    if any(h.startswith(p) for p in prefixes):
                        return i
                return None

            c_inv, c_name = col("nr inw", "numer inw"), col("nazwa")
            c_date, c_price, c_val = col("data"), col("cena"), col("warto")
            c_qty, c_room = col("ilo"), col("pomieszcz")
            if c_inv is None or c_name is None or c_room is None:
                report.warnings.append(f"{path.name} / {sname}: brak wymaganych kolumn")
                continue
            for r in rows[hi + 1:]:
                if len(r) <= max(c_inv, c_name, c_room):
                    continue
                inv = _cell_str(r[c_inv])
                if not inv:
                    continue
                qty_v = r[c_qty] if c_qty is not None else 1
                try:
                    qty = int(float(qty_v)) if qty_v not in ("", None) else 1
                except ValueError:
                    qty = 1
                price = r[c_price] if c_price is not None else None
                if not isinstance(price, (int, float)):
                    val = r[c_val] if c_val is not None else None
                    price = (val / qty) if isinstance(val, (int, float)) and qty else None
                zgadza = any(isinstance(v, str) and "zgadza" in v.lower() for v in r)
                out.append(SourceRow(
                    inv=inv, nazwa=_cell_str(r[c_name]),
                    data=_to_date(r[c_date], datemode) if c_date is not None else "",
                    wartosc=float(price) if isinstance(price, (int, float)) else None,
                    ilosc=max(qty, 1), pomieszczenie=_cell_str(r[c_room]), zgadza=zgadza,
                    file=path.name, sheet=sname,
                ))
    report.rows = len(out)
    return out


def build_items(rows: list[SourceRow], report: ImportReport, verified_label: str = "") -> list[Item]:
    items: dict[str, Item] = {}
    for row in rows:
        parts = parse_location(row.pomieszczenie, row.ilosc)
        if row.ilosc > 1:
            report.split_rows.append(f"{row.inv} ({row.ilosc} szt.): „{row.pomieszczenie}”")
        k = 0
        for n, loc in parts:
            for _ in range(n):
                k += 1
                iid = row.inv if row.ilosc == 1 else f"{row.inv}#{k}"
                if iid in items:
                    report.duplicates.append(f"{iid} ({row.file})")
                    continue
                it = Item(
                    id=iid, inv=row.inv,
                    kategoria=guess_category(row.nazwa, row.file, row.sheet),
                    nazwa=row.nazwa, projekt=guess_project(row.file, row.sheet),
                    data=row.data, wartosc=row.wartosc,
                    sala=loc.sala, pewnosc=loc.pewnosc, status=loc.status, uzytkownik=loc.uzytkownik,
                    sprawdzono=verified_label if row.zgadza else "",
                    sala_ewid=loc.sala_ewid, opis_ewid=row.pomieszczenie,
                    w_ewidencji="tak", zrodlo=f"{row.file} / {row.sheet}",
                )
                items[iid] = it
                if loc.pewnosc != PEWNA:
                    report.uncertain.append(f"{iid}: „{row.pomieszczenie}” → {loc.sala or '?'} ({loc.pewnosc})")
    report.items = len(items)
    return list(items.values())


# --- scalanie z istniejącym spisem ----------------------------------------------------
@dataclass
class MergeReport:
    added: list[str] = field(default_factory=list)
    updated: int = 0
    changed_desc: list[str] = field(default_factory=list)   # zmienił się opis lokalizacji w ewidencji
    missing: list[str] = field(default_factory=list)        # zniknęły z ewidencji


def merge(inv: Inventory, new_items: list[Item]) -> MergeReport:
    """Dane z ewidencji aktualizują spis; pola prowadzone ręcznie (sala, status…) zostają."""
    rep = MergeReport()
    first_import = not inv.items
    new_ids = set()
    for it in new_items:
        new_ids.add(it.id)
        ex = inv.items.get(it.id)
        if ex is None:
            inv.items[it.id] = it
            rep.added.append(it.id)
            if not first_import:
                inv.log(it.id, "nowa pozycja", "", it.sala, "dodana z nowego zestawienia ewidencji")
            continue
        if ex.opis_ewid != it.opis_ewid:
            rep.changed_desc.append(f"{it.id}: „{ex.opis_ewid}” → „{it.opis_ewid}” (u mnie: {ex.sala or '?'})")
        for f in EWID_FIELDS:
            setattr(ex, f, getattr(it, f))
        if not ex.sprawdzono and it.sprawdzono:
            ex.sprawdzono = it.sprawdzono
        rep.updated += 1
    for iid, ex in inv.items.items():
        if iid not in new_ids and ex.w_ewidencji == "tak":
            ex.w_ewidencji = "nie"
            rep.missing.append(iid)
            inv.log(iid, "brak w ewidencji", opis="pozycja zniknęła z nowego zestawienia")
    return rep


def import_files(paths: list[Path], verified_label: str = "") -> tuple[list[Item], ImportReport]:
    report = ImportReport()
    rows = read_source_rows(sorted(paths), report)
    items = build_items(rows, report, verified_label)
    return items, report
