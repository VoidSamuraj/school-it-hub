"""Ekran „Sala”: plan tygodnia sali, wolne okna i sprzęt w sali."""
from __future__ import annotations

from collections import Counter

from nicegui import ui

from ...core.model import DAY_NAMES, DAY_SHORT
from ...core.sale import building, normalize_room
from ...core.wolne import free_windows
from ..app import nav_set
from ..state import S
from ..theme import badge, card, empty_plan_notice, esc, page_header, now_toggle, pc_badge, tattr
from .nauczyciel import url_for as teacher_url
from .tydzien import slot_tip


def build(room: str | None = None):
    nav_set("/sala")
    tt = S.tt
    with ui.column().classes("ws-page"):
        actions = page_header("Sala")
        if not tt:
            empty_plan_notice()
            return
        room = normalize_room(room) if room else tt.rooms[0]
        with actions:
            now_toggle()
            ui.select(tt.rooms, value=room if room in tt.rooms else None, with_input=True, label="Sala",
                      on_change=lambda e: ui.navigate.to(f"/sala/{e.value}")) \
                .props("outlined dense rounded options-dense").classes("w-40")

        busy = tt.busy_count(room)
        total = len(tt.days) * len(tt.periods)
        with ui.row().classes("items-center gap-4"):
            ui.html(badge(room, link=False).replace("ws-badge", "ws-badge text-xl") , sanitize=False)
            ui.html(f'<div><div style="font-size:18px;font-weight:700;display:flex;gap:10px;align-items:center">'
                    f'{building(room)} {pc_badge(S.inv, room, detailed=True)}</div>'
                    f'<div class="ws-mut">zajęta {busy} z {total} lekcji w tygodniu · wolna {total - busy}</div></div>',
                    sanitize=False)
        if room not in tt.rooms:
            with card():
                ui.label("Tej sali nie ma w planie lekcji (np. zaplecze albo pomieszczenie bez zajęć).") \
                    .classes("ws-mut")

        with ui.row().classes("w-full gap-5 items-start no-wrap"):
            # plan tygodnia
            per = tt.periods
            cols = f"92px repeat({len(tt.days)}, minmax(120px, 1fr))"
            parts = [f'<div class="ws-tt ax-y" style="grid-template-columns:{cols}"><div></div>']
            parts += [f'<div class="h" data-today="{d}">{DAY_NAMES[d]}</div>' for d in tt.days]
            for p in per:
                parts.append(f'<div class="h hd"{tattr(tt, "*", p.nr)} style="text-align:left">{p.nr}'
                             f'<small>{p.start}–{p.end}</small></div>')
                for d in tt.days:
                    ls = tt.lessons_at(room, d, p.nr)
                    tip = slot_tip(tt, room, d, p.nr, ls)
                    if ls:
                        txt = "".join(f"<b>{esc(l.subject)}</b>{esc(l.cls)} {esc(l.group)}"
                                      f"<div class='t'><a class='ws-tlink' href='{teacher_url(l.teacher)}'>{esc(l.teacher)}</a></div>" for l in ls)
                        parts.append(f'<div class="cell b"{tattr(tt, d, p.nr)} data-tip="{tip}">{txt}</div>')
                    else:
                        parts.append(f'<div class="cell f"{tattr(tt, d, p.nr)} data-tip="{tip}">wolna</div>')
            parts.append("</div>")
            with card().classes("flex-1"):
                ui.html("".join(parts), sanitize=False).classes("w-full")

            # panel boczny: wolne okna + sprzęt
            with ui.column().classes("w-80 gap-5"):
                with card():
                    ui.label("Wolne okna").classes("text-lg font-bold mb-2")
                    rows = []
                    for d in tt.days:
                        ws = free_windows(tt, room, d)
                        chips = "".join(
                            f'<span class="ws-chip">{w.periods_label()}<small>{w.time_label(tt)}</small></span>'
                            for w in ws) or '<span class="ws-none">brak</span>'
                        rows.append(f'<div style="display:flex;gap:10px;align-items:baseline;margin:4px 0">'
                                    f'<b style="width:34px">{DAY_SHORT[d]}</b><div>{chips}</div></div>')
                    ui.html("".join(rows), sanitize=False)
                with card():
                    from ...core.sale import base_room
                    from ...core.zadania import progress_summary
                    from .zadania import task_dialog
                    ui.label("Zadania").classes("text-lg font-bold mb-1")
                    open_t = [t for t in S.inv.tasks if not t.done and t.sala and base_room(t.sala) == room]
                    if not open_t:
                        ui.label("Brak otwartych zadań w tej sali").classes("ws-mut text-sm")
                    for t in open_t:
                        over = t.overdue()
                        ui.html(f'<div style="padding:3px 0;cursor:pointer"><b>{esc(t.tytul)}</b>'
                                f'{f" <span style=color:{chr(35)}b91c1c>· po terminie</span>" if over else ""}'
                                f'<div class="ws-mut" style="font-size:12px">{esc(t.termin or "bez terminu")} · '
                                f'{esc(t.priorytet)}</div></div>', sanitize=False) \
                            .on("click", lambda t=t: task_dialog(t, lambda: ui.navigate.to(f"/sala/{room}")))
                    glob = []
                    for g in S.inv.global_tasks:
                        if not g.active:
                            continue
                        _, _, per_room = progress_summary(S.inv, g, S.plan_rooms())
                        rp = next((r for r in per_room if base_room(r.room) == room), None)
                        if rp:
                            glob.append(f'<div style="display:flex;justify-content:space-between;font-size:13px">'
                                        f'<span>☑️ {esc(g.tytul)}</span><b style="color:'
                                        f'{"#15803d" if rp.done == rp.total else "var(--ink)"}">{rp.done}/{rp.total}</b></div>')
                    if glob:
                        ui.html("".join(glob), sanitize=False).classes("w-full mt-2")
                    ui.button("Nowe zadanie w tej sali", icon="add",
                              on_click=lambda: task_dialog(None, lambda: ui.navigate.to(f"/sala/{room}"), room)) \
                        .props("flat no-caps color=primary").classes("mt-1")
                with card():
                    ui.label("Sprzęt").classes("text-lg font-bold mb-2")
                    inv = S.inv
                    if not inv.items:
                        ui.label("Brak spisu — zaimportuj ewidencję w „Spis sprzętu”.").classes("ws-mut")
                    else:
                        here = inv.in_room(room, with_zapl=False)
                        zapl = [i for i in inv.in_room(room) if i.sala.endswith("-ZAPL")]
                        for title, items in (("W sali", here), ("Zaplecze", zapl)):
                            if not items and title == "Zaplecze":
                                continue
                            ui.label(f"{title} ({len(items)})").classes("font-semibold mt-1")
                            c = Counter(i.kategoria for i in items)
                            ui.html("".join(
                                f'<div style="display:flex;justify-content:space-between;padding:3px 0">'
                                f'<span>{esc(k)}</span><b>{n}</b></div>' for k, n in c.most_common())
                                or '<span class="ws-none">brak</span>', sanitize=False).classes("w-full")
                        ui.button("Pokaż w spisie sprzętu", icon="arrow_forward",
                                  on_click=lambda: ui.navigate.to(f"/sprzet?sala={room}")) \
                            .props("flat no-caps color=primary").classes("mt-2")
