"""Ekran „Wolne sale”: jeden wiersz na salę, w każdym dniu połączone wolne okna."""
from __future__ import annotations

from datetime import datetime

from nicegui import ui

from ...core.model import DAY_NAMES, DAY_SHORT
from ...core.sale import BUILDINGS, INNE, building
from ...core.moj_plan import HOURS_OFF, HOURS_ONLY, HOURS_SHOW, free_segments
from ...core.wolne import free_windows, now_target
from ..app import nav_set
from ..state import S
from ..theme import (BCOL, BSHORT, badge, card, empty_plan_notice, esc, page_header, pc_badge,
                     set_on)


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def build():
    nav_set("/")
    tt = S.tt
    with ui.column().classes("ws-page"):
        actions = page_header("Wolne sale", f"Plan: {tt.source}" if tt else None)
        if not tt:
            empty_plan_notice()
            return

        nper = len(tt.periods)
        f = {"days": set(tt.days), "lo": tt.periods[0].nr, "hi": tt.periods[-1].nr, "min": 2,
             "bld": None, "q": "", "sort": "room", "pc": None,
             "hours": HOURS_SHOW if S.inv.work_hours.defined else HOURS_OFF}
        inv = S.inv

        # ---------------- filtry
        with card():
            with ui.row().classes("items-start gap-x-8 gap-y-4 w-full ws-filters"):
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Dni</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        day_btns = {}
                        for d in tt.days:
                            def tog(d=d):
                                f["days"] ^= {d}
                                paint()
                                results.refresh()
                            day_btns[d] = ui.button(DAY_SHORT[d], on_click=tog).props("flat dense no-caps")
                    ui.html('<span class="ws-hint">&nbsp;</span>', sanitize=False)
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Lekcje</span>', sanitize=False)
                    with ui.row().classes("items-center gap-3 no-wrap ws-range"):
                        lo_lab = ui.label().classes("font-semibold text-right whitespace-nowrap").style("width:76px")
                        rng = ui.range(min=tt.periods[0].nr, max=tt.periods[-1].nr, step=1,
                                       value={"min": f["lo"], "max": f["hi"]}).props("markers snap").classes("w-52")
                        hi_lab = ui.label().classes("font-semibold whitespace-nowrap").style("width:84px")
                    ui.html('<span class="ws-hint">&nbsp;</span>', sanitize=False)
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Potrzebuję sali na</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        min_btns = {}
                        for n in (1, 2, 3, 4):
                            def setmin(n=n):
                                f["min"] = n
                                paint()
                                results.refresh()
                            label = {1: "1 lekcję", 2: "2", 3: "3", 4: "4+"}[n]
                            min_btns[n] = ui.button(label, on_click=setmin).props("flat dense no-caps")
                    min_hint = ui.html("", sanitize=False).classes("ws-hint")
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Komputery</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        pc_btns = {}
                        for key, label in ((None, "Wszystkie"), ("it", "💻 Sale IT"), ("any", "🖥 Z komputerem")):
                            def setpc(key=key):
                                f["pc"] = key
                                paint()
                                results.refresh()
                            pc_btns[key] = ui.button(label, on_click=setpc).props("flat dense no-caps")
                    if not inv.items:
                        ui.html('<span class="ws-hint">zaimportuj spis sprzętu, żeby filtrować</span>',
                                sanitize=False)
                    else:
                        ui.html('<span class="ws-hint">&nbsp;</span>', sanitize=False)
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Moje godziny pracy</span>', sanitize=False)
                    with ui.row().classes("ws-seg"):
                        hours_btns = {}
                        for key, label in ((HOURS_OFF, "Pomiń"), (HOURS_SHOW, "🌙 Zaznacz po godzinach"),
                                           (HOURS_ONLY, "Tylko w godzinach")):
                            def seth(key=key):
                                f["hours"] = key
                                paint()
                                results.refresh()
                            hb = ui.button(label, on_click=seth).props("flat dense no-caps")
                            if not inv.work_hours.defined and key != HOURS_OFF:
                                hb.disable()
                            hours_btns[key] = hb
                    hours_hint = ui.html("", sanitize=False).classes("ws-hint")
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Budynek</span>', sanitize=False)
                    with ui.row().classes("gap-2"):
                        bld_btns = {}
                        for b in [None] + [b for b in BUILDINGS if b != INNE]:
                            def setb(b=b):
                                f["bld"] = b
                                paint()
                                results.refresh()
                            label = "Wszystkie" if b is None else BSHORT[b]
                            btn = ui.button(on_click=setb).props("flat dense no-caps").classes("ws-chipbtn")
                            with btn:
                                if b:
                                    ui.html(f'<span class="ws-dot" style="background:{BCOL[b]}"></span>', sanitize=False)
                                ui.label(label)
                            bld_btns[b] = btn
                with ui.column().classes("gap-0"):
                    ui.html('<span class="ws-flabel">Sala</span>', sanitize=False)
                    ui.input(placeholder="np. 11w",
                             on_change=lambda e: (f.update(q=e.value or ""), results.refresh())) \
                        .props("outlined dense rounded clearable").classes("w-40")

        def paint():
            for d, b in day_btns.items():
                set_on(b, d in f["days"])
            for n, b in min_btns.items():
                set_on(b, n == f["min"])
            for k, b in bld_btns.items():
                set_on(b, k == f["bld"])
            for k, b in pc_btns.items():
                set_on(b, k == f["pc"])
            for k, b in hours_btns.items():
                set_on(b, k == f["hours"])
            for k, b in sort_btns.items():
                set_on(b, k == f["sort"])
            hours_hint.content = (
                '<a href="/moj-plan" style="color:var(--acc)">ustaw godziny w „Mój plan”</a>'
                if not inv.work_hours.defined else
                {HOURS_OFF: "godziny pracy nie mają wpływu",
                 HOURS_SHOW: "🌙 fioletowe = wolne, ale już po moich godzinach",
                 HOURS_ONLY: "pokazuję tylko to, co mieści się w moich godzinach"}[f["hours"]])
            n = f["min"]
            min_hint.content = ("pokazuję każdą wolną lekcję" if n == 1 else
                                f"tylko okna min. {n} wolnych lekcji pod rząd") + \
                (" — liczone w moich godzinach pracy" if f["hours"] == HOURS_ONLY else "")
            lo_lab.text = f'{f["lo"]} · {tt.period_by_nr[f["lo"]].start}'
            hi_lab.text = f'{f["hi"]} · {tt.period_by_nr[f["hi"]].end}'

        def on_range(e):
            v = e.value or {}
            if (int(v["min"]), int(v["max"])) == (f["lo"], f["hi"]):
                return
            f["lo"], f["hi"] = int(v["min"]), int(v["max"])
            paint()
            results.refresh()
        rng.on_value_change(on_range)

        def now():
            t = now_target(tt, datetime.now())
            f.update(days={t.day}, lo=t.first, hi=tt.periods[-1].nr, min=1)
            rng.value = {"min": f["lo"], "max": f["hi"]}
            paint()
            results.refresh()
            ui.notify(t.message, type="info" if t.today else "warning", position="top", timeout=6000)

        with actions:
            ui.html('<span class="ws-flabel" style="margin:0 4px 0 0">Sortuj</span>', sanitize=False)
            with ui.row().classes("ws-seg"):
                sort_btns = {}
                for key, label in (("room", "wg sali"), ("free", "najwięcej wolnego")):
                    def sets(key=key):
                        f["sort"] = key
                        paint()
                        results.refresh()
                    sort_btns[key] = ui.button(label, on_click=sets).props("flat dense no-caps")
            ui.button("Co jest wolne teraz?", icon="schedule", on_click=now) \
                .props("unelevated no-caps color=primary").classes("ml-2")

        # ---------------- wyniki
        @ui.refreshable
        def results():
            days = [d for d in tt.days if d in f["days"]]
            q = f["q"].strip().upper()
            rows = []
            span = f["hi"] - f["lo"] + 1
            for room in tt.rooms:
                if f["bld"] and building(room) != f["bld"]:
                    continue
                if q and q not in room.upper():
                    continue
                if f["pc"] == "it" and inv.room_kind(room) != "it":
                    continue
                if f["pc"] == "any" and not inv.room_kind(room):
                    continue
                per_day, total = [], 0
                for d in days:
                    segs = free_segments(tt, inv.work_hours, room, d, f["lo"], f["hi"], f["min"], f["hours"])
                    total += sum(b2 - a + 1 for a, b2, _ in segs)
                    per_day.append((d, segs))
                if total:
                    rows.append((room, per_day, total))
            if f["sort"] == "free":
                rows.sort(key=lambda r: -r[2])
            max_total = max(1, span * len(days))
            cols = f"190px repeat({max(1, len(days))},minmax(110px,1fr)) 150px"

            out = [f'<div class="ws-fgrid"><div class="ws-head" style="grid-template-columns:{cols}">'
                   f'<div>Sala</div>' + "".join(f"<div>{DAY_SHORT[d]}</div>" for d in days) +
                   "<div>Wolne razem</div></div>"]
            for room, per_day, total in rows:
                cells = []
                for d, segs in per_day:
                    if not segs:
                        cells.append('<div><span class="ws-none">—</span></div>')
                        continue
                    chips = ""
                    for a, b2, inside in segs:
                        lab = f"{a}" if a == b2 else f"{a}–{b2}"
                        times = f"{tt.period_by_nr[a].start}–{tt.period_by_nr[b2].end}"
                        chips += (f'<span class="ws-chip{"" if inside else " night"}" data-tip="<b>{esc(room)}</b> · '
                                  f'{DAY_NAMES[d]}&#10;lekcje {lab}&#10;{times}'
                                  f'{"" if inside else "&#10;🌙 poza moimi godzinami pracy"}">'
                                  f'{"" if inside else "🌙 "}{lab}<small>{tt.period_by_nr[a].start}</small></span>')
                    cells.append(f"<div>{chips}</div>")
                pct = round(100 * total / max_total)
                b = building(room)
                out.append(
                    f'<a class="ws-row" href="/sala/{esc(room)}" style="grid-template-columns:{cols}">'
                    f'<div style="display:flex;gap:12px;align-items:center">{badge(room, link=False)}'
                    f'<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start">'
                    f'<span class="ws-mut" style="font-size:13px">{BSHORT[b]}</span>{pc_badge(inv, room)}</div></div>'
                    + "".join(cells) +
                    f'<div style="font-size:13px" class="ws-mut"><b style="font-size:17px;color:var(--ink)">{total}</b>'
                    f' lekcji<div class="ws-bar"><i style="width:{pct}%"></i></div></div></a>')
            if not rows:
                out.append('<div class="ws-mut" style="padding:18px 12px">Brak wolnych sal dla tych ustawień.</div>')
            out.append("</div>")
            with card():
                ui.html("".join(out), sanitize=False).classes("w-full")
                ui.label(f"{len(rows)} sal · zielone okienko = ciąg wolnych lekcji pod rząd (np. „3–5” = lekcje 3, 4 i 5); "
                         "najedź, by zobaczyć godziny; kliknij wiersz, by otworzyć plan sali.") \
                    .classes("ws-mut text-sm mt-3")

        paint()
        results()
