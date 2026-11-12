from wolnesale.core.model import Lesson, Period, Timetable
from wolnesale.core.plany import PlanStore, diff_plans
from wolnesale.core.wolne import find_free, free_windows


def make_tt(busy: list[tuple[str, int, int]]) -> Timetable:
    periods = [Period(n, f"{7 + n}:00", f"{7 + n}:45") for n in range(1, 9)]
    lessons = [Lesson(d, p, r, "mat", "1a", "", "Nauczyciel") for (r, d, p) in busy]
    return Timetable(periods=periods, days=[0, 1, 2, 3, 4], lessons=lessons)


def test_whole_day_free():
    tt = make_tt([("12", 0, 1)])
    ws = free_windows(tt, "11W", 0)
    assert [(w.first, w.last) for w in ws] == [(1, 8)]


def test_windows_split_by_lessons():
    tt = make_tt([("12", 0, 3), ("12", 0, 4), ("12", 0, 7)])
    ws = free_windows(tt, "12", 0)
    assert [(w.first, w.last) for w in ws] == [(1, 2), (5, 6), (8, 8)]


def test_range_limits():
    tt = make_tt([("12", 0, 3)])
    ws = free_windows(tt, "12", 0, first=2, last=5)
    assert [(w.first, w.last) for w in ws] == [(2, 2), (4, 5)]


def test_find_free_min_length_and_order():
    tt = make_tt([("12", 0, 3), ("11W", 0, 5)])
    res = find_free(tt, ["12", "11W"], [0], first=2, last=6, min_length=3)
    assert [(w.room, w.first, w.last) for w in res] == [("12", 4, 6), ("11W", 2, 4)]


def test_time_label():
    tt = make_tt([])
    w = free_windows(tt, "12", 0, first=2, last=3)[0]
    assert w.time_label(tt) == "9:00–10:45"


def test_store_roundtrip_and_diff(tmp_path):
    old = make_tt([("12", 0, 1)])
    new = make_tt([("12", 0, 1), ("12", 0, 2), ("5W", 1, 1)])
    pdf = tmp_path / "plan.pdf"
    pdf.write_bytes(b"%PDF-fake")
    store = PlanStore(tmp_path / "program" / "plan.json", tmp_path / "kopie" / "plany",
                      tmp_path / "zrodla" / "plany")
    store.activate(old, pdf)
    store.activate(new, pdf)
    loaded = store.load_active()
    assert loaded.lessons == new.lessons
    assert len(store.versions()) == 1
    assert list((tmp_path / "zrodla" / "plany").glob("*plan.pdf"))      # kopia PDF-a w źródłach
    # PDF już leżący w źródłach nie jest kopiowany drugi raz
    inside = tmp_path / "zrodla" / "plany" / "wgrany.pdf"
    inside.write_bytes(b"%PDF")
    assert store.activate(new, inside) == inside
    d = {x.room: (x.before, x.after) for x in diff_plans(old, new)}
    assert d == {"12": (1, 2), "5W": (0, 1)}


def test_migrate_old_layout(tmp_path):
    from wolnesale.ustawienia import Paths, migrate_old_layout
    root = tmp_path / "dane"
    (root / "plany" / "archiwum").mkdir(parents=True)
    (root / "plany" / "aktywny.json").write_text("{}")
    (root / "plany" / "archiwum" / "2026_poprzedni.json").write_text("{}")
    (root / "plany" / "archiwum" / "2026_plan.pdf").write_bytes(b"%PDF")
    (root / "zasoby.xlsx").write_bytes(b"x")
    (root / "kopie").mkdir()
    (root / "kopie" / "zasoby_2026.xlsx").write_bytes(b"x")
    (root / "przyjete" / "ewidencja_2026").mkdir(parents=True)
    (root / "moje.xls").write_bytes(b"x")                       # plik użytkownika — zostaje
    p = Paths(root)
    moved = migrate_old_layout(p)
    p.ensure()
    assert p.plan.exists() and p.zasoby.exists()
    assert (p.kopie_plany / "2026_poprzedni.json").exists()
    assert (p.zrodla_plany / "2026_plan.pdf").exists()
    assert (p.kopie_zasoby / "zasoby_2026.xlsx").exists()
    assert (p.zrodla_ewidencja / "ewidencja_2026").is_dir()
    assert (root / "moje.xls").exists() and not (root / "plany").exists()
    assert len(moved) == 6
    assert migrate_old_layout(p) == []                            # drugi raz nic nie robi
