"""Rejestr osób: każda osoba raz, niezależnie od źródła (plan, ewidencja, wpis ręczny).

Arkusz „Osoby” w zasoby.xlsx:
    Osoba     — nazwa główna, zwykle „Nazwisko Imię” (tak jak w planie aSc)
    Funkcja   — np. nauczyciel, dyrektor, wicedyrektor, księgowa
    Aliasy    — inne zapisy tej samej osoby, oddzielone „;” (np. „Jan Nowak; Nowak J.”)
    Źródło    — plan / ewidencja / ręcznie
    Uwagi
    Nie łączyć z — osoby oznaczone jako „to nie duplikat”, oddzielone „;”
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sprzet import Inventory

SHEET_PEOPLE = "Osoby"
PEOPLE_COLUMNS = [("nazwa", "Osoba"), ("funkcja", "Funkcja"), ("aliasy", "Aliasy"), ("zrodlo", "Źródło"),
                  ("uwagi", "Uwagi"), ("nie_laczyc", "Nie łączyć z")]
Z_PLANU, Z_EWIDENCJI, RECZNIE = "plan", "ewidencja", "ręcznie"

# funkcje pisane przed nazwiskiem w ewidencji
_TITLES = [
    (r"w-?ce\.?\s*dyr(?:ektor\w*)?\.?", "wicedyrektor"),
    (r"wicedyr\w*\.?", "wicedyrektor"),
    (r"p\.\s*dyrektor\w*", "dyrektor"),
    (r"dyrektor\w*", "dyrektor"),
    (r"gł\.?\s*księgow\w*", "główna księgowa"),
    (r"księgow\w*", "księgowa"),
    (r"kierownik\w*", "kierownik"),
    (r"sekretar\w*", "sekretariat"),
]
_NOT_PEOPLE = {"ups", "serwer", "projektor", "monitor", "komputer", "drukarka", "zestaw", "tablica", "sala"}
_UP = "A-ZĄĆĘŁŃÓŚŹŻ"
_PLACEHOLDERS = {"brak", "wakat", "n", "nn", "nieznany", "vacat", "zastepstwo", "zastępstwo", ""}


def norm_key(s: str) -> str:
    """Klucz porównania: małe litery, bez kropek, pojedyncze spacje."""
    s = re.sub(r"[.\s]+", " ", s.lower()).strip()
    return s


def _ascii(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn") \
        .replace("ł", "l")


def clean_name(raw: str) -> tuple[str, str]:
    """'w-ce dyr. Kowalska Ewa' -> ('Kowalska Ewa', 'wicedyrektor');
    'A. Zieliński w bursie' -> ('A. Zieliński', ''); 'UPS' -> ('', '')."""
    s = (raw or "").strip()
    funkcja = ""
    for pat, fn in _TITLES:
        m = re.match(rf"^\s*{pat}\s*", s, re.IGNORECASE)
        if m:
            funkcja = fn
            s = s[m.end():]
            break
    s = re.split(r"[(/,;]", s)[0]                       # ucinamy opis w nawiasie / po ukośniku
    tokens = s.split()
    name: list[str] = []
    for t in tokens:
        if re.match(rf"^[{_UP}][\w\-]*\.?$", t) or re.match(rf"^[{_UP}]\.$", t):
            name.append(t)
            if len(name) == 3:
                break
        else:
            break                                       # pierwsze małe słowo kończy nazwisko („w bursie”)
    name_s = " ".join(name).strip()
    if not name_s or name_s.lower() in _NOT_PEOPLE or (len(name) == 1 and name_s.isupper() and len(name_s) <= 4):
        return "", funkcja
    return name_s, funkcja


@dataclass
class Person:
    nazwa: str
    funkcja: str = ""
    aliasy: str = ""
    zrodlo: str = RECZNIE
    uwagi: str = ""
    nie_laczyc: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def alias_list(self) -> list[str]:
        return [a.strip() for a in self.aliasy.split(";") if a.strip()]

    @property
    def not_dup(self) -> set[str]:
        return {norm_key(a) for a in self.nie_laczyc.split(";") if a.strip()}

    def add_alias(self, alias: str) -> None:
        alias = alias.strip()
        if alias and norm_key(alias) != norm_key(self.nazwa) and \
                norm_key(alias) not in {norm_key(a) for a in self.alias_list}:
            self.aliasy = "; ".join(self.alias_list + [alias])

    @property
    def tokens(self) -> list[str]:
        return [t.strip(".") for t in self.nazwa.split()]


# --- dopasowanie -------------------------------------------------------------------
def _same_person(a: str, b: str) -> str:
    """Czy dwa zapisy mogą oznaczać tę samą osobę? Zwraca powód albo ''.

    Obsługuje: odwróconą kolejność, inicjał zamiast imienia, zdrobnienie (wspólny początek imienia).
    """
    ta = [_ascii(t).strip(".") for t in a.split() if t.strip(".")]
    tb = [_ascii(t).strip(".") for t in b.split() if t.strip(".")]
    if len(ta) < 2 or len(tb) < 2:
        return ""
    if sorted(ta) == sorted(tb):
        return "ta sama osoba w innej kolejności" if ta != tb else "ten sam zapis"
    # wspólne nazwisko (pełne słowo ≥3 litery), reszta: inicjał lub wspólny początek imienia
    for sa in ta:
        if len(sa) < 3 or sa not in tb:
            continue
        ra = [t for t in ta if t != sa]
        rb = [t for t in tb if t != sa]
        if len(ra) != 1 or len(rb) != 1:
            continue
        x, y = ra[0], rb[0]
        if len(x) == 1 or len(y) == 1:
            if x[0] == y[0]:
                return "inicjał imienia"
        else:
            n = 2 if min(len(x), len(y)) <= 3 else 3
            if x[:n] == y[:n]:
                return "zdrobnienie / skrót imienia"
    return ""


class Registry:
    """Operacje na inv.osoby (dict: nazwa -> Person)."""

    def __init__(self, inv: "Inventory"):
        self.inv = inv

    @property
    def people(self) -> dict[str, Person]:
        return self.inv.osoby

    def find(self, name: str) -> Person | None:
        """Osoba po nazwie albo aliasie (dokładnie, bez względu na wielkość liter i kropki)."""
        k = norm_key(name)
        for p in self.people.values():
            if norm_key(p.nazwa) == k or any(norm_key(a) == k for a in p.alias_list):
                return p
        return None

    def match(self, name: str) -> tuple[Person | None, str]:
        """Najlepsze dopasowanie: dokładne (alias) albo jedna pasująca osoba wg _same_person."""
        p = self.find(name)
        if p:
            return p, "znana"
        hits = [(q, why) for q in self.people.values() if (why := _same_person(name, q.nazwa))]
        if len(hits) == 1:
            return hits[0]
        return None, ""

    def add(self, name: str, funkcja: str = "", zrodlo: str = RECZNIE) -> Person:
        p = self.find(name)
        if p:
            if funkcja and p.funkcja in ("", "nauczyciel"):   # konkretna funkcja wygrywa z ogólną
                p.funkcja = funkcja
            return p
        p = Person(name.strip(), funkcja, zrodlo=zrodlo)
        self.people[p.nazwa] = p
        return p

    def resolve(self, raw: str, zrodlo: str = Z_EWIDENCJI) -> tuple[str, str]:
        """Surowy zapis z ewidencji -> (nazwa w rejestrze, opis co zrobiono). Pusty, gdy to nie osoba."""
        name, funkcja = clean_name(raw)
        if not name and funkcja:
            # sama funkcja („Dyrektor”, „P.Dyrektor”) — osoba-funkcja do scalenia z właściwą osobą
            p = self.find(funkcja.capitalize()) or self.add(funkcja.capitalize(), funkcja, zrodlo)
            return p.nazwa, f"„{raw}” → {p.nazwa} (sama funkcja — scal z właściwą osobą w zakładce Osoby)"
        if not name:
            return "", f"„{raw}” — to nie wygląda na osobę"
        p, why = self.match(name)
        if p:
            p.add_alias(name)                    # alias = oczyszczony zapis (bez funkcji i dopisków)
            if funkcja and p.funkcja in ("", "nauczyciel"):   # konkretna funkcja wygrywa z ogólną
                p.funkcja = funkcja
            return p.nazwa, ("" if norm_key(raw) == norm_key(p.nazwa)
                             else f"„{raw}” → {p.nazwa}" + ("" if why == "znana" else f" ({why})"))
        p = self.add(name, funkcja, zrodlo)
        return p.nazwa, f"„{raw}” → nowa osoba {p.nazwa}" + (f" ({funkcja})" if funkcja else "")

    def sync_plan(self, teachers: list[str]) -> int:
        """Dodaje nauczycieli z planu (funkcja: nauczyciel). Zwraca liczbę nowych."""
        n = 0
        for t in teachers:
            if set(norm_key(t).split()) <= _PLACEHOLDERS:     # „Brak Brak”, „Wakat” — to nie osoby
                continue
            p = self.find(t)
            if p is None:
                p, _ = self.match(t)
                if p is not None:
                    # nauczyciel z planu = pełny, pewny zapis: staje się nazwą główną
                    self.rename(p.nazwa, t)
                    p.zrodlo = Z_PLANU
                    if not p.funkcja:
                        p.funkcja = "nauczyciel"
                    continue
                self.people[t] = Person(t, "nauczyciel", zrodlo=Z_PLANU)
                n += 1
            elif not p.funkcja:
                p.funkcja = "nauczyciel"
        return n

    def devices(self, name: str) -> list:
        return [i for i in self.inv.items.values() if i.uzytkownik == name]

    def rename(self, old: str, new: str) -> None:
        p = self.people.pop(old)
        p.add_alias(old)
        p.nazwa = new.strip()
        p.aliasy = "; ".join(a for a in p.alias_list if norm_key(a) != norm_key(p.nazwa))
        self.people[p.nazwa] = p
        for it in self.inv.items.values():
            if it.uzytkownik == old:
                it.uzytkownik = p.nazwa

    def merge(self, keep: str, others: list[str]) -> int:
        """Scala osoby `others` w `keep`: aliasy przechodzą, urządzenia zmieniają osobę. Zwraca liczbę urządzeń."""
        k = self.people[keep]
        moved = 0
        for name in others:
            if name == keep or name not in self.people:
                continue
            o = self.people.pop(name)
            k.add_alias(o.nazwa)
            for a in o.alias_list:
                k.add_alias(a)
            if o.funkcja and not k.funkcja:
                k.funkcja = o.funkcja
            if o.uwagi:
                k.uwagi = "; ".join(x for x in (k.uwagi, o.uwagi) if x)
            for it in self.inv.items.values():
                if it.uzytkownik == name:
                    it.uzytkownik = keep
                    moved += 1
            self.inv.log(f"osoba:{keep}", "scalenie osób", name, keep, f"{moved} urządzeń")
        return moved

    def duplicates(self) -> list[tuple[str, str, str]]:
        """Pary (a, b, powód) wyglądające na tę samą osobę (pomija oznaczone jako „nie łączyć”)."""
        names = sorted(self.people)
        out = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pa, pb = self.people[a], self.people[b]
                if norm_key(b) in pa.not_dup or norm_key(a) in pb.not_dup:
                    continue
                why = _same_person(a, b)
                if why:
                    out.append((a, b, why))
        return out

    def mark_different(self, a: str, b: str) -> None:
        for x, y in ((a, b), (b, a)):
            p = self.people[x]
            p.nie_laczyc = "; ".join([s for s in p.nie_laczyc.split(";") if s.strip()] + [y])

    def normalize_items(self) -> list[str]:
        """Ujednolica pole „U kogo” we wszystkich urządzeniach wg rejestru. Zwraca opisy zmian."""
        notes = []
        for it in self.inv.items.values():
            if not it.uzytkownik:
                continue
            new, note = self.resolve(it.uzytkownik)
            if not new:
                # to nie osoba (np. „UPS”) — przenosimy do notatki
                it.uwagi = "; ".join(x for x in (it.uwagi, f"z ewidencji: {it.uzytkownik}") if x)
                notes.append(f"{it.id}: {note}")
                it.uzytkownik = ""
                continue
            if new != it.uzytkownik:
                it.uzytkownik = new
                if note:
                    notes.append(note)
        return sorted(set(notes))


# --- odczyt / zapis -----------------------------------------------------------------
def load_people(ws, rows_fn) -> dict[str, Person]:
    by_h = {h: a for a, h in PEOPLE_COLUMNS}
    out: dict[str, Person] = {}
    for row in rows_fn(ws):
        kw, extra = {}, {}
        for h, v in row.items():
            a = by_h.get(h)
            if a:
                kw[a] = "" if v is None else str(v).strip()
            elif h:
                extra[h] = v
        if not kw.get("nazwa"):
            continue
        p = Person(**kw)
        p.extra = extra
        out[p.nazwa] = p
    return out


def write_people(ws, people: dict[str, Person], style_fn) -> None:
    ws.append([h for _, h in PEOPLE_COLUMNS])
    for p in sorted(people.values(), key=lambda p: _ascii(p.nazwa)):
        ws.append([getattr(p, a) for a, _ in PEOPLE_COLUMNS])
    style_fn(ws, widths={"Osoba": 28, "Funkcja": 18, "Aliasy": 50, "Uwagi": 30, "Nie łączyć z": 30})
