"""Nazwy sal i lokalizacji: normalizacja, rozpoznawanie i przypisanie do budynku.

Konwencja szkoły:
    sufiks W  -> Warsztat      (np. 11W, 19WA)
    sufiks B  -> Bursa         (np. 6B)
    bez sufiksu / A -> budynek główny (np. 12, 24A)
    D1 D2 M1 M2 -> duża / mała sala gimnastyczna
    "-ZAPL" -> zaplecze sali (np. 36-ZAPL, 8B-ZAPL)
Lokalizacja spoza tego schematu (np. "Korytarz") to "inne miejsce".
"""
from __future__ import annotations

import re

GLOWNY = "Budynek główny"
WARSZTAT = "Warsztat"
BURSA = "Bursa"
GIMNASTYCZNA = "Sale gimnastyczne"
INNE = "Inne miejsca"

BUILDINGS = [GLOWNY, WARSZTAT, BURSA, GIMNASTYCZNA, INNE]
ZAPL = "-ZAPL"

# numer + opcjonalnie W/B (budynek) + opcjonalnie A (sala obok), albo hala D1/D2/M1/M2
_ROOM_RE = re.compile(r"^(?:\d{1,2}[WB]?A?|[DM]\d)$", re.IGNORECASE)
_NUM_RE = re.compile(r"^0*(\d+)([A-Z]*)$")
_GYM_RE = re.compile(r"^[DM]\d$")


def looks_like_room(text: str) -> bool:
    """Czy token wygląda na nazwę sali (np. '37', '11w', '24a', 'D1')."""
    return bool(_ROOM_RE.match(text.strip()))


def split_zapl(loc: str) -> tuple[str, bool]:
    """'36-ZAPL' -> ('36', True); '36' -> ('36', False)."""
    s = loc.strip().upper().replace(" ", "")
    if s.endswith(ZAPL):
        return s[: -len(ZAPL)], True
    return s, False


def normalize_room(text: str) -> str:
    """Ujednolica zapis sali: '04W' -> '4W', '16.0' -> '16', '11w' -> '11W', '08w-zapl' -> '8W-ZAPL'."""
    s, zapl = split_zapl(text)
    if s.endswith(".0"):
        s = s[:-2]
    m = _NUM_RE.match(s)
    if m:
        s = f"{int(m.group(1))}{m.group(2)}"
    return s + (ZAPL if zapl else "")


def is_room(loc: str) -> bool:
    """Sala lub zaplecze sali (a nie wolny tekst typu 'Korytarz')."""
    base, _ = split_zapl(loc)
    return bool(base) and looks_like_room(base)


def base_room(loc: str) -> str:
    """Sala, do której należy lokalizacja: '36-ZAPL' -> '36'."""
    return normalize_room(split_zapl(loc)[0])


def building(room: str) -> str:
    if not is_room(room):
        return INNE
    r = base_room(room)
    if _GYM_RE.match(r):
        return GIMNASTYCZNA
    m = _NUM_RE.match(r)
    suffix = m.group(2) if m else ""
    if suffix.startswith("W"):
        return WARSZTAT
    if suffix.startswith("B"):
        return BURSA
    return GLOWNY


def sort_key(room: str) -> tuple:
    """Sortowanie: budynek, numer, sufiks; zaplecze zaraz po swojej sali."""
    b = BUILDINGS.index(building(room))
    if b == BUILDINGS.index(INNE):
        return (b, 0, room.upper(), False)
    r, zapl = split_zapl(normalize_room(room))
    if _GYM_RE.match(r):
        return (b, 0, r, zapl)
    m = re.search(r"(\d+)", r)
    num = int(m.group(1)) if m else 0
    return (b, num, r, zapl)
