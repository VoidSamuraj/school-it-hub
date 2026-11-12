"""Ekran „Zadania”: zadania w salach oraz zadania globalne z tabelą checkboxów (cel × zadanie)."""
from __future__ import annotations

from datetime import date, datetime

from nicegui import ui

from ...core.sale import base_room, building, normalize_room, sort_key
from ...core.zadania import (CEL_SALE, CEL_SPRZET, DO_ZROBIENIA, PRIORITIES, TASK_STATUSES,
                             W_TRAKCIE, ZAKRES_IT, ZAKRES_WSZYSTKIE, ZROBIONE, GlobalTask, Task,
                             done_map, next_id, progress_summary, set_done, target_key,
                             target_room, targets)
from ..app import nav_set
from ..state import S
from ..theme import badge, card, esc, page_header

PRIO_COL = {"pilny": ("#fee2e2", "#b91c1c"), "normalny": ("#eef2ff", "#4f46e5"), "niski": ("#f1f5f9", "#64748b")}
STATUS_COL = {DO_ZROBIENIA: ("#fef3c7", "#b45309"), W_TRAKCIE: ("#dbeafe", "#1d4ed8"), ZROBIONE: ("#dcfce7", "#15803d")}

MATRIX_CELL = r"""
<q-td :props="props">
  <template v-if="props.col.name.startsWith('g_')">
    <q-checkbox v-if="props.value !== null" dense color="positive" :model-value="props.value"
      @update:model-value="v => $parent.$emit('toggle', {id: props.row.key, task: props.col.name.slice(2), v: v})" />
    <span v-else style="color:#d1d5db">—</span>
  </template>
  <template v-else>{{ props.value }}</template>
</q-td>
"""


def _save(msg: str | None = None) -> None:
    err = S.save_inventory()
    if err:
        ui.notify(err, type="warning", timeout=8000, close_button=True)
    elif msg:
        ui.notify(msg, type="positive")


def _pill(text: str, colors: tuple[str, str]) -> str:
    return f'<span class="ws-st" style="background:{colors[0]};color:{colors[1]}">{esc(text)}</span>'


def _rooms() -> list[str]:
    from ...core.sale import is_room
    rooms = set(S.plan_rooms()) | {i.sala for i in S.inv.items.values() if i.sala}
    return sorted((r for r in rooms if is_room(r)), key=sort_key)


def open_count() -> int:
    return sum(1 for t in S.inv.tasks if not t.done)


def build(tab: str | None = None):
    nav_set("/zadania")
    with ui.column().classes("ws-page"):
        page_header("Zadania")
        with ui.tabs().props("no-caps align=left active-color=primary indicator-color=primary") \
                .classes("w-full") as tabs:
            t_rooms = ui.tab("sale", label="📍 W salach")
            t_glob = ui.tab("glob", label="☑️ Globalne (na wielu PC / salach)")
        with ui.tab_panels(tabs, value=t_glob if tab == "glob" else t_rooms).classes("w-full bg-transparent"):
            with ui.tab_panel(t_rooms).classes("p-0"):
                room_tasks_panel()
            with ui.tab_panel(t_glob).classes("p-0"):
                global_panel()


# =====================================================================================
# Zadania w salach
# =====================================================================================
def room_tasks_panel(fixed_room: str | None = None) -> None:
    st = {"status": "open", "sala": fixed_room}

    @ui.refreshable
    def body():
        tasks = list(S.inv.tasks)
        if st["status"] == "open":
            tasks = [t for t in tasks if not t.done]
        elif st["status"] == "done":
            tasks = [t for t in tasks if t.done]
        if st["sala"]:
            tasks = [t for t in tasks if base_room(t.sala or "") == base_room(st["sala"])]
        prio = {p: i for i, p in enumerate(reversed(PRIORITIES))}
        tasks.sort(key=lambda t: (t.done, not t.overdue(), prio.get(t.priorytet, 9), t.termin or "9999",
                                  sort_key(t.sala) if t.sala else (99,)))
        with card():
            if not tasks:
                ui.label("Brak zadań 🎉" if st["status"] == "open" else "Brak zadań").classes("ws-mut")
            for t in tasks:
                task_row(t, body.refresh, show_room=not fixed_room)

    with ui.row().classes("w-full items-center gap-3 mb-3"):
        ui.toggle({"open": "Do zrobienia", "done": "Zrobione", "all": "Wszystkie"}, value="open",
                  on_change=lambda e: (st.update(status=e.value), body.refresh())) \
            .props("no-caps rounded unelevated toggle-color=primary")
        if not fixed_room:
            ui.select(_rooms(), label="Sala", clearable=True, with_input=True,
                      on_change=lambda e: (st.update(sala=e.value), body.refresh())) \
                .props("outlined dense options-dense").classes("w-40")
        ui.space()
        ui.button("Nowe zadanie", icon="add", on_click=lambda: task_dialog(None, body.refresh, fixed_room)) \
            .props("unelevated no-caps color=primary")
    body()


def task_row(t: Task, after, show_room: bool = True) -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap py-2").style("border-top:1px solid var(--line)"):
        def toggle(e, t=t):
            t.status = ZROBIONE if e.value else DO_ZROBIENIA
            t.zrobiono = datetime.now().strftime("%Y-%m-%d %H:%M") if e.value else ""
            S.inv.log(f"zadanie:{t.id}", "zrobione" if e.value else "otwarte ponownie", opis=t.tytul)
            _save()
            after()
        ui.checkbox(value=t.done, on_change=toggle).props("color=positive")
        meta = []
        if t.termin:
            over = t.overdue()
            meta.append(f'<span style="color:{"#b91c1c;font-weight:700" if over else "var(--mut)"}">'
                        f'📅 {esc(t.termin)}{" · po terminie" if over else ""}</span>')
        if t.sprzet:
            it = S.inv.items.get(t.sprzet)
            meta.append(f'<span class="ws-mut">🖥 {esc(t.sprzet)}{" · " + esc(it.nazwa[:40]) if it else ""}</span>')
        if t.opis:
            meta.append(f'<span class="ws-mut">{esc(t.opis[:80])}</span>')
        if t.done and t.zrobiono:
            meta.append(f'<span class="ws-mut">✔ {esc(t.zrobiono)}</span>')
        title_style = "text-decoration:line-through;color:var(--mut)" if t.done else ""
        ui.html(f'<div style="min-width:0"><div style="font-weight:600;{title_style}">{esc(t.tytul)}</div>'
                f'<div style="font-size:12.5px;display:flex;gap:12px;flex-wrap:wrap">{"".join(meta)}</div></div>',
                sanitize=False).classes("flex-1 min-w-0 cursor-pointer").on("click", lambda t=t: task_dialog(t, after))
        if show_room and t.sala:
            ui.html(badge(t.sala), sanitize=False)
        ui.html(_pill(t.priorytet, PRIO_COL.get(t.priorytet, PRIO_COL["normalny"])) + " " +
                _pill(t.status, STATUS_COL.get(t.status, STATUS_COL[DO_ZROBIENIA])), sanitize=False)


def task_dialog(t: Task | None, after, room: str | None = None) -> None:
    new = t is None
    t = t or Task(id="", tytul="", sala=room or "")
    with ui.dialog() as dlg, ui.card().classes("w-[600px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Nowe zadanie" if new else "Zadanie").classes("text-xl font-bold")
        tytul = ui.input("Co zrobić", value=t.tytul).props("outlined dense autofocus").classes("w-full")
        with ui.grid(columns=2).classes("w-full gap-3"):
            sala = ui.select(_rooms(), value=t.sala or None, label="Sala", with_input=True, clearable=True,
                             new_value_mode="add-unique").props("outlined dense")
            sprzet = ui.select({}, value=None, label="Sprzęt (opcjonalnie)", with_input=True, clearable=True) \
                .props("outlined dense")
            termin = ui.input("Termin", value=t.termin).props("outlined dense type=date")
            prio = ui.select(PRIORITIES, value=t.priorytet, label="Priorytet").props("outlined dense")
            status = ui.select(TASK_STATUSES, value=t.status, label="Status").props("outlined dense")
        opis = ui.textarea("Opis", value=t.opis).props("outlined dense autogrow").classes("w-full")

        def fill_items(*_):
            r = sala.value
            opts = {}
            if r:
                for it in sorted(S.inv.in_room(r), key=lambda i: (i.kategoria, i.id)):
                    opts[it.id] = f"{it.id} · {it.kategoria} · {it.nazwa[:40]}"
            if t.sprzet and t.sprzet not in opts and t.sprzet in S.inv.items:
                it = S.inv.items[t.sprzet]
                opts[it.id] = f"{it.id} · {it.kategoria} · {it.nazwa[:40]}"
            sprzet.options = opts
            sprzet.value = t.sprzet if t.sprzet in opts else None
            sprzet.update()
        sala.on_value_change(fill_items)
        fill_items()

        def save():
            if not (tytul.value or "").strip():
                ui.notify("Wpisz, co zrobić")
                return
            if new:
                t.id = next_id("Z", [x.id for x in S.inv.tasks])
                t.utworzono = datetime.now().strftime("%Y-%m-%d %H:%M")
                S.inv.tasks.append(t)
            was_done = t.done
            t.tytul, t.sala = tytul.value.strip(), normalize_room(sala.value) if sala.value else ""
            t.sprzet, t.termin, t.priorytet = sprzet.value or "", termin.value or "", prio.value
            t.status, t.opis = status.value, (opis.value or "").strip()
            if t.done and not was_done:
                t.zrobiono = datetime.now().strftime("%Y-%m-%d %H:%M")
            S.inv.log(f"zadanie:{t.id}", "nowe zadanie" if new else "edycja zadania", opis=t.tytul)
            _save("Zapisano zadanie")
            dlg.close()
            after()

        def delete():
            S.inv.tasks = [x for x in S.inv.tasks if x.id != t.id]
            S.inv.log(f"zadanie:{t.id}", "usunięte zadanie", opis=t.tytul)
            _save("Usunięto")
            dlg.close()
            after()

        with ui.row().classes("w-full items-center gap-2"):
            if not new:
                ui.button("Usuń", icon="delete", on_click=delete).props("flat no-caps color=negative")
            ui.space()
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.open()


# =====================================================================================
# Zadania globalne
# =====================================================================================
def global_panel() -> None:
    st = {"show_closed": False, "sala": None, "only_todo": False, "q": ""}

    @ui.refreshable
    def body():
        gl = [g for g in S.inv.global_tasks if g.active or st["show_closed"]]
        # --- karty zadań
        with ui.row().classes("w-full gap-4"):
            if not gl:
                with card():
                    ui.label("Brak zadań globalnych").classes("text-lg font-bold")
                    ui.label("Zadanie globalne to jedna czynność do zrobienia w wielu miejscach, np. "
                             "„aktualizacja Windows na każdym komputerze w salach IT”. Każde miejsce "
                             "odhaczasz osobno w tabeli poniżej.").classes("ws-mut")
            for g in gl:
                done, total, _ = progress_summary(S.inv, g, S.plan_rooms())
                pct = round(100 * done / total) if total else 0
                with ui.element("div").classes("ws-card").style("width:300px;padding:16px 18px"):
                    with ui.row().classes("w-full items-start no-wrap gap-2"):
                        ui.html(f'<div style="font-weight:700;font-size:15px">{esc(g.tytul)}</div>'
                                f'<div class="ws-mut" style="font-size:12px">{esc(g.scope_label())}</div>',
                                sanitize=False).classes("flex-1 min-w-0")
                        with ui.button(icon="more_vert").props("flat round dense"):
                            with ui.menu():
                                ui.menu_item("Edytuj", on_click=lambda g=g: global_dialog(g, body.refresh))
                                ui.menu_item("Otwórz ponownie" if not g.active else "Zakończ (ukryj)",
                                             on_click=lambda g=g: close_task(g))
                                ui.menu_item("Usuń", on_click=lambda g=g: delete_task(g))
                    ui.html(f'<div style="display:flex;justify-content:space-between;margin-top:8px">'
                            f'<b style="font-size:20px">{done}<span class="ws-mut" style="font-size:14px">'
                            f' / {total}</span></b><span class="ws-mut">{pct}%</span></div>'
                            f'<div class="ws-bar"><i style="width:{pct}%"></i></div>'
                            f'{"" if g.active else "<div class=ws-hint>zakończone</div>"}', sanitize=False)

        # --- tabela checkboxów
        for cel in (CEL_SPRZET, CEL_SALE):
            cols_tasks = [g for g in gl if g.cel == cel]
            if cols_tasks:
                matrix(cel, cols_tasks)

    def close_task(g: GlobalTask):
        g.zamkniete = "" if not g.active else "tak"
        _save()
        body.refresh()

    def delete_task(g: GlobalTask):
        S.inv.global_tasks = [x for x in S.inv.global_tasks if x.id != g.id]
        S.inv.progress = [p for p in S.inv.progress if p.zadanie != g.id]
        _save("Usunięto zadanie globalne")
        body.refresh()

    def matrix(cel: str, tasks: list[GlobalTask]) -> None:
        rows: dict[str, dict] = {}
        dms = {g.id: done_map(S.inv, g.id) for g in tasks}
        for g in tasks:
            for t in targets(S.inv, g, S.plan_rooms()):
                k = target_key(t)
                r = rows.get(k)
                if r is None:
                    if cel == CEL_SPRZET:
                        r = {"key": k, "sala": t.sala, "kategoria": t.kategoria, "nazwa": t.nazwa[:50]}
                    else:
                        r = {"key": k, "sala": t, "budynek": building(t)}
                    rows[k] = r
                r[f"g_{g.id}"] = k in dms[g.id]
        for r in rows.values():
            for g in tasks:
                r.setdefault(f"g_{g.id}", None)
        data = list(rows.values())
        if st["sala"]:
            data = [r for r in data if base_room(r["sala"]) == base_room(st["sala"])]
        if st["only_todo"]:
            data = [r for r in data if any(r[f"g_{g.id}"] is False for g in tasks)]
        q = st["q"].strip().lower()
        if q:
            data = [r for r in data if q in " ".join(str(v) for v in r.values()).lower()]
        data.sort(key=lambda r: (sort_key(r["sala"]), r["key"]))

        base_cols = ([{"name": "sala", "label": "Sala", "field": "sala", "sortable": True, "align": "left"},
                      {"name": "key", "label": "ID", "field": "key", "sortable": True, "align": "left"},
                      {"name": "kategoria", "label": "Kategoria", "field": "kategoria", "align": "left"},
                      {"name": "nazwa", "label": "Nazwa", "field": "nazwa", "align": "left",
                       "style": "max-width:260px;overflow:hidden;text-overflow:ellipsis"}]
                     if cel == CEL_SPRZET else
                     [{"name": "sala", "label": "Sala", "field": "sala", "sortable": True, "align": "left"},
                      {"name": "budynek", "label": "Budynek", "field": "budynek", "align": "left"}])
        task_cols = []
        for g in tasks:
            done = sum(1 for r in rows.values() if r[f"g_{g.id}"])
            total = sum(1 for r in rows.values() if r[f"g_{g.id}"] is not None)
            task_cols.append({"name": f"g_{g.id}", "label": f"{g.tytul} ({done}/{total})",
                              "field": f"g_{g.id}", "align": "center"})

        with card().classes("mt-4"):
            title = "Komputery i sprzęt" if cel == CEL_SPRZET else "Sale"
            with ui.row().classes("w-full items-center gap-3"):
                ui.label(f"☑️ {title} — odhaczanie").classes("text-lg font-bold")
                ui.space()
                with ui.button("Odhacz widoczne…", icon="done_all").props("flat no-caps color=primary"):
                    with ui.menu():
                        for g in tasks:
                            ui.menu_item(f"✔ {g.tytul} — zaznacz {len(data)} widocznych",
                                         on_click=lambda g=g: bulk(g, data, True))
                            ui.menu_item(f"✖ {g.tytul} — odznacz widoczne",
                                         on_click=lambda g=g: bulk(g, data, False))
            room_chips(tasks, rows)
            table = ui.table(columns=base_cols + task_cols, rows=data, row_key="key",
                             pagination={"rowsPerPage": 50}) \
                .props("flat dense table-header-class=text-grey-7").classes("w-full")
            table.add_slot("body-cell", MATRIX_CELL)

            def on_toggle(e):
                a = e.args
                set_done(S.inv, a["task"], a["id"], bool(a["v"]))
                _save()
                body.refresh()
            table.on("toggle", on_toggle)

    def room_chips(tasks, rows):
        # postęp na salę (wszystkie zadania tej tabeli razem)
        per: dict[str, list[int]] = {}
        for r in rows.values():
            for g in tasks:
                v = r[f"g_{g.id}"]
                if v is None:
                    continue
                d = per.setdefault(base_room(r["sala"]), [0, 0])
                d[1] += 1
                d[0] += bool(v)
        chips = []
        for room in sorted(per, key=sort_key):
            d, n = per[room]
            full = d == n
            chips.append(f'<span class="ws-chip" style="background:{"#dcfce7" if full else "#f1f5f9"};'
                         f'color:{"#15803d" if full else "var(--ink)"}">{esc(room)}<small>{d}/{n}</small></span>')
        ui.html("".join(chips), sanitize=False).classes("w-full my-2")

    def bulk(g: GlobalTask, data: list[dict], value: bool):
        n = 0
        for r in data:
            if r.get(f"g_{g.id}") is not None:
                set_done(S.inv, g.id, r["key"], value)
                n += 1
        _save(f"{'Odhaczono' if value else 'Odznaczono'} {n} pozycji")
        body.refresh()

    with ui.row().classes("w-full items-center gap-3 mb-3"):
        ui.select(_rooms(), label="Sala", clearable=True, with_input=True,
                  on_change=lambda e: (st.update(sala=e.value), body.refresh())) \
            .props("outlined dense options-dense").classes("w-40")
        ui.input(placeholder="Szukaj: ID, nazwa…", on_change=lambda e: (st.update(q=e.value or ""), body.refresh())) \
            .props("outlined dense rounded clearable").classes("w-60")
        ui.switch("tylko niezrobione", on_change=lambda e: (st.update(only_todo=e.value), body.refresh()))
        ui.switch("pokaż zakończone", on_change=lambda e: (st.update(show_closed=e.value), body.refresh()))
        ui.space()
        ui.button("Nowe zadanie globalne", icon="add", on_click=lambda: global_dialog(None, body.refresh)) \
            .props("unelevated no-caps color=primary")
    body()


def global_dialog(g: GlobalTask | None, after) -> None:
    new = g is None
    g = g or GlobalTask(id="", tytul="")
    cats = sorted({i.kategoria for i in S.inv.items.values() if i.kategoria})
    with ui.dialog() as dlg, ui.card().classes("w-[640px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Nowe zadanie globalne" if new else "Zadanie globalne").classes("text-xl font-bold")
        tytul = ui.input("Co zrobić", value=g.tytul, placeholder="np. Aktualizacja Windows 11 24H2") \
            .props("outlined dense autofocus").classes("w-full")
        cel = ui.toggle({CEL_SPRZET: "🖥 Na sprzęcie (każdy komputer osobno)", CEL_SALE: "🚪 W salach (każda sala osobno)"},
                        value=g.cel).props("no-caps rounded unelevated toggle-color=primary")
        kat = ui.select(cats, value=[c for c in g.category_set if c in cats], multiple=True,
                        label="Jakie urządzenia", clearable=True).props("outlined dense use-chips").classes("w-full")
        preset = ui.button("💻 Komputery + laptopy + chromebooki", on_click=lambda: kat.set_value(
            [c for c in ("Komputer", "Laptop", "Chromebook") if c in cats])).props("flat dense no-caps color=primary")
        mode_val = (ZAKRES_WSZYSTKIE if g.sale.strip().lower() in (ZAKRES_WSZYSTKIE, "") else
                    ZAKRES_IT if g.sale.strip().lower() == ZAKRES_IT.lower() else "lista")
        zakres = ui.toggle({ZAKRES_WSZYSTKIE: "Wszystkie sale", ZAKRES_IT: "💻 Tylko sale IT", "lista": "Wybrane sale"},
                           value=mode_val).props("no-caps rounded unelevated toggle-color=primary")
        sale = ui.select(_rooms(), value=g.room_list, multiple=True, label="Wybrane sale", with_input=True) \
            .props("outlined dense use-chips").classes("w-full")
        opis = ui.textarea("Opis / instrukcja", value=g.opis).props("outlined dense autogrow").classes("w-full")
        count = ui.label().classes("ws-mut")

        def preview(*_):
            kat.set_visibility(cel.value == CEL_SPRZET)
            preset.set_visibility(cel.value == CEL_SPRZET)
            sale.set_visibility(zakres.value == "lista")
            tmp = GlobalTask("x", "x", cel=cel.value, kategorie=", ".join(kat.value or []),
                             sale=", ".join(sale.value or []) if zakres.value == "lista" else zakres.value)
            n = len(targets(S.inv, tmp, S.plan_rooms()))
            count.text = f"Obejmie: {n} {'pozycji sprzętu' if cel.value == CEL_SPRZET else 'sal'}"
        for w in (cel, kat, zakres, sale):
            w.on_value_change(preview)
        preview()

        def save():
            if not (tytul.value or "").strip():
                ui.notify("Wpisz, co zrobić")
                return
            if new:
                g.id = next_id("G", [x.id for x in S.inv.global_tasks])
                g.utworzono = datetime.now().strftime("%Y-%m-%d %H:%M")
                S.inv.global_tasks.append(g)
            g.tytul, g.cel = tytul.value.strip(), cel.value
            g.kategorie = ", ".join(kat.value or []) if cel.value == CEL_SPRZET else ""
            g.sale = ", ".join(sale.value or []) if zakres.value == "lista" else zakres.value
            g.opis = (opis.value or "").strip()
            _save("Zapisano zadanie globalne")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.open()
