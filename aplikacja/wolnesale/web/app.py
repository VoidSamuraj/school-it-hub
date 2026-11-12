"""Główny układ: menu boczne, routing ekranów, wczytywanie planu PDF, start programu."""
from __future__ import annotations

from nicegui import run, ui

from ..core.asc_pdf import PlanParseError, parse_pdf
from ..core.plany import diff_plans
from .state import S
from .theme import CSS, TOOLTIP_JS, esc

NAV = [
    ("Plan", None, None),
    ("/", "search", "Wolne sale"),
    ("/tydzien", "calendar_view_week", "Tydzień"),
    ("/dzien", "today", "Dzień"),
    ("/sala", "meeting_room", "Sale"),
    ("Sprzęt", None, None),
    ("/sprzet", "computer", "Spis sprzętu"),
    ("/zaplecze", "print", "Zaplecze i tusze"),
    ("Praca", None, None),
    ("/zadania", "task_alt", "Zadania"),
    ("/moj-plan", "route", "Mój plan"),
]
SOON: set[str] = set()


def nav_set(path: str) -> None:
    """Podświetla aktywną pozycję menu (wywoływane przez każdy ekran)."""
    buttons = getattr(ui.context.client, "ws_nav", {})
    for p, b in buttons.items():
        if p == path:
            b.classes(add="on").props("color=white")
        else:
            b.classes(remove="on").props("color=blue-grey-3")


def soon_page(title: str, path: str, what: str):
    def build():
        nav_set(path)
        from .theme import card, page_header
        with ui.column().classes("ws-page"):
            page_header(title)
            with card():
                ui.label("Ten ekran jest w przygotowaniu").classes("text-lg font-bold")
                ui.label(what).classes("ws-mut")
    return build


def plan_dialog():
    """Wczytanie nowego PDF-a: upload → analiza → raport → zatwierdzenie."""
    with ui.dialog() as dlg, ui.card().classes("w-[760px] max-w-[95vw] rounded-2xl p-6"):
        ui.label("Wczytaj nowy plan z aSc").classes("text-xl font-bold")
        ui.label("Wybierz PDF z planami nauczycieli. Nic się nie zmieni, dopóki nie zatwierdzisz raportu.") \
            .classes("ws-mut")
        body = ui.column().classes("w-full")

        async def on_upload(e):
            path = S.plan_upload_path(e.file.name)
            await e.file.save(path)
            body.clear()
            with body:
                with ui.row().classes("items-center gap-3"):
                    ui.spinner(size="lg")
                    ui.label(f"Czytam {e.file.name}…")
            try:
                tt, rep = await run.io_bound(parse_pdf, path)
            except PlanParseError as err:
                body.clear()
                with body:
                    ui.label(f"❌ {err}").classes("text-red-700 font-semibold")
                return
            body.clear()
            with body:
                ok = "✅" if rep.ok else "⚠️"
                ui.html(
                    f"<div style='font-size:17px;font-weight:700'>{ok} {esc(tt.source)}</div>"
                    f"<div class='ws-mut'>wygenerowany w aSc {esc(tt.generated or '?')} · stron {rep.pages} · "
                    f"nauczycieli <b>{len(tt.teachers)}</b> · lekcji <b>{rep.lessons}</b> · sal <b>{len(tt.rooms)}</b>"
                    f" · bez sali {rep.lessons_without_room}</div>", sanitize=False)
                lines = []
                old = S.tt
                if old:
                    new_r = sorted(set(tt.rooms) - set(old.rooms))
                    gone = sorted(set(old.rooms) - set(tt.rooms))
                    if new_r:
                        lines.append("🆕 Nowe sale: " + ", ".join(new_r))
                    if gone:
                        lines.append("➖ Sale, których nie ma w nowym planie: " + ", ".join(gone))
                    diffs = diff_plans(old, tt)
                    lines.append(f"📊 Zmiany zajętości ({len(diffs)} sal):")
                    lines += [f"   {d.room:>5}: {d.before:2} → {d.after:2}  ({d.delta:+d})" for d in diffs] or ["   brak"]
                else:
                    lines.append("To pierwszy wczytany plan. Sale: " + ", ".join(tt.rooms))
                lines.append(f"⚠️ Ostrzeżenia ({len(rep.warnings)}):")
                lines += ["   " + w for w in rep.warnings] or ["   brak"]
                ui.code("\n".join(lines), language="text").classes("w-full max-h-80 overflow-auto")
                if not rep.ok:
                    ui.label("Dużo problemów — sprawdź, czy to wydruk planów nauczycieli.") \
                        .classes("text-red-700 font-semibold")

                def accept():
                    S.store.activate(tt, path)
                    S.tt = tt
                    dlg.close()
                    ui.notify(f"Wczytano plan {tt.source}", type="positive")
                    ui.navigate.to("/")

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Anuluj", on_click=dlg.close).props("flat")
                    ui.button("Zatwierdź — ustaw jako aktywny", on_click=accept).props("unelevated color=primary")

        ui.upload(on_upload=on_upload, auto_upload=True, max_files=1) \
            .props('accept=.pdf flat bordered label="Przeciągnij PDF albo kliknij +"').classes("w-full")
        ui.button("Zamknij", on_click=dlg.close).props("flat").classes("self-end")
    dlg.open()


def restore_dialog():
    versions = S.store.versions()
    with ui.dialog() as dlg, ui.card().classes("w-[520px] rounded-2xl p-6"):
        ui.label("Przywróć poprzednią wersję planu").classes("text-xl font-bold")
        if not versions:
            ui.label("Nie ma jeszcze poprzednich wersji.").classes("ws-mut")
        for v in versions[:15]:
            def do(v=v):
                S.tt = S.store.restore(v)
                dlg.close()
                ui.notify("Przywrócono plan", type="positive")
                ui.navigate.to("/")
            ui.button(v.stem, on_click=do).props("flat align=left").classes("w-full")
        ui.button("Zamknij", on_click=dlg.close).props("flat").classes("self-end")
    dlg.open()


def root():
    from .pages import dzien, moj_plan, sala, sprzet, tydzien, wolne, zadania, zaplecze

    ui.add_css(CSS)
    ui.add_head_html('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" '
                     'rel="stylesheet">')
    ui.add_body_html(TOOLTIP_JS)
    ui.colors(primary="#4f46e5")

    with ui.left_drawer(value=True, fixed=True).props("width=240 :breakpoint=700").classes("ws-nav p-3"):
        ui.html('<div class="ws-logo"><span>🏫</span>Wolne Sale</div>', sanitize=False)
        buttons = {}
        for path, icon, label in NAV:
            if icon is None:
                ui.html(f'<div class="ws-sec">{path}</div>', sanitize=False)
                continue
            b = ui.button(label, icon=icon, on_click=lambda p=path: ui.navigate.to(p)) \
                .props("flat no-caps color=blue-grey-3").classes("ws-navbtn")
            if path in SOON:
                b.classes("soon")
                with b:
                    ui.html('<span class="ws-soon">wkrótce</span>', sanitize=False)
            if path == "/zadania":
                n_open = sum(1 for t in S.inv.tasks if not t.done)
                if n_open:
                    with b:
                        ui.html(f'<span class="ws-soon" style="background:#ef4444;color:#fff">{n_open}</span>',
                                sanitize=False)
            buttons[path] = b
        ui.context.client.ws_nav = buttons
        ui.space()
        ui.separator().classes("opacity-20 my-2")
        ui.button("Wczytaj plan (PDF)", icon="upload_file", on_click=plan_dialog) \
            .props("flat no-caps color=blue-grey-3").classes("ws-navbtn")
        ui.button("Poprzednie wersje", icon="history", on_click=restore_dialog) \
            .props("flat no-caps color=blue-grey-3").classes("ws-navbtn")
        if S.tt:
            ui.html(f'<div class="ws-sec" style="text-transform:none;letter-spacing:0">Plan: {esc(S.tt.source)}'
                    f'<br>{len(S.tt.rooms)} sal · {len(S.tt.lessons)} lekcji</div>', sanitize=False)

    for msg in S.errors:
        ui.notify(msg, type="warning", timeout=0, close_button=True)
    S.errors.clear()

    ui.sub_pages({
        "/": wolne.build,
        "/tydzien": tydzien.build,
        "/dzien": dzien.build,
        "/sala": sala.build,
        "/sala/{room}": sala.build,
        "/sprzet": sprzet.build,
        "/zaplecze": zaplecze.build,
        "/zadania": zadania.build,
        "/moj-plan": moj_plan.build,
    }).classes("w-full")


def main(native: bool = True, port: int = 8765, host: str | None = None, show: bool = True) -> None:
    S.load()
    kwargs = dict(root=root, title="Wolne Sale", reload=False, show_welcome_message=False, favicon="🏫",
                  language="pl")
    if native:
        kwargs.update(native=True, window_size=(1480, 920))
    else:
        kwargs.update(port=port, host=host or "127.0.0.1", show=show)
    ui.run(**kwargs)
