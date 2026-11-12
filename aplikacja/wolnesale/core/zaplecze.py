"""Zaplecze: materiały eksploatacyjne (tusze, tonery, bębny…) i ich powiązanie z drukarkami.

Materiał ma pole „Pasuje do” — słowa kluczowe modeli oddzielone przecinkami (np. „M402, M426”).
Drukarka pasuje, gdy któreś słowo występuje w jej nazwie ze spisu sprzętu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from .sprzet import Inventory, Item

SHEET_MATERIALS = "Zaplecze"
PRINTER_CATEGORIES = {"Drukarka", "Urządzenie wielofunkcyjne", "Kserokopiarka", "Ploter"}
MATERIAL_TYPES = ["toner", "tusz", "bęben", "papier", "inne"]
COLORS = ["", "czarny", "cyan", "magenta", "żółty", "kolor (zestaw)"]

# atrybut -> nagłówek w Excelu
MATERIAL_COLUMNS: list[tuple[str, str]] = [
    ("kod", "Kod"),
    ("nazwa", "Nazwa"),
    ("typ", "Typ"),
    ("kolor", "Kolor"),
    ("pasuje_do", "Pasuje do (modele)"),
    ("ilosc", "Ilość"),
    ("minimum", "Minimum"),
    ("lokalizacja", "Gdzie leży"),
    ("uwagi", "Uwagi"),
]


@dataclass
class Material:
    kod: str
    nazwa: str = ""
    typ: str = "toner"
    kolor: str = ""
    pasuje_do: str = ""
    ilosc: int = 0
    minimum: int = 1
    lokalizacja: str = ""
    uwagi: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def keywords(self) -> list[str]:
        return [k.strip().lower() for k in re.split(r"[,;]", self.pasuje_do) if k.strip()]

    def fits(self, printer: "Item") -> bool:
        name = f"{printer.nazwa} {printer.uwagi}".lower()
        return any(k in name for k in self.keywords)

    @property
    def label(self) -> str:
        parts = [self.kod]
        if self.kolor:
            parts.append(self.kolor)
        return " · ".join(parts)


def is_printer(it: "Item") -> bool:
    from .sprzet import WYCOFANY
    return it.kategoria in PRINTER_CATEGORIES and it.status != WYCOFANY


BRANDS = [("hewlett packard", "HP"), ("hp", "HP"), ("brother", "Brother"), ("canon", "Canon"),
          ("konica minolta", "Konica Minolta"), ("konica", "Konica Minolta"), ("develop", "Develop"),
          ("xerox", "Xerox"), ("epson", "Epson"), ("kyocera", "Kyocera"), ("taskalfa", "Kyocera"),
          ("lexmark", "Lexmark"), ("samsung", "Samsung"), ("ricoh", "Ricoh"), ("oki", "OKI"),
          ("evolis", "Evolis"), ("bambu", "Bambu Lab"), ("makerbot", "MakerBot")]


def guess_brand(name: str) -> str:
    """Producent z nazwy ze spisu: 'Kserokopiarka CANON IR 2520' -> 'Canon'."""
    low = f" {name.lower()} "
    for key, brand in BRANDS:
        if re.search(rf"(?<![a-ząćęłńóśźż]){re.escape(key)}(?![a-ząćęłńóśźż])", low):
            return brand
    return ""


def guess_model(name: str) -> str:
    """Najbardziej „modelowy” fragment nazwy: 'Drukarka HP LaserJet Pro 400 M401dne' -> 'M401dne'."""
    name = re.split(r"\(?\s*nr\.?\s*ser", name, flags=re.IGNORECASE)[0]   # bez numerów seryjnych
    name = re.sub(r"\b\d{1,2}\.\d{1,2}\b", " ", name)                       # bez dat typu 12.4
    toks = re.findall(r"(?:[A-Za-z]+-)?[A-Za-z]*\d[\w\-]*", name)
    toks = [t for t in toks if len(t) >= 3 and not re.fullmatch(r"(19|20)\d\d", t)]
    if not toks:
        return ""
    # preferuj tokeny z literami i cyframi, potem dłuższe
    return max(toks, key=lambda t: (bool(re.search(r"[A-Za-z]", t)), len(t)))


@dataclass
class BuyEntry:
    material: Material | None
    reason: str
    printers: list = field(default_factory=list)   # drukarki, których dotyczy


def printers(inv: "Inventory") -> list["Item"]:
    from .sale import sort_key
    out = [i for i in inv.items.values() if is_printer(i)]
    out.sort(key=lambda i: (sort_key(i.sala) if i.sala else (99,), i.nazwa))
    return out


def printers_for(inv: "Inventory", m: Material) -> list["Item"]:
    return [p for p in printers(inv) if m.fits(p)]


def materials_for(inv: "Inventory", printer: "Item") -> list[Material]:
    return [m for m in inv.materials.values() if m.fits(printer)]


def to_buy(inv: "Inventory") -> list[BuyEntry]:
    """Co warto dokupić: brak / poniżej minimum / wg prognozy zapas skończy się w ciągu LEAD_DAYS dni."""
    out = []
    for m in sorted(inv.materials.values(), key=lambda m: (m.ilosc - m.minimum, m.kod)):
        ps = printers_for(inv, m)
        u = usage(inv, m.kod)
        forecast = ""
        if u.days_left is not None:
            forecast = f"zapas na ok. {int(u.days_left)} dni (do ~{u.runout:%d.%m})"
        if m.ilosc <= 0 and ps:
            out.append(BuyEntry(m, "brak na stanie, a drukarki go używają", ps))
        elif m.ilosc < m.minimum:
            out.append(BuyEntry(m, f"poniżej minimum ({m.ilosc} z {m.minimum})"
                                   + (f" · {forecast}" if forecast else ""), ps))
        elif u.days_left is not None and u.days_left < LEAD_DAYS:
            out.append(BuyEntry(m, f"wg zużycia: {forecast}", ps))
    return out


def suggested_buy(inv: "Inventory", m: Material, months: float = 3) -> int:
    """Ile kupić, żeby wystarczyło na ~`months` miesięcy (nie mniej niż do minimum)."""
    u = usage(inv, m.kod)
    need_min = max(m.minimum - m.ilosc, 0)
    if u.per_month:
        need_rate = round(u.per_month * months - m.ilosc + 0.49)
        return max(need_min, need_rate, 1)
    return max(need_min, 1)


# --- schematy kolorów (jakie gniazda ma dany model) -----------------------------
CZARNY, CYAN, MAGENTA, ZOLTY, KOLOR = "czarny", "cyan", "magenta", "żółty", "kolor (zestaw)"
SCHEMES: dict[str, list[str]] = {
    "tylko czarny": [CZARNY],
    "czarny + kolor": [CZARNY, KOLOR],
    "CMYK (4 osobne)": [CZARNY, CYAN, MAGENTA, ZOLTY],
    "nie dotyczy": [],              # np. drukarka 3D, fiskalna, ploter z innym systemem
}
# czytelne opisy do wyboru w programie (klucze zostają w Excelu)
SCHEME_LABELS: dict[str, str] = {
    "tylko czarny": "1 wkład — tylko czarny",
    "czarny + kolor": "2 wkłady — czarny + kolorowy (trójkolorowy)",
    "CMYK (4 osobne)": "4 wkłady — czarny, cyan, magenta, żółty",
    "nie dotyczy": "bez tuszu/tonera (np. drukarka 3D, fiskalna)",
}
SCHEME_SHORT: dict[str, str] = {
    "tylko czarny": "1 wkład · czarny",
    "czarny + kolor": "2 wkłady · czarny + kolor",
    "CMYK (4 osobne)": "4 wkłady · CMYK",
    "nie dotyczy": "bez wkładów",
}
SHEET_MODELS = "Modele drukarek"
MODEL_COLUMNS = ["Model", "Kolory", "Uwagi"]


def material_color(m: Material) -> str:
    return m.kolor or CZARNY


@dataclass
class Slot:
    color: str
    materials: list            # materiały pasujące do tego gniazda

    @property
    def stock(self) -> int:
        return sum(m.ilosc for m in self.materials)

    @property
    def defined(self) -> bool:
        return bool(self.materials)


@dataclass
class PrinterModel:
    model: str                     # np. "M401dne" (albo pełna nazwa, gdy nie da się odgadnąć)
    printers: list
    materials: list
    scheme: str = ""               # klucz z SCHEMES; "" = nieznany
    scheme_guessed: bool = False   # schemat odgadnięty z przypisanych materiałów, nie ustawiony ręcznie
    brand: str = ""                # producent, np. "Canon"

    @property
    def label(self) -> str:
        """Nazwa do wyświetlenia: 'Canon 2520' (gdy model to tylko fragment nazwy)."""
        if self.brand and self.brand.lower() not in self.model.lower():
            return f"{self.brand} {self.model}"
        return self.model

    @property
    def key(self) -> str:
        return self.model.upper()

    @property
    def rooms(self) -> list[str]:
        return sorted({p.sala or "?" for p in self.printers})

    @property
    def slots(self) -> list[Slot]:
        """Gniazda wg schematu; materiały bez pasującego gniazda trafiają do dodatkowych."""
        colors = SCHEMES.get(self.scheme, [])
        slots = [Slot(c, [m for m in self.materials if material_color(m) == c]) for c in colors]
        used = {m.kod for s in slots for m in s.materials}
        extra = [m for m in self.materials if m.kod not in used]
        for m in extra:
            slots.append(Slot(material_color(m), [m]))
        return slots

    @property
    def missing(self) -> list[str]:
        """Kolory, dla których nie zdefiniowano żadnego tuszu/tonera."""
        return [s.color for s in self.slots if not s.defined]

    @property
    def empty(self) -> list[str]:
        """Kolory zdefiniowane, ale z zerowym stanem."""
        return [s.color for s in self.slots if s.defined and s.stock == 0]


def guess_scheme(materials: list[Material]) -> str:
    colors = {material_color(m) for m in materials}
    if colors & {CYAN, MAGENTA, ZOLTY}:
        return "CMYK (4 osobne)"
    if KOLOR in colors:
        return "czarny + kolor"
    if colors:
        return "tylko czarny"
    return ""


def printer_models(inv: "Inventory") -> list[PrinterModel]:
    """Drukarki pogrupowane wg modelu, z pasującymi materiałami i schematem kolorów."""
    groups: dict[str, list] = {}
    for p in printers(inv):
        key = guess_model(p.nazwa) or p.nazwa
        groups.setdefault(key.upper(), []).append(p)
    out = []
    for key, ps in groups.items():
        model = guess_model(ps[0].nazwa) or ps[0].nazwa
        mats = {m.kod: m for p in ps for m in materials_for(inv, p)}
        mats_l = sorted(mats.values(), key=lambda m: (list(COLORS).index(m.kolor) if m.kolor in COLORS else 9, m.kod))
        scheme = inv.model_schemes.get(key, "")
        brand = next((b for b in (guess_brand(p.nazwa) for p in ps) if b), "")
        g = PrinterModel(model, ps, mats_l, scheme, brand=brand)
        if not scheme:
            g.scheme, g.scheme_guessed = guess_scheme(mats_l), True
        out.append(g)
    out.sort(key=lambda g: (g.scheme == "nie dotyczy", not g.missing and bool(g.scheme), -len(g.printers),
                            g.model.lower()))
    return out


def missing_slots(inv: "Inventory") -> list[tuple[PrinterModel, str]]:
    """(model, kolor) bez zdefiniowanego materiału — tylko dla modeli ze znanym schematem."""
    return [(g, c) for g in printer_models(inv) if g.scheme for c in g.missing]


def unassigned_printers(inv: "Inventory") -> list["Item"]:
    """Drukarki, dla których nie ma w zapleczu żadnego materiału."""
    return [p for p in printers(inv) if not materials_for(inv, p)]


def stock_change(inv: "Inventory", kod: str, delta: int, sala: str = "", opis: str = "",
                 when: "datetime | None" = None, change_stock: bool = True) -> Material:
    """Przyjęcie (+) lub wydanie (−) wkładu; zapis w historii (z datą — także wsteczną).

    change_stock=False: tylko wpis o wymianie (np. uzupełnianie historii z przeszłości), stan bez zmian.
    """
    m = inv.materials[kod]
    before = m.ilosc
    if change_stock:
        m.ilosc = max(0, m.ilosc + delta)
    if delta > 0:
        ev = "przyjęcie"
    else:
        ev = "wydanie" if change_stock else "wymiana (wpis wsteczny)"
    n = abs(delta)
    parts = [f"{n} szt."] + ([f"sala {sala}"] if sala else []) + ([opis] if opis else [])
    inv.log(f"zaplecze:{kod}", ev, str(before), str(m.ilosc), " · ".join(parts), when=when)
    return m


# --- zużycie i prognoza --------------------------------------------------------------
USAGE_WINDOW_DAYS = 365      # bierzemy wymiany z ostatniego roku
LEAD_DAYS = 45               # ostrzegaj, gdy zapasu zostało na mniej niż tyle dni
MIN_SPAN_DAYS = 30


@dataclass
class Replacement:
    when: "datetime"
    count: int
    sala: str


@dataclass
class Usage:
    replacements: list            # Replacement, od najstarszej
    per_month: float | None       # średnio sztuk na miesiąc
    days_left: float | None       # na ile dni wystarczy obecny zapas
    runout: "date | None"         # przewidywany dzień wyczerpania
    few_data: bool                # mniej niż 3 wymiany — prognoza orientacyjna
    by_room: dict                 # sala -> średnio co ile dni wymiana (gdy ≥2 wymiany)

    @property
    def last(self) -> "Replacement | None":
        return self.replacements[-1] if self.replacements else None


def _parse_when(s: str):
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip()[:16], fmt)
        except ValueError:
            continue
    return None


def replacements(inv: "Inventory", kod: str) -> list[Replacement]:
    out = []
    for e in inv.history:
        if e.id != f"zaplecze:{kod}" or not (e.zdarzenie.startswith("wydanie") or e.zdarzenie.startswith("wymiana")):
            continue
        when = _parse_when(e.data)
        if not when:
            continue
        m = re.match(r"\s*(\d+)\s*szt", e.opis or "")
        if m:
            n = int(m.group(1))
        else:
            try:
                n = max(int(e.z) - int(e.do), 1)
            except ValueError:
                n = 1
        s = re.search(r"sala\s+([^\s·]+)", e.opis or "")
        out.append(Replacement(when, n, s.group(1) if s else ""))
    out.sort(key=lambda r: r.when)
    return out


def usage(inv: "Inventory", kod: str, today: "date | None" = None) -> Usage:
    from datetime import date, timedelta
    today = today or date.today()
    m = inv.materials[kod]
    reps = replacements(inv, kod)
    recent = [r for r in reps if (today - r.when.date()).days <= USAGE_WINDOW_DAYS]
    by_room = {}
    rooms: dict[str, list] = {}
    for r in reps:
        if r.sala:
            rooms.setdefault(r.sala, []).append(r.when.date())
    for sala, ds in rooms.items():
        if len(ds) >= 2:
            gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
            by_room[sala] = sum(gaps) / len(gaps)
    if not recent:
        return Usage(reps, None, None, None, True, by_room)
    total = sum(r.count for r in recent)
    span = max((today - recent[0].when.date()).days, MIN_SPAN_DAYS)
    rate = total / span                       # sztuk na dzień
    days_left = m.ilosc / rate if rate > 0 else None
    runout = today + timedelta(days=int(days_left)) if days_left is not None else None
    return Usage(reps, rate * 30.4, days_left, runout, len(recent) < 3, by_room)


def load_materials(ws, rows_fn) -> dict[str, Material]:
    by_header = {h: a for a, h in MATERIAL_COLUMNS}
    out: dict[str, Material] = {}
    for row in rows_fn(ws):
        kod = str(row.get("Kod") or "").strip()
        if not kod:
            continue
        kw, extra = {}, {}
        for h, v in row.items():
            a = by_header.get(h)
            if a in ("ilosc", "minimum"):
                try:
                    kw[a] = int(float(v)) if v not in (None, "") else 0
                except (TypeError, ValueError):
                    kw[a] = 0
            elif a:
                kw[a] = "" if v is None else str(v).strip()
            elif h:
                extra[h] = v
        m = Material(**kw)
        m.extra = extra
        out[m.kod] = m
    return out


def load_models(ws, rows_fn) -> tuple[dict[str, str], dict[str, str]]:
    """Arkusz „Modele drukarek” -> ({MODEL: schemat}, {MODEL: uwagi})."""
    schemes, notes = {}, {}
    for row in rows_fn(ws):
        model = str(row.get("Model") or "").strip()
        if not model:
            continue
        s = str(row.get("Kolory") or "").strip()
        if s in SCHEMES:
            schemes[model.upper()] = s
        if row.get("Uwagi"):
            notes[model.upper()] = str(row["Uwagi"])
    return schemes, notes


def write_models(ws, schemes: dict[str, str], notes: dict[str, str]) -> None:
    ws.append(MODEL_COLUMNS)
    for key in sorted(set(schemes) | set(notes)):
        ws.append([key, schemes.get(key, ""), notes.get(key, "")])


def write_materials(ws, materials: dict[str, Material]) -> list[str]:
    extras = sorted({k for m in materials.values() for k in m.extra})
    headers = [h for _, h in MATERIAL_COLUMNS] + extras
    ws.append(headers)
    for m in sorted(materials.values(), key=lambda m: (m.typ, m.kod)):
        ws.append([getattr(m, a) for a, _ in MATERIAL_COLUMNS] + [m.extra.get(k) for k in extras])
    return headers
