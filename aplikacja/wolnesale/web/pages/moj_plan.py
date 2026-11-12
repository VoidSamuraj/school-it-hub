"""Ekran „Mój plan”: tygodniowy grafik godzin pracy (od–do wg zegara, powtarzany co tydzień).

Godziny pracy wpływają na resztę programu: w Wolnych salach okna po godzinach są oznaczone 🌙,
a w Tygodniu lekcje poza godzinami pracy są zakreskowane.
"""
from __future__ import annotations

from nicegui import ui

from ...core.model import DAY_NAMES
from ...core.moj_plan import _hm
from ..app import nav_set
from ..state import S
from ..theme import card, esc, page_header

AXIS_FROM, AXIS_TO = 6 * 60, 20 * 60          # oś czasu 6:00–20:00


def _min(s: str) -> int:
    h, m = _hm(s)
    return h * 60 + m


def _fmt_dur(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"


def _save(msg: str | None = None) -> None:
    err = S.save_inventory()
    if err:
        ui.notify(err, type="warning", timeout=8000, close_button=True)
    elif msg:
        ui.notify(msg, type="positive")


def build():
    nav_set("/moj-plan")
    days = S.tt.days if S.tt else [0, 1, 2, 3, 4]
    wh = S.inv.work_hours
    # robocza kopia do edycji: dzień -> lista [od, do] w formacie HH:MM (pole typu „time” tego wymaga)
    def pad(s: str) -> str:
        hm = _hm(s)
        return f"{hm[0]:02d}:{hm[1]:02d}" if hm else ""
    draft = {d: [[pad(a), pad(b)] for a, b in wh.days.get(d, [])] for d in days}

    with ui.column().classes("ws-page"):
        actions = page_header("Mój plan", "godziny pracy · co tydzień")
        with actions:
            ui.button("Zapisz", icon="save", on_click=lambda: save()).props("unelevated no-caps color=primary")

        @ui.refreshable
        def timeline():
            week_timeline(draft, days)

        @ui.refreshable
        def editor():
            with card():
                ui.label("Godziny pracy w poszczególne dni").classes("text-lg font-bold")
                ui.label("Wpisz, od której do której jesteś w pracy. Możesz dodać kilka przedziałów "
                         "w jednym dniu (np. przerwa). Dzień bez przedziałów = wolne.").classes("ws-hint mb-2")
                for d in days:
                    with ui.row().classes("w-full items-center gap-3 py-2").style("border-top:1px solid var(--line)"):
                        ui.label(DAY_NAMES[d]).classes("font-semibold").style("width:120px")
                        with ui.row().classes("flex-1 items-center gap-3"):
                            if not draft[d]:
                                ui.label("wolne").classes("ws-mut")
                            for i, iv in enumerate(draft[d]):
                                with ui.row().classes("items-center gap-1 no-wrap") \
                                        .style("background:#f1f3f9;border-radius:12px;padding:2px 6px"):
                                    def setv(e, d=d, i=i, k=0):
                                        draft[d][i][k] = e.value or ""
                                        timeline.refresh()
                                    ui.input(value=iv[0], on_change=lambda e, d=d, i=i: setv(e, d, i, 0)) \
                                        .props("dense borderless type=time").style("width:92px")
                                    ui.label("–")
                                    ui.input(value=iv[1], on_change=lambda e, d=d, i=i: setv(e, d, i, 1)) \
                                        .props("dense borderless type=time").style("width:92px")
                                    ui.button(icon="close", on_click=lambda d=d, i=i: remove(d, i)) \
                                        .props("flat round dense size=sm color=grey-7")
                            ui.button("przedział", icon="add", on_click=lambda d=d: add(d)) \
                                .props("flat dense no-caps color=primary")
                        total = day_minutes(draft[d])
                        ui.label(_fmt_dur(total) if total else "").classes("ws-mut").style("width:90px;text-align:right")
                with ui.row().classes("w-full items-center mt-2"):
                    ui.button("Skopiuj poniedziałek na wszystkie dni", icon="content_copy", on_click=copy_first) \
                        .props("flat no-caps color=primary")
                    ui.space()
                    week = sum(day_minutes(draft[d]) for d in days)
                    ui.html(f'<span class="ws-mut">Razem w tygodniu:</span> <b>{_fmt_dur(week)}</b>', sanitize=False)

        def day_minutes(ivs) -> int:
            tot = 0
            for a, b in ivs:
                if _hm(a or "") and _hm(b or "") and _min(b) > _min(a):
                    tot += _min(b) - _min(a)
            return tot

        def add(d):
            last_end = draft[d][-1][1] if draft[d] else ""
            draft[d].append([last_end or "07:30", "15:30" if not last_end else ""])
            editor.refresh()
            timeline.refresh()

        def remove(d, i):
            draft[d].pop(i)
            editor.refresh()
            timeline.refresh()

        def copy_first():
            src = draft[days[0]]
            for d in days[1:]:
                draft[d] = [list(x) for x in src]
            editor.refresh()
            timeline.refresh()

        def save():
            for d in days:
                text = ", ".join(f"{a}-{b}" for a, b in draft[d] if a and b)
                err = wh.set_text(d, text)
                if err:
                    ui.notify(f"{DAY_NAMES[d]}: {err}", type="warning")
                    return
            _save("Zapisano godziny pracy")
            editor.refresh()

        timeline()
        editor()
        with card():
            ui.label("Gdzie to widać").classes("font-bold")
            ui.html('<div class="ws-mut" style="font-size:13px;line-height:1.6">'
                    '🔎 <b>Wolne sale</b> — przełącznik „🌙 Moje godziny pracy”: okna po godzinach są fioletowe z 🌙.<br>'
                    '🗓 <b>Tydzień</b> — lekcje poza godzinami pracy są zakreskowane.<br>'
                    'Lekcja liczy się „w godzinach”, gdy w całości mieści się w którymś przedziale.</div>',
                    sanitize=False)


def week_timeline(draft: dict, days: list[int]) -> None:
    """Oś 6:00–20:00: bloki godzin pracy + lekcje z planu jako cienkie paski w tle."""
    tt = S.tt
    span = AXIS_TO - AXIS_FROM

    def pct(m: int) -> float:
        return max(0.0, min(100.0, (m - AXIS_FROM) * 100 / span))

    hours = range(AXIS_FROM // 60, AXIS_TO // 60 + 1, 2)
    ticks = "".join(f'<div style="position:absolute;left:{pct(h * 60)}%;top:0;bottom:0;'
                    f'border-left:1px dashed #e5e7eb"></div>' for h in hours)
    axis = ('<div style="display:flex;gap:12px"><div style="width:110px"></div>'
            '<div style="position:relative;flex:1;height:16px">'
            + "".join(f'<div style="position:absolute;left:{pct(h * 60)}%;transform:translateX(-50%);'
                      f'font-size:11px;color:var(--mut)">{h}:00</div>' for h in hours)
            + "</div></div>")
    rows = [axis]
    for d in days:
        lessons = ""
        if tt:
            lessons = "".join(
                f'<div data-tip="Lekcja {p.nr}&#10;{p.start}–{p.end}" style="position:absolute;left:{pct(_min(p.start))}%;'
                f'width:{pct(_min(p.end)) - pct(_min(p.start))}%;bottom:2px;height:6px;border-radius:3px;'
                f'background:#cbd5e1"></div>' for p in tt.periods)
        blocks = ""
        for a, b in draft.get(d, []):
            if not (_hm(a or "") and _hm(b or "")) or _min(b) <= _min(a):
                continue
            blocks += (f'<div data-tip="Praca&#10;{esc(a)}–{esc(b)}" style="position:absolute;left:{pct(_min(a))}%;'
                       f'width:{pct(_min(b)) - pct(_min(a))}%;top:4px;bottom:12px;border-radius:8px;'
                       f'background:linear-gradient(90deg,#6366f1,#4f46e5);color:#fff;font-size:12px;font-weight:600;'
                       f'display:flex;align-items:center;justify-content:center;white-space:nowrap;overflow:hidden">'
                       f'{esc(a)}–{esc(b)}</div>')
        rows.append(f'<div style="display:flex;align-items:center;gap:12px;margin:6px 0">'
                    f'<div style="width:110px;font-weight:600">{DAY_NAMES[d]}</div>'
                    f'<div style="position:relative;flex:1;height:44px;background:#f8fafc;border-radius:10px">'
                    f'{ticks}{lessons}{blocks}</div></div>')
    with card():
        ui.html('<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
                '<b style="font-size:17px">Mój tydzień</b>'
                '<span class="ws-mut" style="font-size:12px">fiolet = praca · szare paski = lekcje w szkole</span></div>'
                + "".join(rows), sanitize=False).classes("w-full")
