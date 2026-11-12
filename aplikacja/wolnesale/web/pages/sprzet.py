"""Ekran „Spis sprzętu”: drzewko lokalizacji, tabela z filtrami, edycja, przenoszenie, import ewidencji."""
from __future__ import annotations

import copy
import os
from datetime import date, datetime, timedelta

from nicegui import run, ui

from ...core.ewidencja import import_files, merge
from ...core.osoby import RECZNIE, Registry
from ...core.sale import BUILDINGS, building, is_room, normalize_room, sort_key
from ...core.sprzet import (NA_STALE, NIEPEWNA, NIEZNANA, OK, PC_CATEGORIES, PEWNA, PEWNOSCI,
                            LOCATION_EVENTS, POZA_SZKOLA, SERWIS, STATUSY, WYCOFANY, WYPOZYCZENIE,
                            WYPOZYCZONY, Item)
from ..app import nav_set
from ..state import S
from ..theme import BCOL, badge, card, esc, page_header, set_on

ST_COL = {OK: ("#dcfce7", "#15803d"), SERWIS: ("#dbeafe", "#1d4ed8"), WYPOZYCZONY: ("#ede9fe", "#6d28d9"),
          WYCOFANY: ("#e5e7eb", "#4b5563")}
PEW_COL = {PEWNA: ("#f1f5f9", "#475569"), NIEPEWNA: ("#fef3c7", "#b45309"), NIEZNANA: ("#ffedd5", "#c2410c")}

COLUMNS = [
    {"name": "id", "label": "ID", "field": "id", "sortable": True, "align": "left"},
    {"name": "kategoria", "label": "Kategoria", "field": "kategoria", "sortable": True, "align": "left"},
    {"name": "nazwa", "label": "Nazwa", "field": "nazwa", "sortable": True, "align": "left",
     "style": "max-width:340px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"},
    {"name": "sala", "label": "Sala", "field": "sala", "sortable": True, "align": "left"},
    {"name": "pewnosc", "label": "Lokalizacja", "field": "pewnosc", "sortable": True, "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "sortable": True, "align": "left"},
    {"name": "uzytkownik", "label": "U kogo", "field": "uzytkownik", "sortable": True, "align": "left"},
    {"name": "sprawdzono", "label": "Sprawdzono", "field": "sprawdzono", "sortable": True, "align": "left"},
]

PILL_SLOT = r"""
<q-td :props="props">
  <span class="ws-st" :style="{background: props.row.{key}_bg, color: props.row.{key}_fg}">{{ props.value }}</span>
</q-td>
"""


def unsure(i: Item) -> bool:
    return i.pewnosc != PEWNA or not i.sala


def row_of(i: Item) -> dict:
    sb, sf = ST_COL.get(i.status, ST_COL[OK])
    pb, pf = PEW_COL.get(i.pewnosc, PEW_COL[PEWNA]) if i.sala else PEW_COL[NIEZNANA]
    return {"id": i.id, "kategoria": i.kategoria, "nazwa": i.nazwa, "sala": i.sala or "?",
            "pewnosc": i.pewnosc if i.sala else NIEZNANA, "status": i.status, "uzytkownik": who(i),
            "sprawdzono": i.sprawdzono,
            "status_bg": sb, "status_fg": sf, "pewnosc_bg": pb, "pewnosc_fg": pf}


def who(i: Item) -> str:
    """Kolumna „U kogo”: osoba, rodzaj przydziału, termin zwrotu (⏰ gdy po terminie)."""
    if not i.uzytkownik:
        return ""
    if i.przydzial == WYPOZYCZENIE:
        return f"{'⏰ ' if i.overdue() else ''}👤 {i.uzytkownik} · do {i.zwrot or '?'}"
    return f"👤 {i.uzytkownik} · na stałe"


def locations() -> list[str]:
    return sorted(set(S.inv.locations()) | set(S.plan_rooms()), key=sort_key)


def save_and_report() -> bool:
    err = S.save_inventory()
    if err:
        ui.notify(err, type="warning", timeout=8000, close_button=True)
        return False
    return True


def build(sala: str | None = None):
    nav_set("/sprzet")
    st = {"sel": ("loc", normalize_room(sala)) if sala else ("all",), "q": "", "kat": set(), "status": None,
          "proj": None}

    with ui.column().classes("ws-page"):
        actions = page_header("Spis sprzętu", f"{len(S.inv.items)} szt.")
        with actions:
            # przyciski działają też przy pustym spisie (wtedy reszta ekranu się nie buduje)
            ui.button("Importuj ewidencję", icon="upload", on_click=import_dialog) \
                .props("unelevated color=primary")
            with ui.button(icon="more_vert").props("flat round"):
                with ui.menu():
                    ui.menu_item("Otwórz zasoby.xlsx w Excelu", on_click=open_excel)
                    ui.menu_item("Wczytaj ponownie (po edycji w Excelu)", on_click=lambda: (
                        S.reload_inventory(), ui.navigate.reload()))

        if not S.inv.items:
            with card():
                ui.label("Spis jest pusty").classes("text-xl font-bold")
                ui.label("Kliknij „Importuj ewidencję” i wybierz zestawienia .xls od księgowej "
                         "(można zaznaczyć wszystkie naraz).").classes("ws-mut")
            return

        with ui.tabs().props("no-caps align=left active-color=primary indicator-color=primary") \
                .classes("w-full") as tabs:
            t_items = ui.tab("sprzet", label="🖥 Sprzęt")
            t_hist = ui.tab("historia", label="📜 Historia zmian")
        with ui.tab_panels(tabs, value=t_items).classes("w-full bg-transparent"):
            with ui.tab_panel(t_items).classes("p-0"):
                with ui.row().classes("w-full gap-5 items-start no-wrap"):
                    with card().style("width:290px;flex:none"):
                        tree_box = ui.column().classes("w-full")
                    with ui.column().classes("flex-1 gap-4 min-w-0"):
                        with card():
                            with ui.row().classes("items-center gap-3 w-full"):
                                ui.input(placeholder="Szukaj: nazwa, nr inw., użytkownik, uwagi…",
                                         on_change=lambda e: (st.update(q=e.value or ""), fill())) \
                                    .props("outlined dense rounded clearable").classes("flex-1 min-w-[220px]")
                                kat = ui.select([], label="Kategorie (można kilka)", multiple=True, clearable=True,
                                                on_change=lambda e: (st.update(kat=set(e.value or [])), fill())) \
                                    .props("outlined dense options-dense use-chips").classes("min-w-[240px] max-w-[420px]")
                                ui.button("💻 Komputery", on_click=lambda: kat.set_value(
                                    sorted(c for c in PC_CATEGORIES if c in kat.options))) \
                                    .props("flat dense no-caps color=primary") \
                                    .tooltip("Komputery + laptopy + chromebooki")
                                stat = ui.select(STATUSY, label="Status", clearable=True,
                                                 on_change=lambda e: (st.update(status=e.value), fill())) \
                                    .props("outlined dense options-dense").classes("w-36")
                                proj = ui.select([], label="Projekt", clearable=True,
                                                 on_change=lambda e: (st.update(proj=e.value), fill())) \
                                    .props("outlined dense options-dense").classes("w-32")
                        with card():
                            table = ui.table(columns=COLUMNS, rows=[], row_key="id", selection="multiple",
                                             pagination={"rowsPerPage": 25, "sortBy": None}) \
                                .props("flat dense table-header-class=text-grey-7").classes("w-full")
                            for key in ("status", "pewnosc"):
                                table.add_slot(f"body-cell-{key}", PILL_SLOT.replace("{key}", key))
                            table.on("rowClick", lambda e: edit_dialog(e.args[1]["id"], refresh_all))
                            with ui.row().classes("items-center gap-2 w-full mt-2"):
                                move_b = ui.button("Przenieś zaznaczone", icon="move_up",
                                                   on_click=lambda: move_dialog([r["id"] for r in table.selected], refresh_all)) \
                                    .props("unelevated no-caps color=primary")
                                check_b = ui.button("Sprawdzone dziś", icon="fact_check", on_click=lambda: mark_checked()) \
                                    .props("outline no-caps color=primary")
                                ui.space()
                                count = ui.label().classes("ws-mut")
                            ui.label("Kliknij wiersz, żeby edytować. Zaznacz kilka, żeby przenieść je naraz.") \
                                .classes("ws-mut text-sm")
            with ui.tab_panel(t_hist).classes("p-0"):
                history = history_panel(lambda iid: edit_dialog(iid, refresh_all))

        def update_buttons():
            n = len(table.selected)
            move_b.set_enabled(n > 0)
            check_b.set_enabled(n > 0)
            move_b.text = f"Przenieś zaznaczone ({n})" if n else "Przenieś zaznaczone"
        table.on_select(lambda _: update_buttons())

        def mark_checked():
            today = date.today().isoformat()
            for r in table.selected:
                S.inv.update(r["id"], sprawdzono=today, pewnosc=PEWNA)
            if save_and_report():
                ui.notify(f"Oznaczono {len(table.selected)} szt. jako sprawdzone", type="positive")
            table.selected.clear()
            refresh_all()

        def visible() -> list[Item]:
            key, q = st["sel"], st["q"].strip().lower()
            out = []
            for i in S.inv.items.values():
                if key[0] == "people" and not i.uzytkownik:
                    continue
                if key[0] == "overdue" and not i.overdue():
                    continue
                if key[0] == "unsure" and not unsure(i):
                    continue
                if key[0] == "building" and (not i.sala or building(i.sala) != key[1]):
                    continue
                if key[0] == "loc" and i.sala != key[1]:
                    continue
                if st["kat"] and i.kategoria not in st["kat"]:
                    continue
                if st["status"] and i.status != st["status"]:
                    continue
                if st["proj"] and i.projekt != st["proj"]:
                    continue
                if q and q not in " ".join([i.id, i.nazwa, i.uzytkownik, i.uwagi, i.opis_ewid, i.sala,
                                             i.kategoria]).lower():
                    continue
                out.append(i)
            out.sort(key=lambda i: (sort_key(i.sala) if i.sala else (99,), i.kategoria, i.id))
            return out

        def fill():
            items = visible()
            table.rows = [row_of(i) for i in items]
            table.selected.clear()
            table.update()
            count.text = f"{len(items)} szt."
            update_buttons()

        def tree():
            items = list(S.inv.items.values())
            by_loc: dict[str, int] = {}
            for i in items:
                by_loc[i.sala] = by_loc.get(i.sala, 0) + 1
            nodes = [{"id": "all", "label": f"📦 Wszystko · {len(items)}"},
                     {"id": "people", "label": f"👤 U osób · {sum(1 for i in items if i.uzytkownik)}"},
                     {"id": "unsure", "label": f"❓ Do sprawdzenia · {sum(unsure(i) for i in items)}"}]
            n_over = sum(1 for i in items if i.overdue())
            if n_over:
                nodes.insert(2, {"id": "overdue", "label": f"⏰ Po terminie zwrotu · {n_over}"})
            for b in BUILDINGS:
                locs = sorted((l for l in by_loc if l and building(l) == b), key=sort_key)
                if not locs:
                    continue
                nodes.append({"id": f"b|{b}", "label": f"{b} · {sum(by_loc[l] for l in locs)}",
                              "children": [{"id": f"l|{l}",
                                            "label": f"{l.replace('-ZAPL', ' · zaplecze')} · {by_loc[l]}"}
                                           for l in locs]})
            if by_loc.get(""):
                nodes.append({"id": "l|", "label": f"⚠ Bez lokalizacji · {by_loc['']}"})
            tree_box.clear()
            sel = st["sel"]
            sel_id = {"all": "all", "unsure": "unsure", "people": "people", "overdue": "overdue"}.get(sel[0]) or (
                f"b|{sel[1]}" if sel[0] == "building" else f"l|{sel[1]}")

            def on_sel(e):
                v = e.value
                if not v:
                    return
                if v in ("all", "unsure", "people", "overdue"):
                    st["sel"] = (v,)
                elif v.startswith("b|"):
                    st["sel"] = ("building", v[2:])
                else:
                    st["sel"] = ("loc", v[2:])
                fill()

            with tree_box:
                t = ui.tree(nodes, label_key="label", on_select=on_sel).classes("ws-tree w-full") \
                    .props("selected-color=primary no-transition")
                t.select(sel_id)
                if sel[0] == "loc" and sel[1]:
                    t.expand([f"b|{building(sel[1])}"])
                elif sel[0] == "building":
                    t.expand([f"b|{sel[1]}"])

        def refresh_all():
            items = list(S.inv.items.values())
            kat.options = sorted({i.kategoria for i in items if i.kategoria})
            kat.update()
            proj.options = sorted({i.projekt for i in items if i.projekt})
            proj.update()
            tree()
            fill()
            history.refresh()

        refresh_all()


EVENT_COL = {"przeniesienie": ("#e0e7ff", "#4338ca"), "serwis": ST_COL[SERWIS],
             "powrót z serwisu": ST_COL[OK], "wypożyczenie": ST_COL[WYPOZYCZONY], "zwrot": ST_COL[OK],
             "wycofanie": ST_COL[WYCOFANY], "wydanie": ("#fef3c7", "#b45309")}
KINDS = {"all": "Wszystko", "move": "Lokalizacja (przeniesienia, wydania, zwroty)", "status": "Serwis / status",
         "other": "Inne"}
PERIODS = {7: "7 dni", 30: "30 dni", 365: "rok", 0: "całość"}
STATUS_EVENTS = {"serwis", "powrót z serwisu", "wycofanie", "zmiana statusu"}

HIST_COLUMNS = [
    {"name": "data", "label": "Kiedy", "field": "data", "sortable": True, "align": "left"},
    {"name": "zdarzenie", "label": "Co", "field": "zdarzenie", "sortable": True, "align": "left"},
    {"name": "z", "label": "Z", "field": "z", "align": "left"},
    {"name": "do", "label": "Do", "field": "do", "align": "left"},
    {"name": "id", "label": "ID", "field": "id", "sortable": True, "align": "left"},
    {"name": "nazwa", "label": "Urządzenie", "field": "nazwa", "align": "left",
     "style": "max-width:320px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"},
    {"name": "opis", "label": "Opis", "field": "opis", "align": "left"},
]
EVENT_SLOT = r"""
<q-td :props="props">
  <span class="ws-st" :style="{background: props.row.ev_bg, color: props.row.ev_fg}">{{ props.value }}</span>
</q-td>
"""
ARROW_SLOT = r"""
<q-td :props="props"><b>{{ props.value }}</b></q-td>
"""


def history_panel(open_item):
    """Dziennik zmian sprzętu: przeniesienia, serwis, wypożyczenia… — z filtrami."""
    hs = {"kind": "all", "room": None, "days": 30, "q": ""}

    with card():
        with ui.row().classes("items-start gap-x-8 gap-y-4 w-full ws-filters"):
            def seg(title, options, key):
                with ui.column().classes("gap-0"):
                    ui.html(f'<span class="ws-flabel">{title}</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        btns = {}
                        for k, label in options.items():
                            def setk(k=k):
                                hs[key] = k
                                for kk, b in btns.items():
                                    set_on(b, kk == k)
                                body.refresh()
                            btns[k] = ui.button(label, on_click=setk).props("flat dense no-caps")
                            set_on(btns[k], k == hs[key])
            seg("Rodzaj zmiany", KINDS, "kind")
            seg("Okres", PERIODS, "days")
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Sala (z albo do)</span>', sanitize=False)
                ui.select(locations(), label="", with_input=True, clearable=True,
                          on_change=lambda e: (hs.update(room=e.value), body.refresh())) \
                    .props("outlined dense options-dense").classes("w-40")
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Szukaj</span>', sanitize=False)
                ui.input(placeholder="ID, nazwa, opis…",
                         on_change=lambda e: (hs.update(q=e.value or ""), body.refresh())) \
                    .props("outlined dense rounded clearable").classes("w-60")

    @ui.refreshable
    def body():
        since = (date.today() - timedelta(days=hs["days"])).isoformat() if hs["days"] else ""
        q = hs["q"].strip().lower()
        room = normalize_room(hs["room"]) if hs["room"] else None
        rows = []
        for e in S.inv.history:
            if e.id.startswith(("zaplecze:", "zadanie:")):
                continue
            ev = e.zdarzenie
            if hs["kind"] == "move" and ev not in LOCATION_EVENTS:
                continue
            if hs["kind"] == "status" and ev not in STATUS_EVENTS:
                continue
            if hs["kind"] == "other" and (ev in LOCATION_EVENTS or ev in STATUS_EVENTS):
                continue
            if since and e.data[:10] < since:
                continue
            if room and ev in LOCATION_EVENTS and not any(room == s.split(" · ")[-1] for s in (e.z, e.do)):
                continue
            if room and ev not in LOCATION_EVENTS:
                it = S.inv.items.get(e.id)
                if not it or it.sala != room:
                    continue
            it = S.inv.items.get(e.id)
            name = f"{it.kategoria} · {it.nazwa}" if it else ""
            if q and q not in f"{e.id} {name} {e.opis} {e.z} {e.do}".lower():
                continue
            bg, fg = EVENT_COL.get(ev, ("#f1f5f9", "#475569"))
            rows.append({"key": f"{e.data}|{e.id}|{len(rows)}", "data": e.data, "zdarzenie": ev,
                         "z": e.z or "—", "do": e.do or "—", "id": e.id, "nazwa": name, "opis": e.opis,
                         "ev_bg": bg, "ev_fg": fg})
        rows.sort(key=lambda r: r["data"], reverse=True)
        n_moves = sum(1 for r in rows if r["zdarzenie"] in LOCATION_EVENTS)
        with card():
            ui.label(f"{len(rows)} zmian · w tym {n_moves} zmian lokalizacji").classes("ws-mut text-sm")
            if not rows:
                ui.label("Brak zmian w wybranym okresie. Każde przeniesienie, serwis czy wypożyczenie "
                         "zapisuje się tu automatycznie.").classes("ws-mut mt-2")
                return
            t = ui.table(columns=HIST_COLUMNS, rows=rows, row_key="key",
                         pagination={"rowsPerPage": 50, "sortBy": "data", "descending": True}) \
                .props("flat dense table-header-class=text-grey-7").classes("w-full")
            t.add_slot("body-cell-zdarzenie", EVENT_SLOT)
            t.add_slot("body-cell-do", ARROW_SLOT)
            t.on("rowClick", lambda ev: open_item(ev.args[1]["id"]) if ev.args[1]["id"] in S.inv.items else None)
            ui.label("Kliknij wiersz, żeby otworzyć urządzenie.").classes("ws-mut text-sm mt-1")

    body()
    return body


def open_excel():
    if not S.inv_path.exists():
        ui.notify("Spisu jeszcze nie ma — najpierw zaimportuj ewidencję.")
        return
    ui.notify("Po zmianach w Excelu zapisz i zamknij plik, potem „Wczytaj ponownie”.", timeout=8000)
    from ...ustawienia import open_in_system
    open_in_system(S.inv_path)


def where_html(it: Item) -> str:
    """„Gdzie jest teraz”: sala albo osoba + miejsce, z rodzajem przydziału i terminem zwrotu."""
    place = it.sala or "?"
    place_html = ("🏠 " + esc(POZA_SZKOLA) if place == POZA_SZKOLA else
                  f'🚪 {badge(place) if is_room(place) else esc(place)}')
    if not it.uzytkownik:
        return f'<div style="font-size:16px;display:flex;gap:8px;align-items:center">{place_html}</div>'
    kind = it.przydzial or NA_STALE
    extra = ""
    if kind == WYPOZYCZENIE:
        over = it.overdue()
        extra = (f' · zwrot do <b style="color:{"#b91c1c" if over else "inherit"}">{esc(it.zwrot or "?")}</b>'
                 + (' <b style="color:#b91c1c">(po terminie!)</b>' if over else ""))
    return (f'<div style="font-size:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
            f'<span>👤 <b>{esc(it.uzytkownik)}</b></span><span>{place_html}</span></div>'
            f'<div class="ws-mut" style="font-size:13px;margin-top:2px">{esc(kind)}{extra}</div>')


def edit_dialog(item_id: str, after):
    it = S.inv.items[item_id]

    def done(msg: str):
        if save_and_report():
            ui.notify(msg, type="positive")
        dlg.close()
        after()

    with ui.dialog() as dlg, ui.card().classes("w-[680px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.html(f'<div style="font-size:19px;font-weight:700">{esc(it.nazwa)}</div>'
                f'<div class="ws-mut">{esc(it.kategoria)} · nr inw. <b>{esc(it.inv)}</b> · projekt {esc(it.projekt)}'
                f' · przyjęty {esc(it.data or "?")}'
                f'{f" · {it.wartosc:.2f} zł" if it.wartosc else ""}</div>'
                + ("" if it.w_ewidencji == "tak" else
                   '<div style="margin-top:6px;color:#c2410c;font-weight:600">'
                   'nie ma go w ostatnim zestawieniu od księgowej</div>'), sanitize=False)

        # --- gdzie jest teraz + akcje
        with ui.element("div").classes("w-full").style("background:#f5f6fd;border-radius:14px;padding:12px 14px"):
            ui.html('<span class="ws-flabel">Gdzie jest teraz</span>' + where_html(it), sanitize=False)
            def then(action):
                # okno urządzenia zamykamy, akcja otwiera własne; po niej wracamy do odświeżonego urządzenia
                dlg.close()
                # nowe okno otwieramy chwilę później i poza zamkniętym oknem — inaczej Quasar go nie pokaże
                with ui.context.client.content:
                    ui.timer(0.3, lambda: action(it.id, lambda: (after(), reopen())), once=True)

            def reopen():
                with ui.context.client.content:
                    edit_dialog(it.id, after)

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Przenieś", icon="move_up",
                          on_click=lambda: then(lambda i, a: move_dialog([i], a))) \
                    .props("unelevated dense no-caps color=primary")
                ui.button("Wydaj osobie / wypożycz", icon="person_add",
                          on_click=lambda: then(handover_dialog)) \
                    .props("outline dense no-caps color=primary")
                if it.uzytkownik:
                    ui.button("Zwrot", icon="assignment_return",
                              on_click=lambda: then(return_dialog)) \
                        .props("outline dense no-caps color=positive")

        # --- pozostałe pola
        with ui.grid(columns=3).classes("w-full gap-3"):
            status = ui.select([s for s in STATUSY if s != WYPOZYCZONY or it.status == WYPOZYCZONY],
                               value=it.status, label="Status").props("outlined dense")
            pew = ui.select(PEWNOSCI, value=it.pewnosc, label="Pewność lokalizacji").props("outlined dense")
            with ui.row().classes("items-center gap-1 no-wrap"):
                checked = ui.input("Sprawdzono", value=it.sprawdzono).props("outlined dense").classes("flex-1")
                ui.button("dziś", on_click=lambda: checked.set_value(date.today().isoformat())) \
                    .props("flat dense no-caps color=primary")
        notes = ui.textarea("Notatka", value=it.uwagi).props("outlined dense autogrow").classes("w-full")

        # --- historia lokalizacji (oś czasu) + inne zmiany
        loc = S.inv.location_history(it.id)
        ui.html('<span class="ws-flabel" style="margin-top:4px">Historia lokalizacji</span>', sanitize=False)
        if not loc:
            ui.label("Jeszcze nie przenoszono — jest tu od importu ewidencji.").classes("ws-mut text-sm")
        else:
            rows = "".join(
                f'<div style="display:grid;grid-template-columns:120px 1fr;gap:10px;padding:6px 0;'
                f'border-top:1px solid var(--line)"><span class="ws-mut" style="font-size:13px">{esc(e.data)}</span>'
                f'<div><span class="ws-st" style="background:{EVENT_COL.get(e.zdarzenie, ("#f1f5f9", "#475569"))[0]};'
                f'color:{EVENT_COL.get(e.zdarzenie, ("#f1f5f9", "#475569"))[1]}">{esc(e.zdarzenie)}</span> '
                f'{esc(e.z or "—")} → <b>{esc(e.do or "—")}</b>'
                f'{f"<div class=ws-mut style=font-size:12.5px>{esc(e.opis)}</div>" if e.opis else ""}</div></div>'
                for e in reversed(loc))
            ui.html(rows, sanitize=False).classes("w-full max-h-56 overflow-auto")
        other = [e for e in S.inv.item_history(it.id) if e not in loc]
        if other:
            with ui.expansion(f"Inne zmiany ({len(other)})", icon="history").classes("w-full"):
                for e in reversed(other):
                    ui.html(f'<div style="padding:3px 0"><span class="ws-mut">{esc(e.data)}</span> · '
                            f'<b>{esc(e.zdarzenie)}</b> {esc(e.z)} → {esc(e.do)} '
                            f'<span class="ws-mut">{esc(e.opis)}</span></div>', sanitize=False)

        def save():
            S.inv.update(it.id, pewnosc=pew.value, status=status.value,
                         sprawdzono=(checked.value or "").strip(), uwagi=(notes.value or "").strip())
            done("Zapisano")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Zamknij", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.open()


def move_dialog(ids: list[str], after):
    if not ids:
        return
    with ui.dialog() as dlg, ui.card().classes("w-[480px] rounded-2xl p-6 gap-3"):
        ui.label(f"Przenieś {len(ids)} szt." if len(ids) > 1 else "Przenieś do innej sali").classes("text-xl font-bold")
        target = ui.select(locations() + [POZA_SZKOLA], label="Dokąd", with_input=True,
                           new_value_mode="add-unique").props("outlined").classes("w-full")
        note = ui.input("Notatka (opcjonalnie)", placeholder="np. na czas remontu sali").props("outlined dense") \
            .classes("w-full")
        if any(S.inv.items[i].uzytkownik for i in ids):
            ui.label("Przypisanie do osoby zostaje — zmienia się tylko miejsce. "
                     "Żeby oddać sprzęt do sali, użyj „Zwrot”.").classes("ws-hint")

        def go():
            if not target.value:
                ui.notify("Wybierz, dokąd")
                return
            for iid in ids:
                S.inv.move_to(iid, str(target.value).strip(), (note.value or "").strip())
                S.inv.items[iid].pewnosc = PEWNA
            if save_and_report():
                ui.notify(f"Przeniesiono {len(ids)} szt. → {target.value}", type="positive")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Przenieś", icon="move_up", on_click=go).props("unelevated no-caps color=primary")
    dlg.open()


def handover_dialog(item_id: str, after):
    it = S.inv.items[item_id]
    with ui.dialog() as dlg, ui.card().classes("w-[520px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Wydaj osobie / wypożycz").classes("text-xl font-bold")
        ui.label(f"{it.kategoria} · {it.nazwa}").classes("ws-mut")
        opts = {n: (f"{n} · {S.inv.osoby[n].funkcja}" if n in S.inv.osoby and S.inv.osoby[n].funkcja else n)
                for n in S.inv.people()}
        person = ui.select(opts, value=it.uzytkownik or None, label="Komu (z rejestru osób albo wpisz nową)",
                           with_input=True, new_value_mode="add-unique").props("outlined dense").classes("w-full")
        kind = ui.toggle({WYPOZYCZENIE: "⏳ Wypożyczenie (na czas)", NA_STALE: "📌 Na stałe (np. służbowy)"},
                         value=it.przydzial or WYPOZYCZENIE).props("no-caps rounded unelevated toggle-color=primary")
        until = ui.input("Zwrot do", value=it.zwrot or (date.today() + timedelta(days=14)).isoformat()) \
            .props("outlined dense type=date").classes("w-full")
        ui.html('<span class="ws-flabel">Gdzie będzie</span>', sanitize=False)
        here = it.sala if it.sala and it.sala != POZA_SZKOLA else None
        place_kind = ui.toggle({"home": "🏠 Poza szkołą (dom)", "room": "🚪 W sali"},
                               value="room" if (it.uzytkownik and it.sala != POZA_SZKOLA) else "home") \
            .props("no-caps rounded unelevated toggle-color=primary")
        room = ui.select(locations(), value=here, label="Sala", with_input=True,
                         new_value_mode="add-unique").props("outlined dense").classes("w-full")
        note = ui.input("Notatka", placeholder="np. na praktyki, z zasilaczem i torbą").props("outlined dense") \
            .classes("w-full")

        def vis(*_):
            until.set_visibility(kind.value == WYPOZYCZENIE)
            room.set_visibility(place_kind.value == "room")
        kind.on_value_change(vis)
        place_kind.on_value_change(vis)
        vis()

        def go():
            if not person.value:
                ui.notify("Wpisz, komu")
                return
            if place_kind.value == "room" and not room.value:
                ui.notify("Wybierz salę")
                return
            place = POZA_SZKOLA if place_kind.value == "home" else str(room.value)
            who_name = str(person.value)
            if who_name not in S.inv.osoby:      # wpisana ręcznie: dopasuj do rejestru albo dodaj nową osobę
                who_name = Registry(S.inv).resolve(who_name, RECZNIE)[0] or who_name
            S.inv.hand_over(it.id, who_name, place, kind.value,
                            until.value if kind.value == WYPOZYCZENIE else "", (note.value or "").strip())
            if save_and_report():
                ui.notify(f"{'Wypożyczono' if kind.value == WYPOZYCZENIE else 'Wydano'}: {who_name}",
                          type="positive")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="person_add", on_click=go).props("unelevated no-caps color=primary")
    dlg.open()


def return_dialog(item_id: str, after):
    it = S.inv.items[item_id]
    with ui.dialog() as dlg, ui.card().classes("w-[480px] rounded-2xl p-6 gap-3"):
        ui.label("Zwrot").classes("text-xl font-bold")
        ui.html(f'<div class="ws-mut">Od: 👤 <b>{esc(it.uzytkownik)}</b> · {esc(it.sala or "?")}</div>', sanitize=False)
        room = ui.select(locations(), value=S.inv.room_before_handover(it.id) or None, label="Wraca do sali",
                         with_input=True, new_value_mode="add-unique").props("outlined dense").classes("w-full")
        note = ui.input("Notatka", placeholder="np. bez uszkodzeń / brak zasilacza").props("outlined dense") \
            .classes("w-full")

        def go():
            if not room.value:
                ui.notify("Wybierz salę, do której wraca")
                return
            S.inv.take_back(it.id, str(room.value), (note.value or "").strip())
            if save_and_report():
                ui.notify(f"Zwrócono → {room.value}", type="positive")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zwrot", icon="assignment_return", on_click=go).props("unelevated no-caps color=positive")
    dlg.open()


def import_dialog(*_):
    with ui.dialog() as dlg, ui.card().classes("w-[820px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Import ewidencji").classes("text-xl font-bold")
        ui.label("Wybierz zestawienia z księgowości (.xls/.xlsx) — możesz zaznaczyć wszystkie naraz. "
                 "Twoje zmiany (sala, osoba, status, notatki) nie zostaną nadpisane.").classes("ws-mut")
        body = ui.column().classes("w-full")

        async def on_multi(e):
            folder = S.ewidencja_upload_dir()
            paths = []
            for f in e.files:
                p = folder / f.name
                await f.save(p)
                paths.append(p)
            body.clear()
            with body:
                ui.spinner(size="lg")
            items, rep = await run.io_bound(import_files, paths, "ewidencja: zgadza się")
            preview = copy.deepcopy(S.inv)
            mrep = merge(preview, items)
            first = not S.inv.items
            preg = Registry(preview)
            preg.sync_plan(S.tt.teachers if S.tt else [])
            person_notes = preg.normalize_items()
            body.clear()
            with body:
                stats = [("plików", len(rep.files)), ("sztuk", rep.items), ("do sprawdzenia", len(rep.uncertain)),
                         ("rozbite numery", len(rep.split_rows)), ("duplikaty", len(rep.duplicates))]
                if not first:
                    stats += [("nowe", len(mrep.added)), ("zmieniony opis", len(mrep.changed_desc)),
                              ("zniknęły", len(mrep.missing))]
                with ui.row().classes("gap-3 flex-wrap"):
                    for label, n in stats:
                        ui.html(f'<div style="background:#f1f3f9;border-radius:12px;padding:8px 14px">'
                                f'<div style="font-size:20px;font-weight:700">{n}</div>'
                                f'<div class="ws-mut" style="font-size:12px">{label}</div></div>', sanitize=False)
                lines = []
                if rep.warnings:
                    lines += ["⚠️ Ostrzeżenia:"] + ["   " + w for w in rep.warnings] + [""]
                if not first:
                    for title, lst in (("✏ Zmienił się opis w ewidencji:", mrep.changed_desc),
                                       ("➖ Nie ma ich w nowym zestawieniu:", mrep.missing),
                                       ("🆕 Nowe:", mrep.added)):
                        if lst:
                            lines += [title] + ["   " + s for s in lst] + [""]
                if person_notes:
                    lines += ["👥 Osoby — ujednolicone wg rejestru osób (sprawdzisz i scalisz w zakładce Osoby):"] + \
                             ["   " + s for s in person_notes] + [""]
                lines += ["❓ Lokalizacja do sprawdzenia:"] + ["   " + s for s in rep.uncertain] + [""]
                lines += ["✂ Numery z kilkoma sztukami (rozbite na #1, #2…):"] + ["   " + s for s in rep.split_rows]
                ui.code("\n".join(lines), language="text").classes("w-full max-h-80 overflow-auto")

                def do_import():
                    merge(S.inv, items)
                    reg = Registry(S.inv)
                    reg.sync_plan(S.tt.teachers if S.tt else [])
                    reg.normalize_items()
                    S.inv.ensure_rooms(S.plan_rooms() + S.inv.locations())
                    if save_and_report():
                        ui.notify(f"Zaimportowano — spis: {len(S.inv.items)} szt.", type="positive")
                    dlg.close()
                    ui.navigate.reload()        # pełne odświeżenie — ekran pustego spisu musi się przebudować

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
                    ui.button("Importuj", icon="download_done", on_click=do_import) \
                        .props("unelevated no-caps color=primary")

        ui.upload(multiple=True, auto_upload=True, on_multi_upload=on_multi) \
            .props('accept=".xls,.xlsx" flat bordered label="Przeciągnij pliki albo kliknij +"').classes("w-full")
    dlg.open()
