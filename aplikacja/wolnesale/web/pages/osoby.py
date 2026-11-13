"""Ekran „Osoby”: rejestr osób (plan + ewidencja + ręcznie), duplikaty, scalanie, edycja."""
from __future__ import annotations

from nicegui import ui

from ...core.osoby import RECZNIE, Z_EWIDENCJI, Z_PLANU, Person, Registry, norm_key
from ..app import nav_set
from ..state import S
from ..theme import badge, card, esc, page_header, set_on

FUNKCJE = ["nauczyciel", "dyrektor", "wicedyrektor", "główna księgowa", "księgowa", "sekretariat",
           "administracja", "kierownik", "pedagog", "obsługa", "uczeń"]
SRC_COL = {Z_PLANU: ("#e0e7ff", "#4338ca", "📅 plan"), Z_EWIDENCJI: ("#fef3c7", "#b45309", "📦 ewidencja"),
           RECZNIE: ("#f1f5f9", "#475569", "✍ ręcznie")}
VIEWS = {"all": "Wszyscy", "devices": "Ze sprzętem", "outside": "Spoza planu", "roles": "Z funkcją"}

COLUMNS = [
    {"name": "nazwa", "label": "Osoba", "field": "nazwa", "sortable": True, "align": "left"},
    {"name": "funkcja", "label": "Funkcja", "field": "funkcja", "sortable": True, "align": "left"},
    {"name": "zrodlo", "label": "Skąd", "field": "zrodlo", "sortable": True, "align": "left"},
    {"name": "sprzet", "label": "Sprzęt", "field": "sprzet", "sortable": True, "align": "right"},
    {"name": "aliasy", "label": "Inne zapisy (aliasy)", "field": "aliasy", "align": "left",
     "style": "max-width:420px;white-space:normal"},
]
SRC_SLOT = r"""
<q-td :props="props">
  <span class="ws-st" :style="{background: props.row.src_bg, color: props.row.src_fg}">{{ props.row.src_label }}</span>
</q-td>
"""


def _save(msg: str | None = None) -> bool:
    err = S.save_inventory()
    if err:
        ui.notify(err, type="warning", timeout=8000, close_button=True)
        return False
    if msg:
        ui.notify(msg, type="positive")
    return True


def build():
    nav_set("/osoby")
    reg = Registry(S.inv)
    st = {"view": "all", "q": ""}
    if not S.inv.osoby and (S.tt or S.inv.items):
        # pierwsze wejście: zbuduj rejestr z planu i ewidencji
        reg.sync_plan(S.tt.teachers if S.tt else [])
        reg.normalize_items()
        _save()

    with ui.column().classes("ws-page"):
        actions = page_header("Osoby")
        with actions:
            ui.button("Uporządkuj (plan + ewidencja)", icon="auto_fix_high", on_click=lambda: tidy()) \
                .props("outline no-caps color=primary") \
                .tooltip("Dodaje nauczycieli z planu i ujednolica osoby przy sprzęcie (inicjały, kolejność, zdrobnienia)")
            ui.button("Dodaj osobę", icon="person_add", on_click=lambda: person_dialog(None, refresh)) \
                .props("unelevated no-caps color=primary")

        dup_box = ui.column().classes("w-full gap-0")

        with card():
            with ui.row().classes("items-start gap-x-8 gap-y-4 w-full ws-filters"):
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Pokaż</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        vbtn = {}
                        for k, label in VIEWS.items():
                            def setv(k=k):
                                st["view"] = k
                                for kk, b in vbtn.items():
                                    set_on(b, kk == k)
                                fill()
                            vbtn[k] = ui.button(label, on_click=setv).props("flat dense no-caps")
                            set_on(vbtn[k], k == "all")
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Szukaj</span>', sanitize=False)
                    ui.input(placeholder="nazwisko, imię, alias…",
                             on_change=lambda e: (st.update(q=e.value or ""), fill())) \
                        .props("outlined dense rounded clearable").classes("w-72")

        with card():
            table = ui.table(columns=COLUMNS, rows=[], row_key="nazwa", selection="multiple",
                             pagination={"rowsPerPage": 50, "sortBy": "nazwa"}) \
                .props("flat dense table-header-class=text-grey-7").classes("w-full")
            table.add_slot("body-cell-zrodlo", SRC_SLOT)
            table.on("rowClick", lambda e: person_dialog(e.args[1]["nazwa"], refresh))
            with ui.row().classes("items-center gap-2 w-full mt-2"):
                merge_b = ui.button("Scal zaznaczone", icon="merge",
                                    on_click=lambda: merge_dialog([r["nazwa"] for r in table.selected], refresh)) \
                    .props("unelevated no-caps color=primary")
                ui.space()
                count = ui.label().classes("ws-mut")
            ui.label("Zaznacz dwie (lub więcej) osoby, które są tą samą osobą, i kliknij „Scal”. "
                     "Kliknij wiersz, żeby zmienić nazwę, funkcję albo zobaczyć sprzęt.").classes("ws-mut text-sm")

        def upd_btn():
            n = len(table.selected)
            merge_b.set_enabled(n >= 2)
            merge_b.text = f"Scal zaznaczone ({n})" if n >= 2 else "Scal zaznaczone"
        table.on_select(lambda _: upd_btn())

        def fill():
            q = norm_key(st["q"])
            counts: dict[str, int] = {}
            for it in S.inv.items.values():
                if it.uzytkownik:
                    counts[it.uzytkownik] = counts.get(it.uzytkownik, 0) + 1
            rows = []
            for p in S.inv.osoby.values():
                n = counts.get(p.nazwa, 0)
                if st["view"] == "devices" and not n:
                    continue
                if st["view"] == "outside" and p.zrodlo == Z_PLANU:
                    continue
                if st["view"] == "roles" and p.funkcja in ("", "nauczyciel"):
                    continue
                if q and q not in norm_key(" ".join([p.nazwa, p.funkcja, p.aliasy])):
                    continue
                bg, fg, lab = SRC_COL.get(p.zrodlo, SRC_COL[RECZNIE])
                rows.append({"nazwa": p.nazwa, "funkcja": p.funkcja, "zrodlo": p.zrodlo, "sprzet": n,
                             "aliasy": p.aliasy, "src_bg": bg, "src_fg": fg, "src_label": lab})
            table.rows = rows
            table.selected.clear()
            table.update()
            count.text = (f"{len(rows)} z {len(S.inv.osoby)} osób" if len(rows) != len(S.inv.osoby)
                          else f"{len(rows)} osób")
            upd_btn()

        def duplicates():
            dup_box.clear()
            dups = reg.duplicates()
            dup_box.set_visibility(bool(dups))
            if not dups:
                return
            with dup_box, card().style("background:#fffbeb"):
                ui.label(f"⚠️ Możliwe duplikaty ({len(dups)})").classes("text-lg font-bold")
                ui.label("Te zapisy wyglądają na tę samą osobę. Wybierz, który zostaje — drugi zniknie, "
                         "a jego sprzęt przejdzie na osobę, która zostaje.").classes("ws-mut text-sm mb-1")
                for a, b, why in dups[:30]:
                    with ui.row().classes("w-full items-center gap-3 py-1").style("border-top:1px solid #fde68a"):
                        ui.html(f'<b>{esc(a)}</b> ⇄ <b>{esc(b)}</b> <span class="ws-mut">· {esc(why)}</span>',
                                sanitize=False).classes("flex-1")
                        ui.button(f"Zostaw: {a}", on_click=lambda a=a, b=b: quick_merge(a, b)) \
                            .props("flat dense no-caps color=primary")
                        ui.button(f"Zostaw: {b}", on_click=lambda a=a, b=b: quick_merge(b, a)) \
                            .props("flat dense no-caps color=primary")
                        ui.button("To różne osoby", on_click=lambda a=a, b=b: (reg.mark_different(a, b), _save(),
                                                                                  refresh())) \
                            .props("flat dense no-caps color=grey-8")

        def quick_merge(keep, other):
            n = reg.merge(keep, [other])
            _save(f"Scalono: {other} → {keep} (przeniesiony sprzęt: {n})")
            refresh()

        def tidy():
            added = reg.sync_plan(S.tt.teachers if S.tt else [])
            notes = reg.normalize_items()
            _save()
            with ui.dialog() as d, ui.card().classes("w-[720px] max-w-[95vw] rounded-2xl p-6 gap-2"):
                ui.label("Porządkowanie osób").classes("text-xl font-bold")
                ui.label(f"Nowi nauczyciele z planu: {added} · zmiany przy sprzęcie: {len(notes)}").classes("ws-mut")
                ui.code("\n".join(notes) or "Wszystko było już uporządkowane.", language="text") \
                    .classes("w-full max-h-96 overflow-auto")
                ui.button("OK", on_click=d.close).props("unelevated no-caps color=primary").classes("self-end")
            d.on("hide", d.delete)
            d.open()
            refresh()

        def refresh():
            duplicates()
            fill()

        refresh()


def merge_dialog(names: list[str], after) -> None:
    reg = Registry(S.inv)
    people = [S.inv.osoby[n] for n in names if n in S.inv.osoby]
    if len(people) < 2:
        return
    counts = {p.nazwa: len(reg.devices(p.nazwa)) for p in people}
    default = next((p.nazwa for p in people if p.zrodlo == Z_PLANU),
                   max(people, key=lambda p: (len(p.nazwa.split()), counts[p.nazwa], len(p.nazwa))).nazwa)
    with ui.dialog() as dlg, ui.card().classes("w-[560px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Scal osoby").classes("text-xl font-bold")
        ui.label("Wybierz zapis, który zostaje. Pozostałe staną się jego aliasami, a ich sprzęt przejdzie na tę osobę.") \
            .classes("ws-mut text-sm")
        keep = ui.radio({p.nazwa: f"{p.nazwa}  ·  {p.funkcja or 'bez funkcji'}  ·  "
                                  f"{SRC_COL.get(p.zrodlo, SRC_COL[RECZNIE])[2]}  ·  sprzęt: {counts[p.nazwa]}"
                         for p in people}, value=default).classes("w-full")
        roles = sorted({p.funkcja for p in people if p.funkcja} | set(FUNKCJE))
        best = next((p.funkcja for p in people if p.funkcja not in ("", "nauczyciel")), "") or \
            next((p.funkcja for p in people if p.funkcja), "")
        fn = ui.select(roles, value=best or None, label="Funkcja po scaleniu", with_input=True,
                       new_value_mode="add-unique", clearable=True).props("outlined dense").classes("w-full")

        def go():
            k = keep.value
            n = reg.merge(k, [p.nazwa for p in people if p.nazwa != k])
            S.inv.osoby[k].funkcja = fn.value or ""
            _save(f"Scalono w: {k} (przeniesiony sprzęt: {n})")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Scal", icon="merge", on_click=go).props("unelevated no-caps color=primary")
    dlg.on("hide", dlg.delete)
    dlg.open()


def person_dialog(name: str | None, after) -> None:
    reg = Registry(S.inv)
    new = name is None
    p = S.inv.osoby.get(name) if name else Person("", zrodlo=RECZNIE)
    if p is None:
        return
    with ui.dialog() as dlg, ui.card().classes("w-[620px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Nowa osoba" if new else p.nazwa).classes("text-xl font-bold")
        nazwa = ui.input("Osoba (Nazwisko Imię)", value=p.nazwa).props("outlined dense").classes("w-full")
        fn = ui.select(sorted(set(FUNKCJE) | ({p.funkcja} if p.funkcja else set())), value=p.funkcja or None,
                       label="Funkcja", with_input=True, new_value_mode="add-unique", clearable=True) \
            .props("outlined dense").classes("w-full")
        aliasy = ui.input("Inne zapisy (aliasy, oddzielone ;)", value=p.aliasy).props("outlined dense") \
            .classes("w-full")
        ui.label("Aliasy to inne zapisy tej samej osoby (np. z ewidencji). Program przy kolejnym imporcie "
                 "rozpozna po nich osobę.").classes("ws-hint")
        uwagi = ui.input("Uwagi", value=p.uwagi).props("outlined dense").classes("w-full")
        devs = [] if new else reg.devices(p.nazwa)
        if not new and S.tt and any(l.teacher == p.nazwa for l in S.tt.lessons):
            from .nauczyciel import url_for
            ui.button("Plan lekcji tej osoby", icon="calendar_view_week",
                      on_click=lambda: (dlg.close(), ui.navigate.to(url_for(p.nazwa)))) \
                .props("outline no-caps color=primary")
        if not new:
            ui.html(f'<span class="ws-flabel" style="margin-top:6px">Sprzęt tej osoby ({len(devs)})</span>',
                    sanitize=False)
            if devs:
                ui.html("".join(
                    f'<div style="display:flex;gap:10px;padding:4px 0;border-top:1px solid var(--line);font-size:13px">'
                    f'<span style="width:110px">{esc(i.id)}</span><span style="flex:1">{esc(i.kategoria)} · '
                    f'{esc(i.nazwa[:50])}</span><span>{esc(i.sala or "?")}</span>'
                    f'<span class="ws-mut">{esc(i.przydzial or "")}{" do " + esc(i.zwrot) if i.zwrot else ""}</span></div>'
                    for i in devs), sanitize=False).classes("w-full max-h-48 overflow-auto shrink-0")
            else:
                ui.label("Brak przypisanego sprzętu.").classes("ws-mut text-sm")
            ui.html('<span class="ws-flabel" style="margin-top:6px">To ta sama osoba co…</span>', sanitize=False)
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                target = ui.select({n: (f"{n} · {q.funkcja}" if q.funkcja else n)
                                    for n, q in sorted(S.inv.osoby.items()) if n != p.nazwa},
                                   label="np. Dyrektor → właściwe nazwisko", with_input=True, clearable=True) \
                    .props("outlined dense").classes("flex-1")

                def merge_into():
                    if not target.value:
                        ui.notify("Wybierz osobę")
                        return
                    keep = target.value
                    best = p.funkcja if p.funkcja not in ("", "nauczyciel") else ""
                    n = reg.merge(keep, [p.nazwa])
                    if best:
                        S.inv.osoby[keep].funkcja = best
                    _save(f"Scalono: {p.nazwa} → {keep} (przeniesiony sprzęt: {n})")
                    dlg.close()
                    after()
                ui.button("Scal", icon="merge", on_click=merge_into).props("outline no-caps color=primary")
            ui.label("Ten wpis zniknie, jego zapis stanie się aliasem, a sprzęt przejdzie na wybraną osobę.") \
                .classes("ws-hint")

        def save():
            nn = (nazwa.value or "").strip()
            if not nn:
                ui.notify("Wpisz nazwę osoby")
                return
            if new:
                if reg.find(nn):
                    ui.notify("Taka osoba już jest w rejestrze")
                    return
                q = reg.add(nn, fn.value or "", RECZNIE)
            else:
                if nn != p.nazwa:
                    other = reg.find(nn)
                    if other and other is not p:
                        ui.notify("Taka osoba już istnieje — użyj „Scal”")
                        return
                    reg.rename(p.nazwa, nn)
                q = S.inv.osoby[nn]
                q.funkcja = fn.value or ""
            q.aliasy = "; ".join(a.strip() for a in (aliasy.value or "").split(";") if a.strip())
            q.uwagi = (uwagi.value or "").strip()
            _save("Zapisano")
            dlg.close()
            after()

        def delete():
            S.inv.osoby.pop(p.nazwa, None)
            _save("Usunięto z rejestru")
            dlg.close()
            after()

        with ui.row().classes("w-full items-center gap-2"):
            if not new and not devs:
                ui.button("Usuń", icon="delete", on_click=delete).props("flat no-caps color=negative")
            ui.space()
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.on("hide", dlg.delete)
    dlg.open()
