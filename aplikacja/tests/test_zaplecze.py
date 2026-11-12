from openpyxl import load_workbook

from wolnesale.core.ewidencja import merge
from wolnesale.core.sprzet import Inventory, Item
from wolnesale.core.zaplecze import (Material, guess_model, materials_for, missing_slots,
                                     printer_models, printers, printers_for, stock_change, to_buy,
                                     unassigned_printers)


def make_inv(tmp_path) -> Inventory:
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [
        Item(id="D1", kategoria="Drukarka", nazwa="Drukarka HP LaserJet Pro 400 M401dne", sala="11W"),
        Item(id="D2", kategoria="Drukarka", nazwa="Drukarka HP LaserJet P2055dn", sala="16"),
        Item(id="D3", kategoria="Urządzenie wielofunkcyjne", nazwa="Brother MFC-L2710DW", sala="24"),
        Item(id="D4", kategoria="Drukarka", nazwa="Drukarka HP M401", sala="12", status="wycofany"),
        Item(id="K1", kategoria="Komputer", nazwa="Dell", sala="11W"),
    ])
    inv.materials = {
        "CF280X": Material("CF280X", "Toner HP 80X", pasuje_do="M401, M425", ilosc=0, minimum=2),
        "CE505A": Material("CE505A", "Toner HP 05A", pasuje_do="P2055", ilosc=3, minimum=1),
        "TN2420": Material("TN2420", "Toner Brother", pasuje_do="MFC-L27", ilosc=1, minimum=2),
        "STARY": Material("STARY", "Toner do niczego", pasuje_do="XYZ999", ilosc=0, minimum=0),
    }
    return inv


def test_guess_model():
    assert guess_model("Drukarka HP LaserJet Pro 400 M401dne") == "M401dne"
    assert guess_model("Drukarka HP LaserJet P2055dn") == "P2055dn"
    assert guess_model("Drukarka HP 2015") == ""            # sam rok to nie model
    assert guess_model("Brother MFC-L2710DW") == "MFC-L2710DW"


def test_brand_and_label(tmp_path):
    from wolnesale.core.zaplecze import guess_brand
    assert guess_brand("Kserokopiarka CANON IR 2520") == "Canon"
    assert guess_brand("Drukarka laserowa Hewlett Packard LaserJet Pro 400") == "HP"
    assert guess_brand("Urządzenie wielofunkcyjne TASKALFA 3011") == "Kyocera"
    assert guess_brand("Kserokopiarka Konica Minolta Develop ineo 227") == "Konica Minolta"
    assert guess_brand("Drukarka fiskalna") == ""
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [Item(id="A", kategoria="Kserokopiarka", nazwa="Kserokopiarka CANON IR 2520", sala="1W"),
                Item(id="B", kategoria="Drukarka", nazwa="Drukarka fiskalna", sala="8WA")])
    labels = {g.label for g in printer_models(inv)}
    assert labels == {"Canon 2520", "Drukarka fiskalna"}


def test_matching(tmp_path):
    inv = make_inv(tmp_path)
    assert [p.id for p in printers(inv)] == ["D2", "D3", "D1"]       # wg sal; bez komputera i wycofanej
    assert [m.kod for m in materials_for(inv, inv.items["D1"])] == ["CF280X"]
    assert [p.id for p in printers_for(inv, inv.materials["CF280X"])] == ["D1"]


def test_to_buy_and_unassigned(tmp_path):
    inv = make_inv(tmp_path)
    buy = {b.material.kod: b for b in to_buy(inv)}
    assert set(buy) == {"CF280X", "TN2420"}          # CE505A ok, STARY bez drukarek i minimum 0
    assert "brak na stanie" in buy["CF280X"].reason
    inv.materials.pop("CE505A")
    assert [p.id for p in unassigned_printers(inv)] == ["D2"]


def test_color_schemes(tmp_path):
    inv = Inventory(tmp_path / "z.xlsx")
    merge(inv, [
        Item(id="A", kategoria="Drukarka", nazwa="Brother DCP-L5500DN", sala="28"),
        Item(id="B", kategoria="Drukarka", nazwa="Brother DCP-L5500DN", sala="5W"),
        Item(id="C", kategoria="Drukarka", nazwa="Brother MFC-L8690CDW", sala="19"),
        Item(id="E", kategoria="Drukarka", nazwa="HP DeskJet 3835", sala="39"),
    ])
    inv.materials = {
        "TN3480": Material("TN3480", pasuje_do="DCP-L5500", kolor="czarny", ilosc=2),
        "TN423BK": Material("TN423BK", pasuje_do="MFC-L8690", kolor="czarny", ilosc=1),
        "TN423C": Material("TN423C", pasuje_do="MFC-L8690", kolor="cyan", ilosc=0),
        "HP652BK": Material("HP652BK", pasuje_do="3835", kolor="", ilosc=1),
    }
    inv.model_schemes["3835"] = "czarny + kolor"
    by = {g.model: g for g in printer_models(inv)}
    assert len(by["DCP-L5500DN"].printers) == 2                          # agregacja: ile drukarek
    assert (by["DCP-L5500DN"].scheme, by["DCP-L5500DN"].missing) == ("tylko czarny", [])
    g = by["MFC-L8690CDW"]
    assert g.scheme == "CMYK (4 osobne)" and g.scheme_guessed           # odgadnięty z kolorów
    assert g.missing == ["magenta", "żółty"] and g.empty == ["cyan"]
    e = by["3835"]
    assert not e.scheme_guessed and e.missing == ["kolor (zestaw)"]     # ustawiony ręcznie
    assert ("3835", "kolor (zestaw)") in [(m.model, c) for m, c in missing_slots(inv)]
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx")
    assert back.model_schemes == {"3835": "czarny + kolor"}


def test_usage_forecast(tmp_path):
    from datetime import date, datetime
    inv = make_inv(tmp_path)
    inv.materials["CE505A"].ilosc = 10
    today = date(2026, 11, 1)
    # 6 wymian w ~5 miesięcy, w dwóch salach (w tym wpisy wsteczne bez zmiany stanu)
    for d, sala in [("2026-06-01", "16"), ("2026-07-01", "26"), ("2026-08-01", "16"),
                    ("2026-09-01", "26"), ("2026-10-01", "16"), ("2026-10-31", "26")]:
        stock_change(inv, "CE505A", -1, sala=sala, when=datetime.fromisoformat(d), change_stock=False)
    assert inv.materials["CE505A"].ilosc == 10                      # wpisy wsteczne nie ruszają stanu
    from wolnesale.core.zaplecze import suggested_buy, usage
    u = usage(inv, "CE505A", today=today)
    assert len(u.replacements) == 6 and not u.few_data
    assert 1.1 < u.per_month < 1.3                                    # ~6 szt. / 153 dni
    assert 240 < u.days_left < 270                                    # 10 szt. wystarczy na ~8 miesięcy
    assert 55 < u.by_room["16"] < 70                                  # w sali 16 co ~2 miesiące
    assert suggested_buy(inv, inv.materials["CE505A"]) >= 1
    inv.materials["CE505A"].ilosc = 1                                 # 1 szt. ≈ 25 dni -> ostrzeżenie
    assert "wg zużycia" in {b.material.kod: b for b in to_buy(inv)}["CE505A"].reason


def test_stock_change_and_save(tmp_path):
    inv = make_inv(tmp_path)
    stock_change(inv, "CE505A", -1, sala="16", opis="wymiana")
    stock_change(inv, "CF280X", +5)
    stock_change(inv, "TN2420", -9)                  # nie schodzi poniżej zera
    assert (inv.materials["CE505A"].ilosc, inv.materials["CF280X"].ilosc, inv.materials["TN2420"].ilosc) == (2, 5, 0)
    inv.other_sheets["Moje notatki"] = [["a", "b"], [1, 2]]
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx")
    assert back.materials["CE505A"].ilosc == 2 and back.materials["CF280X"].pasuje_do == "M401, M425"
    ev = [e for e in back.history if e.id == "zaplecze:CE505A"][0]
    assert (ev.zdarzenie, ev.z, ev.do, ev.opis) == ("wydanie", "3", "2", "1 szt. · sala 16 · wymiana")
    assert back.other_sheets["Moje notatki"] == [["a", "b"], [1, 2]]
    assert "Zaplecze" in load_workbook(tmp_path / "z.xlsx").sheetnames
