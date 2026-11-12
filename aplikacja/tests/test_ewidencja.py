from pathlib import Path

import pytest

from wolnesale.core.ewidencja import (guess_category, guess_project, import_files, merge,
                                      parse_location, parse_single)
from wolnesale.core.sprzet import (NIEPEWNA, NIEZNANA, PEWNA, SERWIS, WYPOZYCZONY, Inventory,
                                   Item)

DANE = Path(__file__).resolve().parents[2] / "dane"      # <projekt>\dane


@pytest.mark.parametrize("text, sala, ewid, user", [
    ("16.0", "16", "16", ""),
    ("04W", "4W", "4W", ""),
    ("24A", "24A", "24A", ""),
    ("36-ZAPL", "36-ZAPL", "36-ZAPL", ""),
    ("08W-ZAPL", "8W-ZAPL", "8W-ZAPL", ""),
    ("29/ w 12", "12", "29", ""),
    ("10W/ w 16", "16", "10W", ""),
    ("4B/w 8B-ZAPL", "8B-ZAPL", "4B", ""),
    ("36-ZAPL/w 4", "4", "36-ZAPL", ""),
    ("30W/w 21W od 23.09.25", "21W", "30W", ""),
    ("16 (jest w 39W) - do LT", "39W", "16", ""),
    ("02W (jest w 14W Kowalski J.)", "14W", "2W", "Kowalski J."),
    ("12W użytkuje Nowak Jan", "12W", "12W", "Nowak Jan"),
    ("w 22 użytkuje Dyrektor", "22", "22", "Dyrektor"),
    ("21 Wiśniewska A.", "21", "21", "Wiśniewska A."),
    ("28Zieliński Piotr", "28", "28", "Zieliński Piotr"),
    ("zestaw w 09W", "9W", "9W", ""),
    ("w 11W", "11W", "11W", ""),
    ("01 - korytarz szkolny", "Korytarz", "", ""),
])
def test_parse_single(text, sala, ewid, user):
    loc = parse_single(text)
    assert (loc.sala, loc.sala_ewid, loc.uzytkownik) == (sala, ewid, user)


def test_parse_single_status_and_uncertain():
    assert parse_single("11W (w naprawie)").status == SERWIS
    loc = parse_single("z 16/użyczona do archiwum")
    assert loc.status == WYPOZYCZONY and loc.sala_ewid == "16" and loc.pewnosc != PEWNA
    loc = parse_single("w bursie wychowawcy (z 16)")
    assert loc.sala == "Bursa (inne)" and loc.sala_ewid == "16" and loc.pewnosc == NIEPEWNA
    assert parse_single("").pewnosc == NIEZNANA
    loc = parse_single("26 użytkuje Lewandowska Ewa/ w 16")
    assert (loc.sala, loc.sala_ewid, loc.uzytkownik, loc.pewnosc) == ("16", "26", "Lewandowska Ewa", NIEPEWNA)


def test_parse_location_pieces_with_people():
    res = parse_location("16/ od IX 2024 1 szt. Wójcik A. nr ser.SN0000000001, "
                         "1 szt. Kamińska Anna nr ser. SN0000000002, 1 szt. 16 nr ser. SN0000000003", 3)
    assert sum(n for n, _ in res) == 3
    assert "1" not in [l.sala for _, l in res]
    assert any(l.uzytkownik.startswith("Kamińska") for _, l in res)


def test_parse_location_lists():
    res = parse_location("6, 2 w 10W, 31W", 4)
    assert [(n, l.sala) for n, l in res] == [(1, "6"), (2, "10W"), (1, "31W")]
    res = parse_location("16 w 10W", 16)
    assert [(n, l.sala) for n, l in res] == [(16, "10W")]
    res = parse_location("16.0", 3)
    assert [(n, l.sala) for n, l in res] == [(3, "16")]
    res = parse_location("29, 23", 3)  # brakuje jednej sztuki
    assert sum(n for n, _ in res) == 3 and res[-1][1].pewnosc == NIEZNANA


def test_categories_and_projects():
    assert guess_category("Chromebook HP Fortis", "Laptopy.xls", "Chromebooki") == "Chromebook"
    assert guess_category("Monitor interaktywny Avtek", "Tablice.xls", "x") == "Tablica / monitor interaktywny"
    assert guess_category("Serwer DELL T130", "Komputery.xls", "x") == "Serwer"
    assert guess_category("Coś dziwnego", "Skanery stan.xls", "zestawienie") == "Skaner"
    assert guess_project("Komputery stan ŚT.xls", "x") == "ŚT"
    assert guess_project("Laptopy.xls", "Laptopy KPO 22 12 2025") == "KPO"
    assert guess_project("Komputery.xls", "zestawienie") == "PŚT"


def test_merge_keeps_user_fields(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [Item(id="A", nazwa="PC", sala="12", sala_ewid="12", opis_ewid="12")])
    inv.update("A", sala="14", uzytkownik="Kowalski")
    rep = merge(inv, [Item(id="A", nazwa="PC Dell", sala="12", sala_ewid="12", opis_ewid="12/w 13"),
                      Item(id="B", nazwa="Monitor", sala="5")])
    a = inv.items["A"]
    assert (a.nazwa, a.sala, a.uzytkownik, a.opis_ewid) == ("PC Dell", "14", "Kowalski", "12/w 13")
    assert rep.added == ["B"] and rep.changed_desc
    rep2 = merge(inv, [Item(id="B", nazwa="Monitor", sala="5")])
    assert rep2.missing == ["A"] and inv.items["A"].w_ewidencji == "nie"


def test_room_kind(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    items = [Item(id=f"P{k}", kategoria="Komputer", sala="11W") for k in range(8)]
    items += [Item(id="N", kategoria="Komputer", sala="12"), Item(id="M", kategoria="Monitor", sala="13"),
              Item(id="Z", kategoria="Komputer", sala="13-ZAPL")]
    merge(inv, items)
    assert (inv.pc_count("11W"), inv.room_kind("11W")) == (8, "it")
    assert (inv.pc_count("12"), inv.room_kind("12")) == (1, "pc")
    assert (inv.pc_count("13"), inv.room_kind("13")) == (0, "")
    merge(inv, [Item(id=f"L{k}", kategoria="Laptop", sala="4") for k in range(16)]
          + [Item(id=f"T{k}", kategoria="Tablet", sala="5") for k in range(10)])
    assert (inv.pc_count("4"), inv.room_kind("4")) == (16, "it")      # laptopy też się liczą
    assert inv.room_kind("5") == ""                                    # tablety nie
    inv.ensure_rooms(["12"])
    inv.rooms[0]["Typ"] = "komputerowa"          # ręczny typ ma pierwszeństwo
    assert inv.room_kind("12") == "it"


def test_save_load_roundtrip(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [Item(id="A", nazwa="PC", sala="12", wartosc=100.5)])
    inv.update("A", sala="11w", status="serwis")
    inv.ensure_rooms(["12", "11W", "36-ZAPL", "Korytarz"])
    inv.items["A"].extra["Moja kolumna"] = "xyz"
    inv.save(backup_dir=tmp_path / "kopie")
    inv.save(backup_dir=tmp_path / "kopie")
    back = Inventory.load(tmp_path / "z.xlsx")
    a = back.items["A"]
    assert (a.sala, a.status, a.wartosc, a.extra["Moja kolumna"]) == ("11W", "serwis", 100.5, "xyz")
    assert [e.zdarzenie for e in back.history] == ["przeniesienie", "serwis"]
    assert sorted(r["Sala"] for r in back.rooms) == ["11W", "12"]
    assert len(list((tmp_path / "kopie").glob("*.xlsx"))) == 1


@pytest.mark.skipif(not list(DANE.glob("*.xls")), reason="brak lokalnych plików ewidencji")
def test_real_files():
    items, rep = import_files(list(DANE.glob("*.xls")))
    assert len(rep.files) == 14
    assert 700 <= rep.items <= 760
    by_id = {i.id: i for i in items}
    # 13 komputerów pod jednym numerem rozbitych na sztuki
    assert sum(1 for i in items if i.inv == "PŚT/00405") == 13
    assert by_id["PŚT/00113"].sala == "12" and by_id["PŚT/00113"].sala_ewid == "29"
    with_room = sum(1 for i in items if i.sala)
    assert with_room / len(items) > 0.95
