"""Ekran „Dzień”: sale × lekcje jednego dnia, z klasą i przedmiotem."""
from __future__ import annotations

from datetime import date

from nicegui import ui

from ...core.model import DAY_SHORT
from ..app import nav_set
from ..state import S
from ..theme import badge, card, empty_plan_notice, esc, now_toggle, page_header, pc_badge, set_on, tattr
from .tydzien import room_filters, room_passes, slot_tip


def build():
    nav_set("/dzien")
    tt = S.tt
    with ui.column().classes("ws-page"):
        actions = page_header("Dzień")
        if not tt:
            empty_plan_notice()
            return
        with actions:
            now_toggle()
        today = date.today().weekday()
        st = {"day": today if today in tt.days else tt.days[0], "bld": None, "pc": None, "q": ""}

        def day_group():
            with ui.column().classes("gap-0"):
                ui.html('<span class="ws-flabel">Dzień</span>', sanitize=False)
                with ui.row().classes("ws-seg"):
                    btns = {}
                    for d in tt.days:
                        def setd(d=d):
                            st["day"] = d
                            for k, b in btns.items():
                                set_on(b, k == d)
                            grid.refresh()
                        btns[d] = ui.button(DAY_SHORT[d] + (" · dziś" if d == today else ""), on_click=setd) \
                            .props("flat dense no-caps")
                        set_on(btns[d], d == st["day"])
                ui.html('<span class="ws-hint">&nbsp;</span>', sanitize=False)

        room_filters(st, lambda: grid.refresh(), extra=day_group)

        @ui.refreshable
        def grid():
            d = st["day"]
            rooms = [r for r in tt.rooms if room_passes(st, r)]
            per = tt.periods
            wh = S.inv.work_hours
            cols = f"110px repeat({len(per)}, minmax(92px, 1fr))"
            parts = [f'<div class="ws-tt ax-x" style="grid-template-columns:{cols};padding-top:14px"><div></div>']
            parts += [f'<div class="h hd"{tattr(tt, d, p.nr)}>{p.nr}<small>{p.start}–{p.end}</small></div>'
                      for p in per]
            for room in rooms:
                parts.append(f'<div class="r" style="flex-direction:column;align-items:flex-start;gap:3px">'
                             f'{badge(room)}{pc_badge(S.inv, room)}</div>')
                for p in per:
                    ls = tt.lessons_at(room, d, p.nr)
                    tip = slot_tip(tt, room, d, p.nr, ls)
                    off = "" if wh.lesson_in_hours(tt, d, p.nr) else " off"
                    if off:
                        tip += "&#10;🌙 poza moimi godzinami pracy"
                    if ls:
                        seen = list(dict.fromkeys((l.cls, l.subject) for l in ls))
                        txt = "".join(f"<b>{esc(c)}</b><span class='t'>{esc(s)}</span><br>" for c, s in seen)
                        parts.append(f'<div class="cell b{off}"{tattr(tt, d, p.nr)} data-tip="{tip}">{txt}</div>')
                    else:
                        parts.append(f'<div class="cell f{off}"{tattr(tt, d, p.nr)} data-tip="{tip}">wolna</div>')
            parts.append("</div>")
            with card():
                if not rooms:
                    ui.label("Brak sal dla tych filtrów.").classes("ws-mut")
                else:
                    ui.label(f"{len(rooms)} sal").classes("ws-mut text-sm mb-2")
                    ui.html("".join(parts), sanitize=False).classes("w-full")

        grid()
