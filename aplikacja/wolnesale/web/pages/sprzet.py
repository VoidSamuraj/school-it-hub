"""Ekran „Spis sprzętu”: drzewko lokalizacji, tabela z filtrami, edycja, przenoszenie, import ewidencji."""
from __future__ import annotations

import copy
import os
from datetime import date, datetime

from nicegui import run, ui

from ...core.ewidencja import import_files, merge
from ...core.sale import BUILDINGS, building, normalize_room, sort_key
from ...core.sprzet import (NIEPEWNA, NIEZNANA, OK, PC_CATEGORIES, PEWNA, PEWNOSCI, SERWIS, STATUSY,
                            WYCOFANY, WYPOZYCZONY, Item)
from ..app import nav_set
from ..state import S
from ..theme import BCOL, card, esc, page_header

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
    {"name": "uzytkownik", "label": "Użytkownik", "field": "uzytkownik", "sortable": True, "align": "left"},
    {"name": "ewid", "label": "Wg ewidencji", "field": "ewid", "sortable": True, "align": "left"},
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
            "pewnosc": i.pewnosc if i.sala else NIEZNANA, "status": i.status, "uzytkownik": i.uzytkownik,
            "ewid": (i.sala_ewid + (" ⇄" if i.moved else "")), "sprawdzono": i.sprawdzono,
            "status_bg": sb, "status_fg": sf, "pewnosc_bg": pb, "pewnosc_fg": pf}


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
          "proj": None, "moved": False}

    with ui.column().classes("ws-page"):
        actions = page_header("Spis sprzętu", f"{len(S.inv.items)} szt.")
        with actions:
            ui.button("Importuj ewidencję", icon="upload", on_click=lambda: import_dialog(refresh_all)) \
                .props("unelevated color=primary")
            with ui.button(icon="more_vert").props("flat round"):
                with ui.menu():
                    ui.menu_item("Otwórz zasoby.xlsx w Excelu", on_click=open_excel)
                    ui.menu_item("Wczytaj ponownie (po edycji w Excelu)", on_click=lambda: (
                        S.reload_inventory(), refresh_all(), ui.notify("Wczytano spis z pliku")))

        if not S.inv.items:
            with card():
                ui.label("Spis jest pusty").classes("text-xl font-bold")
                ui.label("Kliknij „Importuj ewidencję” i wybierz zestawienia .xls od księgowej "
                         "(można zaznaczyć wszystkie naraz).").classes("ws-mut")
            return

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
                        ui.switch("tylko przeniesione", on_change=lambda e: (st.update(moved=e.value), fill()))
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
                if st["moved"] and not i.moved:
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
                     {"id": "unsure", "label": f"❓ Do sprawdzenia · {sum(unsure(i) for i in items)}"}]
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
            sel_id = {"all": "all", "unsure": "unsure"}.get(sel[0]) or (
                f"b|{sel[1]}" if sel[0] == "building" else f"l|{sel[1]}")

            def on_sel(e):
                v = e.value
                if not v:
                    return
                if v in ("all", "unsure"):
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

        refresh_all()


def open_excel():
    if not S.inv_path.exists():
        ui.notify("Spisu jeszcze nie ma — najpierw zaimportuj ewidencję.")
        return
    ui.notify("Po zmianach w Excelu zapisz i zamknij plik, potem „Wczytaj ponownie”.", timeout=8000)
    from ...ustawienia import open_in_system
    open_in_system(S.inv_path)


def edit_dialog(item_id: str, after):
    it = S.inv.items[item_id]
    with ui.dialog() as dlg, ui.card().classes("w-[620px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.html(f'<div style="font-size:19px;font-weight:700">{esc(it.nazwa)}</div>'
                f'<div class="ws-mut">{esc(it.kategoria)} · nr inw. <b>{esc(it.inv)}</b> · projekt {esc(it.projekt)}'
                f' · przyjęty {esc(it.data or "?")}'
                f'{f" · {it.wartosc:.2f} zł" if it.wartosc else ""}</div>'
                f'<div style="margin-top:8px;background:#f8fafc;border-radius:10px;padding:8px 12px" class="ws-mut">'
                f'Ewidencja: sala <b>{esc(it.sala_ewid or "?")}</b> — „{esc(it.opis_ewid)}”'
                f'{"" if it.w_ewidencji == "tak" else " · <b style=color:#c2410c>brak w ostatnim zestawieniu</b>"}'
                f'</div>', sanitize=False)
        with ui.grid(columns=2).classes("w-full gap-3"):
            sala = ui.select(locations(), value=it.sala or None, label="Sala (faktycznie)", with_input=True,
                             new_value_mode="add-unique").props("outlined dense")
            pew = ui.select(PEWNOSCI, value=it.pewnosc, label="Pewność lokalizacji").props("outlined dense")
            status = ui.select(STATUSY, value=it.status, label="Status").props("outlined dense")
            user = ui.input("Użytkownik / komu wypożyczony", value=it.uzytkownik).props("outlined dense")
            with ui.row().classes("items-center gap-2 no-wrap"):
                checked = ui.input("Sprawdzono", value=it.sprawdzono).props("outlined dense").classes("flex-1")
                ui.button("dziś", on_click=lambda: checked.set_value(date.today().isoformat())) \
                    .props("flat dense no-caps color=primary")
        notes = ui.textarea("Uwagi", value=it.uwagi).props("outlined dense autogrow").classes("w-full")
        hist = S.inv.item_history(it.id)
        with ui.expansion(f"Historia ({len(hist)})", icon="history").classes("w-full"):
            if not hist:
                ui.label("brak zmian").classes("ws-mut")
            for e in reversed(hist):
                ui.html(f'<div style="padding:3px 0"><span class="ws-mut">{esc(e.data)}</span> · <b>{esc(e.zdarzenie)}</b>'
                        f' {esc(e.z)} → {esc(e.do)} <span class="ws-mut">{esc(e.opis)}</span></div>', sanitize=False)

        def save():
            S.inv.update(it.id, sala=(sala.value or "").strip(), pewnosc=pew.value, status=status.value,
                         uzytkownik=(user.value or "").strip(), sprawdzono=(checked.value or "").strip(),
                         uwagi=(notes.value or "").strip())
            if save_and_report():
                ui.notify("Zapisano", type="positive")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.open()


def move_dialog(ids: list[str], after):
    if not ids:
        return
    with ui.dialog() as dlg, ui.card().classes("w-[460px] rounded-2xl p-6 gap-3"):
        ui.label(f"Przenieś {len(ids)} szt.").classes("text-xl font-bold")
        target = ui.select(locations(), label="Nowa sala", with_input=True, new_value_mode="add-unique") \
            .props("outlined").classes("w-full")

        def go():
            if not target.value:
                ui.notify("Wybierz salę")
                return
            for iid in ids:
                S.inv.update(iid, sala=str(target.value).strip(), pewnosc=PEWNA)
            if save_and_report():
                ui.notify(f"Przeniesiono {len(ids)} szt. do {target.value}", type="positive")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Przenieś", icon="move_up", on_click=go).props("unelevated no-caps color=primary")
    dlg.open()


def import_dialog(after):
    with ui.dialog() as dlg, ui.card().classes("w-[820px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Import ewidencji").classes("text-xl font-bold")
        ui.label("Wybierz zestawienia z księgowości (.xls/.xlsx) — możesz zaznaczyć wszystkie naraz. "
                 "Twoje zmiany (faktyczna sala, status, użytkownik, uwagi) nie zostaną nadpisane.").classes("ws-mut")
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
                lines += ["❓ Lokalizacja do sprawdzenia:"] + ["   " + s for s in rep.uncertain] + [""]
                lines += ["✂ Numery z kilkoma sztukami (rozbite na #1, #2…):"] + ["   " + s for s in rep.split_rows]
                ui.code("\n".join(lines), language="text").classes("w-full max-h-80 overflow-auto")

                def do_import():
                    merge(S.inv, items)
                    S.inv.ensure_rooms(S.plan_rooms() + S.inv.locations())
                    if save_and_report():
                        ui.notify(f"Zaimportowano — spis: {len(S.inv.items)} szt.", type="positive")
                    dlg.close()
                    ui.navigate.to("/sprzet")

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
                    ui.button("Importuj", icon="download_done", on_click=do_import) \
                        .props("unelevated no-caps color=primary")

        ui.upload(multiple=True, auto_upload=True, on_multi_upload=on_multi) \
            .props('accept=".xls,.xlsx" flat bordered label="Przeciągnij pliki albo kliknij +"').classes("w-full")
    dlg.open()
