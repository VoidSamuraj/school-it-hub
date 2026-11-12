"""Przypisanie urządzenia do sali albo osoby, wypożyczenia, zwroty i historia lokalizacji."""
from datetime import date

from wolnesale.core.ewidencja import merge
from wolnesale.core.sprzet import (NA_STALE, OK, POZA_SZKOLA, WYPOZYCZENIE, WYPOZYCZONY, Inventory,
                                   Item)


def make(tmp_path) -> Inventory:
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [Item(id="L1", kategoria="Laptop", nazwa="Laptop HP", sala="36-ZAPL"),
                Item(id="P1", kategoria="Projektor", nazwa="Epson", sala="12")])
    return inv


def test_move_keeps_person(tmp_path):
    inv = make(tmp_path)
    inv.move_to("P1", "14w", "projektor do warsztatu")
    assert inv.items["P1"].where == "14W"
    e = inv.location_history("P1")[-1]
    assert (e.zdarzenie, e.z, e.do, e.opis) == ("przeniesienie", "12", "14W", "projektor do warsztatu")


def test_hand_over_and_return(tmp_path):
    inv = make(tmp_path)
    # wypożyczenie do domu z datą zwrotu
    inv.hand_over("L1", "Nowak Jan", POZA_SZKOLA, WYPOZYCZENIE, until="2026-11-20", note="praca zdalna")
    it = inv.items["L1"]
    assert (it.uzytkownik, it.sala, it.status, it.przydzial) == ("Nowak Jan", POZA_SZKOLA, WYPOZYCZONY, WYPOZYCZENIE)
    assert it.where == "Nowak Jan · Poza szkołą"
    assert it.overdue(date(2026, 11, 21)) and not it.overdue(date(2026, 11, 19))
    e = inv.location_history("L1")[-1]
    assert e.zdarzenie == "wypożyczenie" and e.z == "36-ZAPL" and "zwrot do 2026-11-20" in e.opis
    assert inv.room_before_handover("L1") == "36-ZAPL"
    # zwrot do sali
    inv.take_back("L1", "36-zapl", "bez uwag")
    assert (it.uzytkownik, it.sala, it.status, it.przydzial, it.zwrot) == ("", "36-ZAPL", OK, "", "")
    assert [e.zdarzenie for e in inv.location_history("L1")] == ["wypożyczenie", "zwrot"]


def test_permanent_assignment_in_room(tmp_path):
    inv = make(tmp_path)
    inv.hand_over("L1", "Kowalska Anna", "24", NA_STALE, until="2027-01-01")
    it = inv.items["L1"]
    assert (it.where, it.status, it.zwrot) == ("Kowalska Anna · 24", OK, "")   # na stałe: bez zwrotu
    assert not it.overdue(date(2030, 1, 1))
    inv.move_to("L1", "33")                                                    # nauczycielka zmienia salę
    assert it.where == "Kowalska Anna · 33"
    assert inv.people() == ["Kowalska Anna"]


def test_fields_saved(tmp_path):
    inv = make(tmp_path)
    inv.hand_over("L1", "Nowak Jan", POZA_SZKOLA, WYPOZYCZENIE, until="2026-12-01")
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx").items["L1"]
    assert (back.przydzial, back.zwrot, back.sala) == (WYPOZYCZENIE, "2026-12-01", POZA_SZKOLA)
