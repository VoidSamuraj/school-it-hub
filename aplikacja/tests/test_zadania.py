from datetime import date

from wolnesale.core.ewidencja import merge
from wolnesale.core.sprzet import Inventory, Item
from wolnesale.core.zadania import (CEL_SALE, GlobalTask, Task, next_id, progress_summary, set_done,
                                    targets)


def make_inv(tmp_path) -> Inventory:
    inv = Inventory(tmp_path / "z.xlsx")
    items = [Item(id=f"A{k}", kategoria="Komputer", sala="11W") for k in range(8)]       # pracownia IT
    items += [Item(id=f"L{k}", kategoria="Laptop", sala="4") for k in range(7)]          # IT (laptopy)
    items += [Item(id="N1", kategoria="Komputer", sala="12"),                            # PC nauczyciela
              Item(id="P1", kategoria="Projektor", sala="12"),
              Item(id="Z1", kategoria="Komputer", sala="36-ZAPL"),                       # zaplecze — pomijamy
              Item(id="W1", kategoria="Komputer", sala="11W", status="wycofany")]        # wycofany — pomijamy
    merge(inv, items)
    return inv


def test_targets_scopes(tmp_path):
    inv = make_inv(tmp_path)
    g_all = GlobalTask("G1", "Aktualizacja Windows", kategorie="Komputer, Laptop", sale="wszystkie")
    assert len(targets(inv, g_all)) == 16
    g_it = GlobalTask("G2", "Antywirus", kategorie="Komputer, Laptop", sale="sale IT")
    assert {i.sala for i in targets(inv, g_it)} == {"11W", "4"}
    g_list = GlobalTask("G3", "Office", kategorie="Komputer", sale="12, 11w")
    assert len(targets(inv, g_list)) == 9
    g_rooms = GlobalTask("G4", "Sprawdź projektor", cel=CEL_SALE, sale="wszystkie")
    assert targets(inv, g_rooms, plan_rooms=["11W", "12", "4", "D1"]) == ["4", "12", "11W", "D1"]


def test_progress_and_save(tmp_path):
    inv = make_inv(tmp_path)
    g = GlobalTask("G1", "Aktualizacja", kategorie="Komputer", sale="sale IT")
    inv.global_tasks.append(g)
    for k in range(3):
        set_done(inv, "G1", f"A{k}", True)
    set_done(inv, "G1", "A0", False)
    set_done(inv, "G1", "A1", True)            # drugi raz — bez duplikatu
    done, total, rooms = progress_summary(inv, g)
    assert (done, total) == (2, 8) and rooms[0].room == "11W"
    inv.tasks.append(Task("Z1", "Wymienić toner", sala="39W", termin="2026-01-01"))
    inv.save()
    back = Inventory.load(tmp_path / "z.xlsx")
    assert back.global_tasks[0].tytul == "Aktualizacja" and back.global_tasks[0].active
    assert {p.cel for p in back.progress} == {"A1", "A2"}
    t = back.tasks[0]
    assert t.sala == "39W" and t.overdue(date(2026, 2, 1)) and not t.overdue(date(2025, 12, 1))


def test_next_id():
    assert next_id("Z", ["Z1", "Z7", "X3"]) == "Z8"
    assert next_id("G", []) == "G1"
