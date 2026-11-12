"""Rejestr osób: czyszczenie nazwisk z ewidencji, dopasowanie do planu, duplikaty, scalanie."""
import pytest

from wolnesale.core.ewidencja import merge
from wolnesale.core.osoby import Registry, _same_person, clean_name
from wolnesale.core.sprzet import Inventory, Item

# fikcyjni nauczyciele (jak w planie aSc: „Nazwisko Imię”)
TEACHERS = ["Nowak Jan", "Kowalska Anna", "Zieliński Piotr", "Lewandowska Elżbieta", "Wójcik Izabela",
            "Kamiński Jarosław"]


@pytest.mark.parametrize("raw, name, fn", [
    ("w-ce dyr. Kowalska Anna", "Kowalska Anna", "wicedyrektor"),
    ("Gł.Księgowa Wiśniewska Ewa", "Wiśniewska Ewa", "główna księgowa"),
    ("P.Dyrektor", "", "dyrektor"),
    ("A. Wójcik w bursie", "A. Wójcik", ""),
    ("Nowak Jan nagłośnienie (jest w bursie)", "Nowak Jan", ""),
    ("Zieliński Piotr/ w 16", "Zieliński Piotr", ""),
    ("UPS", "", ""),
    ("Kowalski J.", "Kowalski J.", ""),
])
def test_clean_name(raw, name, fn):
    assert clean_name(raw) == (name, fn)


@pytest.mark.parametrize("a, b, ok", [
    ("Piotr Zieliński", "Zieliński Piotr", True),     # odwrócona kolejność
    ("Nowak J.", "Nowak Jan", True),                  # inicjał
    ("Wójcik Iza", "Wójcik Izabela", True),           # zdrobnienie
    ("Kamiński Jarek", "Kamiński Jarosław", True),
    ("Nowak Jan", "Nowak Anna", False),               # inna osoba
    ("Kowalska Anna", "Kowalski Adam", False),
])
def test_same_person(a, b, ok):
    assert bool(_same_person(a, b)) is ok


def make(tmp_path) -> Inventory:
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [
        Item(id="1", kategoria="Laptop", sala="28", uzytkownik="w-ce dyr. Kowalska Anna"),
        Item(id="2", kategoria="Laptop", sala="28", uzytkownik="Piotr Zieliński"),
        Item(id="3", kategoria="Laptop", sala="16", uzytkownik="Zieliński Piotr"),
        Item(id="4", kategoria="Monitor", sala="16", uzytkownik="UPS"),
        Item(id="5", kategoria="Laptop", sala="20", uzytkownik="Gł.Księgowa Wiśniewska Ewa"),
        Item(id="6", kategoria="Laptop", sala="21", uzytkownik="Wójcik Iza"),
    ])
    return inv


def test_sync_and_normalize(tmp_path):
    inv = make(tmp_path)
    reg = Registry(inv)
    assert reg.sync_plan(TEACHERS) == len(TEACHERS)
    notes = reg.normalize_items()
    u = {i.id: i.uzytkownik for i in inv.items.values()}
    assert u == {"1": "Kowalska Anna", "2": "Zieliński Piotr", "3": "Zieliński Piotr", "4": "",
                 "5": "Wiśniewska Ewa", "6": "Wójcik Izabela"}
    assert inv.osoby["Kowalska Anna"].funkcja == "wicedyrektor"          # funkcja z ewidencji zostaje
    assert inv.osoby["Wiśniewska Ewa"].zrodlo == "ewidencja"             # spoza planu — nowa osoba
    assert "Piotr Zieliński" in inv.osoby["Zieliński Piotr"].alias_list
    assert "z ewidencji: UPS" in inv.items["4"].uwagi                    # nie-osoba trafia do notatki
    assert any("UPS" in n for n in notes)
    # drugi raz nic się nie zmienia, alias działa od razu
    assert reg.normalize_items() == []
    assert reg.find("piotr zieliński").nazwa == "Zieliński Piotr"


def test_merge_and_not_duplicate(tmp_path):
    inv = make(tmp_path)
    reg = Registry(inv)
    reg.add("Dyrektor", "dyrektor", "ewidencja")
    reg.add("Nowak Jan", "nauczyciel", "plan")
    inv.items["4"].uzytkownik = "Dyrektor"
    # „Dyrektor” to w rzeczywistości Nowak Jan — scalamy ręcznie
    assert reg.merge("Nowak Jan", ["Dyrektor"]) == 1
    assert inv.items["4"].uzytkownik == "Nowak Jan" and "Dyrektor" not in inv.osoby
    assert reg.find("Dyrektor").nazwa == "Nowak Jan"                     # stara nazwa = alias
    assert inv.osoby["Nowak Jan"].funkcja == "nauczyciel"
    # wykrywanie duplikatów i „to różne osoby”
    reg.add("Nowak J.", "", "ewidencja")
    assert ("Nowak J.", "Nowak Jan", "inicjał imienia") in reg.duplicates()
    reg.mark_different("Nowak J.", "Nowak Jan")
    assert reg.duplicates() == []


def test_people_saved(tmp_path):
    inv = make(tmp_path)
    reg = Registry(inv)
    reg.sync_plan(TEACHERS)
    reg.normalize_items()
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx")
    assert back.osoby["Zieliński Piotr"].alias_list == ["Piotr Zieliński"]
    assert back.osoby["Kowalska Anna"].funkcja == "wicedyrektor"
    assert "Wiśniewska Ewa" in back.people()


def test_sync_plan_pomija_zaslepki(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    reg = Registry(inv)
    assert reg.sync_plan(["Brak Brak", "Wakat", "Nowak Jan"]) == 1
    assert list(inv.osoby) == ["Nowak Jan"]


def test_po_scaleniu_funkcja_trafia_do_osoby(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    reg = Registry(inv)
    reg.sync_plan(["Nowak Anna"])
    assert reg.resolve("P.Dyrektor")[0] == "Dyrektor"
    reg.merge("Nowak Anna", ["Dyrektor"])
    assert reg.resolve("P.Dyrektor")[0] == "Nowak Anna"
    assert list(inv.osoby) == ["Nowak Anna"]
