"""Ekran „Nauczyciele”: lista nauczycieli z planu i tygodniowy plan wybranego nauczyciela."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, unquote

from nicegui import ui

from ...core.model import DAY_NAMES, DAY_SHORT
from ...core.nauczyciele import hours_by_teacher, teacher_week
from ...core.osoby import _PLACEHOLDERS, norm_key
from ...core.wolne import now_target
from ..app import nav_set
from ..state import S
from ..theme import badge, card, empty_plan_notice, esc, page_header


def url_for(teacher: str) -> str:
    return "/nauczyciel/" + quote(teacher, safe="")


_PL = str.maketrans({"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o",
                     "ś": "s", "ź": "z", "ż": "z"})


def pl_key(s: str) -> str:
    """Klucz sortowania po polsku (ą po a, ł po l…)."""
    return norm_key(s).translate(_PL)


def room_link(room: str | None) -> str:
    if not room:
        return "bez sali"
    return f"<a class='ws-tlink' href='/sala/{quote(room, safe='')}'>📍 sala <b style='display:inline'>{esc(room)}</b></a>"


def _real(t: str) -> bool:
    return bool(t) and not set(norm_key(t).split()) <= _PLACEHOLDERS


def build(name: str | None = None):
    nav_set("/nauczyciel")
    tt = S.tt
    with ui.column().classes("ws-page"):
        actions = page_header("Nauczyciele")
        if not tt:
            empty_plan_notice()
            return
        hours = {t: h for t, h in hours_by_teacher(tt).items() if _real(t)}
        teachers = sorted(hours, key=pl_key)
        name = unquote(name) if name else None
        with actions:
            ui.select(teachers, value=name if name in hours else None, with_input=True, label="Nauczyciel",
                      on_change=lambda e: e.value and ui.navigate.to(url_for(e.value))) \
                .props("outlined dense rounded options-dense").classes("w-72")
        if name:
            teacher_view(tt, name)
        else:
            teacher_list(teachers, hours)


def teacher_list(teachers: list[str], hours: dict[str, int]) -> None:
    st = {"q": ""}
    with card():
        with ui.row().classes("items-center gap-4 w-full"):
            ui.input(placeholder="szukaj nauczyciela…", on_change=lambda e: (st.update(q=e.value or ""),
                                                                             grid.refresh())) \
                .props("outlined dense rounded clearable autofocus").classes("w-72")
            ui.label(f"{len(teachers)} nauczycieli w planie").classes("ws-mut")

        @ui.refreshable
        def grid():
            q = norm_key(st["q"])
            people = S.inv.osoby
            cells = []
            for t in teachers:
                p = people.get(t)
                extra = " ".join([p.aliasy, p.funkcja]) if p else ""
                if q and q not in norm_key(t + " " + extra):
                    continue
                role = p.funkcja if p and p.funkcja not in ("", "nauczyciel") else ""
                cells.append(
                    f'<a class="ws-tcard" href="{url_for(t)}"><b>{esc(t)}</b>'
                    f'<span class="ws-mut">{hours[t]} lekcji/tydz.{" · " + esc(role) if role else ""}</span></a>')
            ui.html('<div class="ws-tgrid">' + ("".join(cells) or '<span class="ws-none">nikogo nie znaleziono</span>')
                    + "</div>", sanitize=False).classes("w-full mt-3")
        grid()


def teacher_view(tt, name: str) -> None:
    w = teacher_week(tt, name)
    person = S.inv.osoby.get(name)
    total = len(tt.days) * len(tt.periods)
    role = person.funkcja if person and person.funkcja else "nauczyciel"
    gaps_total = sum(len(w.gaps(d)) for d in tt.days)

    # „teraz”: podświetl bieżącą (albo najbliższą) lekcję, jeśli to dzisiaj
    nt = now_target(tt, datetime.now())
    now_key = (nt.day, nt.first) if nt.today else None
    now_line = ""
    if now_key:
        ls = w.slots.get(now_key)
        when = "Teraz" if not nt.message else "Następna lekcja"
        if ls:
            l = ls[0]
            now_line = (f'{when} ({nt.first}. lekcja): <b>{esc(l.subject)}</b> {esc(l.cls)} {esc(l.group)} — '
                        f'{badge(l.room) if l.room else "bez sali"}')
        else:
            now_line = f'{when} ({nt.first}. lekcja): <b>nie ma lekcji</b>'

    with ui.row().classes("items-center gap-4"):
        ui.html(f'<div><div style="font-size:22px;font-weight:700">{esc(name)}</div>'
                f'<div class="ws-mut">{esc(role)} · {w.hours} lekcji w tygodniu (z {total}) · '
                f'okienek: {gaps_total}</div>'
                + (f'<div style="margin-top:4px">{now_line}</div>' if now_line else "") + "</div>",
                sanitize=False)
        ui.space()
        ui.button("Wszyscy nauczyciele", icon="arrow_back", on_click=lambda: ui.navigate.to("/nauczyciel")) \
            .props("flat no-caps color=primary")

    with ui.row().classes("w-full gap-5 items-start no-wrap"):
        cols = f"92px repeat({len(tt.days)}, minmax(120px, 1fr))"
        parts = [f'<div class="ws-tt" style="grid-template-columns:{cols}"><div></div>']
        parts += [f'<div class="h">{DAY_NAMES[d]}</div>' for d in tt.days]
        for p in tt.periods:
            parts.append(f'<div class="h" style="text-align:left">{p.nr}<small>{p.start}–{p.end}</small></div>')
            for d in tt.days:
                ls = w.slots.get((d, p.nr), [])
                ring = ' style="outline:2px solid var(--acc);outline-offset:1px"' if (d, p.nr) == now_key else ""
                if ls:
                    txt = "".join(
                        f"<b>{esc(l.subject)}</b>{esc(l.cls)} {esc(l.group)}"
                        f"<div class='t'>{room_link(l.room)}</div>" for l in ls)
                    parts.append(f'<div class="cell b"{ring}>{txt}</div>')
                elif p.nr in w.gaps(d):
                    parts.append(f'<div class="cell gap"{ring}>okienko</div>')
                else:
                    parts.append(f'<div class="cell e"{ring}></div>')
        parts.append("</div>")
        with card().classes("flex-1"):
            ui.html("".join(parts), sanitize=False).classes("w-full")

        with ui.column().classes("w-80 gap-5 shrink-0"):
            with card():
                ui.label("Dni").classes("text-lg font-bold mb-2")
                rows = []
                for d in tt.days:
                    r = w.day_range(d)
                    if not r:
                        desc = '<span class="ws-none">wolne</span>'
                    else:
                        a, b = tt.period_by_nr[r[0]], tt.period_by_nr[r[1]]
                        g = w.gaps(d)
                        desc = (f'{r[0]}–{r[1]} <span class="ws-mut">({a.start}–{b.end})</span>'
                                + (f' · okienka: {", ".join(map(str, g))}' if g else ""))
                    rows.append(f'<div style="display:flex;gap:10px;margin:4px 0"><b style="width:34px">'
                                f'{DAY_SHORT[d]}</b><div>{desc}</div></div>')
                ui.html("".join(rows), sanitize=False)
            with card():
                ui.label("Sale").classes("text-lg font-bold mb-2")
                ui.html("".join(f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                f'padding:2px 0">{badge(r)}<b>{n}</b></div>' for r, n in w.rooms)
                        or '<span class="ws-none">brak</span>', sanitize=False).classes("w-full")
            with card():
                ui.label("Klasy i przedmioty").classes("text-lg font-bold mb-2")
                ui.html('<div class="ws-mut" style="font-size:12px">KLASY</div>'
                        + "".join(f'<span class="ws-chip">{esc(c)}<small>{n}</small></span>' for c, n in w.classes)
                        + '<div class="ws-mut" style="font-size:12px;margin-top:8px">PRZEDMIOTY</div>'
                        + "".join(f'<div style="display:flex;justify-content:space-between"><span>{esc(s)}</span>'
                                  f'<b>{n}</b></div>' for s, n in w.subjects), sanitize=False).classes("w-full")
            if person:
                devs = [i for i in S.inv.items.values() if i.uzytkownik == name]
                with card():
                    ui.label(f"Sprzęt ({len(devs)})").classes("text-lg font-bold mb-2")
                    ui.html("".join(f'<div style="font-size:13px;padding:2px 0">{esc(i.kategoria)} · '
                                    f'{esc(i.nazwa[:40])} <span class="ws-mut">({esc(i.where)})</span></div>'
                                    for i in devs) or '<span class="ws-none">brak</span>', sanitize=False) \
                        .classes("w-full")
                    if person.aliasy:
                        ui.label(f"Inne zapisy: {person.aliasy}").classes("ws-hint")
