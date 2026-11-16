"""Ekran „Tydzień”: wszystkie sale × dni × lekcje, z odstępami między dniami i dymkami."""
from __future__ import annotations

from nicegui import ui

from ...core.model import DAY_NAMES, DAY_SHORT, Timetable
from ...core.sale import BUILDINGS, INNE, building
from ..app import nav_set
from ..state import S
from ..theme import (BCOL, BSHORT, badge, card, empty_plan_notice, esc, page_header, pc_badge,
                     now_toggle, set_on, tattr)


def slot_tip(tt: Timetable, room: str, d: int, nr: int, ls) -> str:
    p = tt.period_by_nr[nr]
    head = f"<b>{esc(room)}</b> · {DAY_NAMES[d]} · lekcja {nr}&#10;🕒 {p.start}–{p.end}"
    if not ls:
        return head + "&#10;✅ wolna"
    lines = [f"⛔ {esc(l.subject)} · {esc(l.cls)}{(' ' + esc(l.group)) if l.group else ''}&#10;"
             f"&#160;&#160;&#160;&#160;👤 {esc(l.teacher)}" for l in ls]
    return head + "&#10;" + "&#10;".join(lines)


def building_filter(state: dict, on_change):
    with ui.row().classes("gap-2"):
        btns = {}
        for b in [None] + [b for b in BUILDINGS if b != INNE]:
            def setb(b=b):
                state["bld"] = b
                for k, x in btns.items():
                    set_on(x, k == b)
                on_change()
            btn = ui.button(on_click=setb).props("flat dense no-caps").classes("ws-chipbtn")
            with btn:
                if b:
                    ui.html(f'<span class="ws-dot" style="background:{BCOL[b]}"></span>', sanitize=False)
                ui.label("Wszystkie" if b is None else BSHORT[b])
            btns[b] = btn
        for k, x in btns.items():
            set_on(x, k is None)


def room_filters(state: dict, on_change, extra=None) -> None:
    """Wspólny pasek filtrów sal (jak w Wolnych salach): budynek, komputery, sala.

    state: klucze "bld", "pc" (None / "it" / "any"), "q". `extra` — funkcja dokładająca własne grupy na początku.
    """
    state.setdefault("bld", None)
    state.setdefault("pc", None)
    state.setdefault("q", "")
    inv = S.inv
    with card():
        with ui.row().classes("items-start gap-x-8 gap-y-4 w-full ws-filters"):
            if extra:
                extra()
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Budynek</span>', sanitize=False)
                building_filter(state, on_change)
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Komputery</span>', sanitize=False)
                with ui.row().classes("ws-seg"):
                    pc_btns = {}
                    for key, label in ((None, "Wszystkie"), ("it", "💻 Sale IT"), ("any", "🖥 Z komputerem")):
                        def setpc(key=key):
                            state["pc"] = key
                            for k, b in pc_btns.items():
                                set_on(b, k == key)
                            on_change()
                        pc_btns[key] = ui.button(label, on_click=setpc).props("flat dense no-caps")
                        set_on(pc_btns[key], key == state["pc"])
                        if key and not inv.items:
                            pc_btns[key].disable()
                ui.html('<span class="ws-hint">' + ("zaimportuj spis sprzętu, żeby filtrować" if not inv.items
                                                    else "&nbsp;") + "</span>", sanitize=False)
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Sala</span>', sanitize=False)
                ui.input(placeholder="np. 11w", on_change=lambda e: (state.update(q=e.value or ""), on_change())) \
                    .props("outlined dense rounded clearable").classes("w-40")


def room_passes(state: dict, room: str) -> bool:
    if state.get("bld") and building(room) != state["bld"]:
        return False
    q = (state.get("q") or "").strip().upper()
    if q and q not in room.upper():
        return False
    pc = state.get("pc")
    if pc == "it" and S.inv.room_kind(room) != "it":
        return False
    if pc == "any" and not S.inv.room_kind(room):
        return False
    return True


def build():
    nav_set("/tydzien")
    tt = S.tt
    with ui.column().classes("ws-page"):
        actions = page_header("Tydzień", "najedź na kratkę, by zobaczyć szczegóły")
        if not tt:
            empty_plan_notice()
            return
        with actions:
            now_toggle()
        st = {"bld": None}
        room_filters(st, lambda: grid.refresh())
        with ui.row().classes("items-center gap-6 w-full"):
            ui.space()
            ui.html('<span class="ws-c f" style="display:inline-block;vertical-align:middle"></span> wolna &nbsp; '
                    '<span class="ws-c b" style="display:inline-block;vertical-align:middle"></span> zajęta'
                    + (' &nbsp; <span class="ws-c f off" style="display:inline-block;vertical-align:middle"></span>'
                       ' poza moimi godzinami' if S.inv.work_hours.defined else ''),
                    sanitize=False).classes("ws-mut text-sm")

        @ui.refreshable
        def grid():
            rooms = [r for r in tt.rooms if room_passes(st, r)]
            per = tt.periods
            wh = S.inv.work_hours
            h1 = ['<th></th>']
            h2 = ['<th></th>']
            for i, d in enumerate(tt.days):
                if i:
                    h1.append('<th class="gap"></th>')
                    h2.append('<th class="gap"></th>')
                h1.append(f'<th class="day" data-today="{d}" colspan="{len(per)}">{DAY_NAMES[d]}</th>')
                h2 += [f'<th class="hd"{tattr(tt, d, p.nr)} data-tip="Lekcja {p.nr}&#10;🕒 {p.start}–{p.end}">'
                       f'{p.nr}</th>' for p in per]
            h1.append("<th></th>")
            h2.append('<th style="text-align:left;padding-left:12px">wolne</th>')
            body = []
            total = len(tt.days) * len(per)
            for room in rooms:
                cells = [f'<td class="room">{badge(room)} {pc_badge(S.inv, room)}</td>']
                free = 0
                for i, d in enumerate(tt.days):
                    if i:
                        cells.append('<td class="gap"></td>')
                    for p in per:
                        ls = tt.lessons_at(room, d, p.nr)
                        free += not ls
                        cls = "b" if ls else "f"
                        tip = slot_tip(tt, room, d, p.nr, ls)
                        if not wh.lesson_in_hours(tt, d, p.nr):
                            cls += " off"
                            tip += "&#10;🌙 poza moimi godzinami pracy"
                        cells.append(f'<td{tattr(tt, d, p.nr)}><span class="ws-c {cls}" data-tip="{tip}"></span></td>')
                cells.append(f'<td class="free"><b>{free}</b>/{total}</td>')
                body.append("<tr>" + "".join(cells) + "</tr>")
            html = (f'<div class="ws-week ax-x"><table><thead><tr>{"".join(h1)}</tr><tr>{"".join(h2)}</tr></thead>'
                    f'<tbody>{"".join(body)}</tbody></table></div>')
            with card():
                ui.html(html, sanitize=False).classes("w-full")

        grid()
