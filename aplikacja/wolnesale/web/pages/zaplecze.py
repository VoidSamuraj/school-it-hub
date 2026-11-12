"""Ekran „Zaplecze i tusze”: stany materiałów, przyjęcia/wydania, co dokupić, drukarki wg modelu."""
from __future__ import annotations

from nicegui import ui

from datetime import date, datetime

from ...core.zaplecze import (COLORS, LEAD_DAYS, MATERIAL_TYPES, SCHEME_LABELS, SCHEME_SHORT,
                              USAGE_WINDOW_DAYS, Material, guess_model, printer_models, printers_for,
                              stock_change, suggested_buy, to_buy, usage)
from ..app import nav_set
from ..state import S
from ...core.sale import base_room, building, sort_key
from ..theme import BCOL, card, esc, page_header

COLOR_DOT = {"czarny": "#111827", "cyan": "#06b6d4", "magenta": "#d946ef", "żółty": "#facc15",
             "kolor (zestaw)": "conic-gradient(#06b6d4,#d946ef,#facc15,#06b6d4)"}


def _save(msg: str | None = None) -> None:
    err = S.save_inventory()
    if err:
        ui.notify(err, type="warning", timeout=8000, close_button=True)
    elif msg:
        ui.notify(msg, type="positive")


def _dot(kolor: str) -> str:
    c = COLOR_DOT.get(kolor)
    return f'<span class="ws-dot" style="background:{c};width:11px;height:11px"></span>' if c else ""


def _months(days: float) -> str:
    if days < 45:
        return f"{int(days)} dni"
    return f"{days / 30.4:.1f} mies.".replace(".", ",", 1)


def usage_line(inv, m: Material) -> str:
    """Jedna linijka: średnie zużycie, na ile wystarczy zapas, ostatnia wymiana."""
    u = usage(inv, m.kod)
    if not u.replacements:
        return ('<div class="ws-hint" data-tip="Każde „−” zapisuje wymianę z datą.&#10;'
                'Dawne wymiany dopiszesz z datą wsteczną.">📈 brak danych o zużyciu</div>')
    parts = []
    if u.per_month is not None:
        parts.append(f"≈ {u.per_month:.1f} szt./mies.".replace(".", ","))
    if u.days_left is not None:
        warn = u.days_left < LEAD_DAYS
        parts.append(f'<b style="color:{"#b91c1c" if warn else "#15803d"}">zapas na {_months(u.days_left)}</b>'
                     f' (do ~{u.runout:%d.%m.%Y})')
    last = u.last
    parts.append(f"ostatnio {last.when:%d.%m.%Y}" + (f" ({esc(last.sala)})" if last.sala else ""))
    if u.few_data:
        parts.append("<i>mało danych</i>")
    return f'<div style="font-size:12px;margin-top:2px">📈 {" · ".join(parts)}</div>'


TILE = ("padding:16px 20px;width:auto;min-width:180px;height:100%;box-sizing:border-box;"
        "display:flex;flex-direction:column;justify-content:space-between;gap:6px")


def _stat(value, label: str, color: str = "var(--ink)", bg: str = "#fff") -> None:
    ui.html(f'<div class="ws-card" style="background:{bg};{TILE}">'
            f'<div style="font-size:28px;font-weight:700;line-height:1.1;color:{color}">{value}</div>'
            f'<div class="ws-mut" style="font-size:13px">{label}</div></div>', sanitize=False).style("display:flex")


def _breakdown_tile(by_scheme: dict[str, int]) -> None:
    """Kafelka: ile drukarek ma 1 / 2 / 4 wkłady, ile jeszcze nieustawionych."""
    order = ["tylko czarny", "czarny + kolor", "CMYK (4 osobne)", "nie dotyczy", ""]
    names = {**SCHEME_SHORT, "": "nie ustawiono"}
    rows = "".join(
        f'<span style="{"color:#b45309" if k == "" else ""}">{esc(names[k])}</span>'
        f'<b style="text-align:right;{"color:#b45309" if k == "" else ""}">{by_scheme[k]}</b>'
        for k in order if by_scheme.get(k))
    ui.html(f'<div class="ws-card" style="{TILE};min-width:240px">'
            f'<div style="display:grid;grid-template-columns:1fr auto;gap:2px 18px;font-size:13.5px">{rows}</div>'
            f'<div class="ws-mut" style="font-size:13px">drukarek wg liczby wkładów</div></div>',
            sanitize=False).style("display:flex")


def build():
    nav_set("/zaplecze")
    inv = S.inv

    with ui.column().classes("ws-page"):
        actions = page_header("Zaplecze i tusze")
        view = {"models": "todo", "edit": False}

        def toggle_edit(e):
            view["edit"] = e.value
            add_btn.set_visibility(e.value)
            content.refresh()

        with actions:
            ui.switch("Tryb edycji", value=False, on_change=toggle_edit).props("color=primary") \
                .tooltip("Włącz, żeby dodawać i zmieniać wkłady oraz ustawiać drukarki")
            add_btn = ui.button("Dodaj wkład", icon="add", on_click=lambda: material_dialog(None, content.refresh)) \
                .props("unelevated no-caps color=primary")
            add_btn.set_visibility(False)

        @ui.refreshable
        def content():
            mats = sorted(inv.materials.values(), key=lambda m: (m.typ, m.kod))
            buy = to_buy(inv)
            models = printer_models(inv)
            todo = [g for g in models if g.scheme != "nie dotyczy" and (not g.scheme or g.missing)]
            n_pr = sum(len(g.printers) for g in models)
            by_scheme: dict[str, int] = {}
            for g in models:
                key = "" if g.scheme_guessed and not g.scheme else g.scheme
                by_scheme[key] = by_scheme.get(key, 0) + len(g.printers)

            with ui.row().classes("gap-4").style("align-items:stretch"):
                _stat(n_pr, f"drukarek w spisie · {len(models)} modeli")
                _breakdown_tile(by_scheme)
                _stat(sum(m.ilosc for m in mats), f"sztuk na stanie · {len(mats)} rodzajów")
                _stat(len(buy), "🛒 do dokupienia", "#b91c1c" if buy else "#15803d", "#fef2f2" if buy else "#fff")
                _stat(len(todo), "modeli do uzupełnienia (kolory / tusze)",
                      "#b45309" if todo else "#15803d", "#fffbeb" if todo else "#fff")

            with ui.row().classes("w-full gap-5 items-start no-wrap"):
                # ---- materiały
                with card().classes("flex-1 min-w-0"):
                    ui.label("Wkłady na stanie (tusze, tonery…)").classes("text-lg font-bold mb-2")
                    if not mats:
                        ui.label("Brak wkładów. Włącz „Tryb edycji” i dodaj wkład albo kliknij brakujący kolor przy modelu "
                                 "drukarki w sekcji poniżej.").classes("ws-mut")
                    for m in mats:
                        low = m.ilosc < m.minimum
                        ps = printers_for(inv, m)
                        with ui.row().classes("w-full items-center gap-3 no-wrap py-2") \
                                .style("border-top:1px solid var(--line)"):
                            ui.html(
                                f'<div style="min-width:0;flex:1;cursor:pointer">'
                                f'<div style="font-weight:700;display:flex;gap:8px;align-items:center">'
                                f'{_dot(m.kolor)}{esc(m.kod)}'
                                f'<span class="ws-st" style="background:#eef2ff;color:#4f46e5">{esc(m.typ)}</span></div>'
                                f'<div class="ws-mut" style="font-size:13px">{esc(m.nazwa)}'
                                f'{" · " + esc(m.lokalizacja) if m.lokalizacja else ""}</div>'
                                f'<div style="font-size:12px;margin-top:2px" data-tip="'
                                f'{"&#10;".join(esc(f"{p.sala or "?"} · {p.nazwa}") for p in ps) or "żadna drukarka nie pasuje"}">'
                                f'🖨 pasuje do: <b>{len(ps)}</b> drukarek'
                                f'{" · " + esc(m.pasuje_do) if m.pasuje_do else ""}</div>'
                                f'<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:3px">{room_tags(ps)}</div>'
                                f'{usage_line(inv, m)}</div>', sanitize=False) \
                                .classes("flex-1 min-w-0").on(
                                    "click", lambda m=m: material_dialog(m, content.refresh) if view["edit"]
                                    else usage_dialog(m))
                            ui.button(icon="remove", on_click=lambda m=m: issue_dialog(m, content.refresh)) \
                                .props("round flat dense color=grey-8").tooltip("Wydaj (zużycie)")
                            ui.html(f'<div style="text-align:center;min-width:64px">'
                                    f'<div style="font-size:24px;font-weight:700;color:{"#b91c1c" if low else "var(--ink)"}">'
                                    f'{m.ilosc}</div><div class="ws-mut" style="font-size:11px">min. {m.minimum}</div></div>',
                                    sanitize=False)
                            ui.button(icon="add", on_click=lambda m=m: receive_dialog(m, content.refresh)) \
                                .props("round flat dense color=primary").tooltip("Przyjmij (dostawa)")

                # ---- do dokupienia
                with card().style("width:360px;flex:none"):
                    ui.label("🛒 Do dokupienia").classes("text-lg font-bold mb-2")
                    if not buy:
                        ui.label("Nic — stany są w porządku 👍").classes("ws-mut")
                    lines = []
                    for b in buy:
                        m = b.material
                        need = suggested_buy(inv, m)
                        lines.append(f"{m.kod} ({m.nazwa}) — {need} szt.")
                        ui.html(f'<div style="padding:8px 0;border-top:1px solid var(--line)">'
                                f'<div style="display:flex;justify-content:space-between;gap:8px">'
                                f'<b>{_dot(m.kolor)}{esc(m.kod)}</b><span style="color:#b91c1c;font-weight:700">'
                                f'kup {need}</span></div>'
                                f'<div class="ws-mut" style="font-size:13px">{esc(b.reason)}'
                                f'{f" · {len(b.printers)} drukarek" if b.printers else ""}</div></div>', sanitize=False)
                    if buy:
                        ui.label(f"„kup N” = tyle, żeby wystarczyło na ~3 miesiące wg dotychczasowego zużycia "
                                 f"(albo do minimum, gdy brak danych). Ostrzeżenie, gdy zapas < {LEAD_DAYS} dni.") \
                            .classes("ws-hint")
                        ui.button("Kopiuj listę zakupów", icon="content_copy",
                                  on_click=lambda: (ui.clipboard.write("\n".join(lines)),
                                                    ui.notify("Skopiowano do schowka"))) \
                            .props("flat no-caps color=primary").classes("mt-2")

            # ---- drukarki wg modelu
            with card():
                with ui.row().classes("w-full items-center"):
                    with ui.column().classes("gap-0"):
                        ui.label("Drukarki wg modelu").classes("text-lg font-bold")
                        ui.label("W trybie edycji ustaw przy modelu, ile wkładów ma drukarka (np. sam czarny "
                                 "albo 4 kolory) — wtedy widać, którego wkładu brakuje na zapleczu."
                                 if view["edit"] else
                                 "Przy każdym modelu: ile drukarek, gdzie stoją i jakie wkłady są na zapleczu.") \
                            .classes("ws-mut text-sm")
                    ui.space()
                    ui.toggle({"todo": f"Do uzupełnienia ({len(todo)})", "all": f"Wszystkie ({len(models)})"},
                              value=view["models"],
                              on_change=lambda e: (view.update(models=e.value), content.refresh())) \
                        .props("no-caps rounded unelevated toggle-color=primary")
                shown = todo if view["models"] == "todo" else models
                if not shown:
                    ui.label("Wszystkie modele mają przypisane tusze 👍").classes("ws-mut mt-2")
                for g in shown:
                    model_row(g, content.refresh, view["edit"])

        content()


# ---------------------------------------------------------------------------
def printers_tip(g) -> str:
    """Dymek na modelu: każda drukarka z salą, nr inw. i statusem."""
    lines = [f"<b>{esc(g.label)}</b> — {len(g.printers)} szt."]
    for p in sorted(g.printers, key=lambda p: sort_key(p.sala) if p.sala else (99,)):
        st = "" if p.status == "OK" else f" · {esc(p.status)}"
        lines.append(f"🖨 <b>{esc(p.sala or '?')}</b> · {esc(p.inv or p.id)}{st}&#10;"
                     f"&#160;&#160;&#160;&#160;{esc(p.nazwa[:60])}")
    return "&#10;".join(lines)


def room_tags(printers: list) -> str:
    """Sale jako małe kolorowe etykiety (kolor budynku), klik -> plan sali; ×N gdy kilka drukarek w sali."""
    counts: dict[str, int] = {}
    for p in printers:
        counts[p.sala or "?"] = counts.get(p.sala or "?", 0) + 1
    out = []
    for room in sorted(counts, key=lambda r: sort_key(r) if r != "?" else (99,)):
        n = counts[room]
        color = BCOL.get(building(room), "#64748b") if room != "?" else "#94a3b8"
        label = room.replace("-ZAPL", " zapl.")
        link = base_room(room) if room != "?" else ""
        tag = (f'<a href="/sala/{esc(link)}" class="ws-tag" style="background:{color}">'
               if link else f'<span class="ws-tag" style="background:{color}">')
        out.append(f'{tag}{esc(label)}{f" ×{n}" if n > 1 else ""}{"</a>" if link else "</span>"}')
    return "".join(out)


def model_row(g, after, edit: bool = False) -> None:
    """Wiersz modelu: ile drukarek, gdzie, jakie wkłady (gniazda) i ich stan."""
    with ui.row().classes("w-full items-center gap-4 no-wrap py-3").style("border-top:1px solid var(--line)"):
        ui.html(f'<div style="min-width:0"><div style="display:flex;gap:8px;align-items:baseline">'
                f'<b style="font-size:16px;cursor:help" data-tip="{printers_tip(g)}">{esc(g.label)}</b>'
                f'<span class="ws-pc" style="font-size:12px" data-tip="{printers_tip(g)}">🖨 × {len(g.printers)}</span>'
                f'</div><div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px">{room_tags(g.printers)}</div>'
                f'</div>', sanitize=False).classes("shrink-0").style("width:260px")

        def set_scheme(e, g=g):
            if e.value:
                S.inv.model_schemes[g.key] = e.value
            else:
                S.inv.model_schemes.pop(g.key, None)
            _save()
            after()

        with ui.column().classes("gap-0 shrink-0").style("width:290px"):
            if edit:
                ui.select(SCHEME_LABELS, value=g.scheme or None, label="Ile wkładów ma ta drukarka?",
                          clearable=True, on_change=set_scheme) \
                    .props("outlined dense options-dense").classes("w-full")
                if g.scheme_guessed and g.scheme:
                    ui.label("odgadnięte z przypisanych wkładów — wybierz, żeby potwierdzić").classes("ws-hint")
            elif g.scheme:
                ui.html(f'<span class="ws-st" style="background:#f1f5f9;color:#334155">{esc(SCHEME_SHORT[g.scheme])}'
                        f'</span>{" <span class=ws-hint>(odgadnięte)</span>" if g.scheme_guessed else ""}',
                        sanitize=False)
            else:
                ui.html('<span class="ws-st" style="background:#fffbeb;color:#b45309">nie ustawiono, ile ma wkładów'
                        '</span>', sanitize=False)

        with ui.row().classes("flex-1 gap-2 items-center"):
            for s in g.slots:
                if s.defined:
                    for m in s.materials:
                        ok = m.ilosc > 0
                        chip = ui.html(
                            f'<span class="ws-chip" style="background:{"#dcfce7" if ok else "#fee2e2"};'
                            f'color:{"#15803d" if ok else "#b91c1c"};{"cursor:pointer" if edit else ""}" '
                            f'data-tip="{esc(m.nazwa or m.kod)}&#10;{esc(s.color)} · na stanie {m.ilosc}">'
                            f'{_dot(s.color)}{esc(m.kod)}<small>{m.ilosc} szt.</small></span>', sanitize=False)
                        if edit:
                            chip.on("click", lambda m=m: material_dialog(m, after))
                elif edit:
                    ui.html(f'<span class="ws-chip" style="background:#fff;border:1.5px dashed #f87171;color:#b91c1c;'
                            f'cursor:pointer" data-tip="Nie ma jeszcze wkładu: {esc(s.color)}&#10;kliknij, żeby dodać">'
                            f'{_dot(s.color)}＋ {esc(s.color)}</span>', sanitize=False) \
                        .on("click", lambda c=s.color, g=g: material_dialog(
                            None, after, template=Material(kod="", pasuje_do=guess_model(g.printers[0].nazwa) or g.model,
                                                           kolor=c, typ="toner")))
                else:
                    ui.html(f'<span class="ws-chip" style="background:#fff;border:1.5px dashed #f87171;color:#b91c1c">'
                            f'{_dot(s.color)}brak: {esc(s.color)}</span>', sanitize=False)
        if edit:
            ui.button(icon="link", on_click=lambda g=g: assign_dialog(g, after)) \
                .props("flat round dense color=primary").tooltip("Przypisz wkład, który już jest na liście")


def material_dialog(m: Material | None, after, template: Material | None = None) -> None:
    new = m is None
    m = m or template or Material(kod="")
    with ui.dialog() as dlg, ui.card().classes("w-[600px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.label("Nowy wkład" if new else f"Wkład {m.kod}").classes("text-xl font-bold")
        with ui.grid(columns=2).classes("w-full gap-3"):
            kod = ui.input("Kod (np. CF280X, TN-2420)", value=m.kod).props("outlined dense")
            if not new:
                kod.props("readonly")
            nazwa = ui.input("Nazwa", value=m.nazwa).props("outlined dense")
            typ = ui.select(MATERIAL_TYPES, value=m.typ, label="Typ").props("outlined dense")
            kolor = ui.select(COLORS, value=m.kolor, label="Kolor").props("outlined dense")
            ilosc = ui.number("Ilość na stanie", value=m.ilosc, min=0, precision=0).props("outlined dense")
            minimum = ui.number("Minimum (poniżej = kupić)", value=m.minimum, min=0, precision=0) \
                .props("outlined dense")
        pas = ui.input("Pasuje do (modele, po przecinku)", value=m.pasuje_do,
                       placeholder="np. M401, M425").props("outlined dense").classes("w-full")
        ui.label("Wystarczy fragment nazwy modelu z „Drukarki wg modelu”, np. M401 albo DCP-L5500.") \
            .classes("ws-hint")
        lok = ui.input("Gdzie leży", value=m.lokalizacja, placeholder="np. 16 – szafa").props("outlined dense") \
            .classes("w-full")
        uw = ui.input("Uwagi", value=m.uwagi).props("outlined dense").classes("w-full")

        def save():
            k = (kod.value or "").strip()
            if not k:
                ui.notify("Podaj kod materiału")
                return
            if new and k in S.inv.materials:
                ui.notify("Taki kod już istnieje")
                return
            m.kod, m.nazwa, m.typ, m.kolor = k, (nazwa.value or "").strip(), typ.value, kolor.value or ""
            m.pasuje_do, m.lokalizacja, m.uwagi = (pas.value or "").strip(), (lok.value or "").strip(), (uw.value or "").strip()
            old_qty = S.inv.materials[k].ilosc if k in S.inv.materials and not new else None
            m.ilosc, m.minimum = int(ilosc.value or 0), int(minimum.value or 0)
            S.inv.materials[k] = m
            if new:
                S.inv.log(f"zaplecze:{k}", "nowy materiał", "", str(m.ilosc), m.nazwa)
            elif old_qty is not None and old_qty != m.ilosc:
                S.inv.log(f"zaplecze:{k}", "korekta stanu", str(old_qty), str(m.ilosc))
            _save("Zapisano")
            dlg.close()
            after()

        def delete():
            S.inv.materials.pop(m.kod, None)
            S.inv.log(f"zaplecze:{m.kod}", "usunięty materiał")
            _save("Usunięto")
            dlg.close()
            after()

        with ui.row().classes("w-full items-center gap-2"):
            if not new:
                ui.button("Usuń", icon="delete", on_click=lambda: confirm(f"Usunąć {m.kod} z zaplecza?", delete)) \
                    .props("flat no-caps color=negative")
            ui.space()
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Zapisz", icon="save", on_click=save).props("unelevated no-caps color=primary")
    dlg.open()


def confirm(text: str, action) -> None:
    with ui.dialog() as d, ui.card().classes("rounded-2xl p-6"):
        ui.label(text).classes("text-lg font-semibold")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Nie", on_click=d.close).props("flat no-caps")
            ui.button("Tak", on_click=lambda: (d.close(), action())).props("unelevated no-caps color=negative")
    d.open()


def issue_dialog(m: Material, after) -> None:
    rooms = sorted({p.sala for p in printers_for(S.inv, m) if p.sala})
    with ui.dialog() as dlg, ui.card().classes("w-[440px] rounded-2xl p-6 gap-3"):
        ui.label(f"Wymiana / wydanie {m.kod}").classes("text-xl font-bold")
        ui.label(f"Na stanie: {m.ilosc}").classes("ws-mut")
        with ui.row().classes("w-full gap-3 no-wrap"):
            n = ui.number("Ile sztuk", value=1, min=1, precision=0).props("outlined dense").classes("w-28")
            day = ui.input("Kiedy", value=date.today().isoformat()).props("outlined dense type=date") \
                .classes("flex-1")
        sala = ui.select(rooms, label="Do drukarki w sali (opcjonalnie)", with_input=True,
                         new_value_mode="add-unique", clearable=True).props("outlined dense")
        opis = ui.input("Notatka", placeholder="np. wymiana w drukarce nauczycielskiej").props("outlined dense")
        only_log = ui.checkbox("Tylko wpis do historii — nie zdejmuj ze stanu "
                               "(gdy uzupełniasz dawne wymiany)")

        def on_day(e):
            try:
                only_log.value = date.fromisoformat(e.value) < date.today().replace(day=1) if e.value else False
            except ValueError:
                pass
        day.on_value_change(on_day)

        def go():
            try:
                when = datetime.combine(date.fromisoformat(day.value), datetime.now().time()) if day.value else None
            except ValueError:
                ui.notify("Niepoprawna data")
                return
            k = int(n.value or 1)
            stock_change(S.inv, m.kod, -k, sala.value or "", (opis.value or "").strip(),
                         when=when, change_stock=not only_log.value)
            _save(f"Zapisano wymianę {k} × {m.kod}" + (" (bez zmiany stanu)" if only_log.value else ""))
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Wydaj", icon="remove", on_click=go).props("unelevated no-caps color=primary")
    dlg.open()


def usage_dialog(m: Material) -> None:
    """Podgląd zużycia: średnia, prognoza, wymiany wg sal, lista wymian."""
    u = usage(S.inv, m.kod)
    with ui.dialog() as dlg, ui.card().classes("w-[620px] max-w-[95vw] rounded-2xl p-6 gap-3"):
        ui.html(f'<div style="font-size:19px;font-weight:700">{_dot(m.kolor)}{esc(m.kod)}</div>'
                f'<div class="ws-mut">{esc(m.nazwa)} · na stanie <b>{m.ilosc}</b></div>', sanitize=False)
        if not u.replacements:
            ui.label("Brak zapisanych wymian. Każde „−” (wydanie) zapisuje datę — po kilku wymianach "
                     "program policzy średnie zużycie i na ile wystarczy zapas. Dawne wymiany możesz "
                     "dopisać z datą wsteczną.").classes("ws-mut")
        else:
            tiles = []
            if u.per_month is not None:
                tiles.append((f"{u.per_month:.1f}".replace(".", ","), "szt. na miesiąc (średnio)"))
            if u.days_left is not None:
                tiles.append((_months(u.days_left), f"zapas wystarczy do ~{u.runout:%d.%m.%Y}"))
            tiles.append((str(len(u.replacements)), "wymian zapisanych"))
            ui.html('<div style="display:flex;gap:10px;flex-wrap:wrap">' + "".join(
                f'<div style="background:#f1f3f9;border-radius:12px;padding:10px 14px">'
                f'<div style="font-size:22px;font-weight:700">{v}</div>'
                f'<div class="ws-mut" style="font-size:12px">{t}</div></div>' for v, t in tiles) + "</div>",
                sanitize=False)
            if u.few_data:
                ui.label("Mało danych (mniej niż 3 wymiany w ostatnim roku) — prognoza orientacyjna.") \
                    .classes("ws-hint")
            ui.label(f"Średnia liczona z wymian z ostatnich {USAGE_WINDOW_DAYS} dni.").classes("ws-hint")
            if u.by_room:
                ui.label("Co ile dni wymiana w sali").classes("font-semibold mt-2")
                ui.html("".join(f'<div style="display:flex;justify-content:space-between;padding:2px 0">'
                                f'<span>{esc(s)}</span><b>co ~{int(d)} dni</b></div>'
                                for s, d in sorted(u.by_room.items(), key=lambda kv: kv[1])), sanitize=False) \
                    .classes("w-full")
            ui.label("Wymiany").classes("font-semibold mt-2")
            ui.html("".join(f'<div style="display:flex;gap:14px;padding:3px 0;border-top:1px solid var(--line)">'
                            f'<span class="ws-mut" style="width:90px">{r.when:%d.%m.%Y}</span>'
                            f'<span style="width:50px">{r.count} szt.</span><span>{esc(r.sala) or "—"}</span></div>'
                            for r in reversed(u.replacements)), sanitize=False).classes("w-full max-h-64 overflow-auto")
        ui.button("Zamknij", on_click=dlg.close).props("flat no-caps").classes("self-end")
    dlg.open()


def receive_dialog(m: Material, after) -> None:
    with ui.dialog() as dlg, ui.card().classes("w-[400px] rounded-2xl p-6 gap-3"):
        ui.label(f"Przyjmij {m.kod}").classes("text-xl font-bold")
        n = ui.number("Ile sztuk przyszło", value=1, min=1, precision=0).props("outlined dense")
        opis = ui.input("Notatka", placeholder="np. faktura, dostawca").props("outlined dense")

        def go():
            stock_change(S.inv, m.kod, int(n.value or 1), "", (opis.value or "").strip())
            _save(f"Przyjęto {int(n.value or 1)} × {m.kod}")
            dlg.close()
            after()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Anuluj", on_click=dlg.close).props("flat no-caps")
            ui.button("Przyjmij", icon="add", on_click=go).props("unelevated no-caps color=primary")
    dlg.open()


def assign_dialog(g, after) -> None:
    """Przypisanie materiału do modelu drukarki: dopisuje model do pola „Pasuje do”."""
    model = guess_model(g.printers[0].nazwa) or g.model
    with ui.dialog() as dlg, ui.card().classes("w-[520px] rounded-2xl p-6 gap-3"):
        ui.label(f"Wkład dla {g.label}").classes("text-xl font-bold")
        ui.label(f"{len(g.printers)} szt. w salach: {', '.join(g.rooms)}").classes("ws-mut")
        key = ui.input("Słowo kluczowe modelu", value=model).props("outlined dense").classes("w-full")
        existing = {m.kod: f"{m.kod} — {m.nazwa}" for m in S.inv.materials.values()}
        pick = ui.select(existing, label="Wkład z listy", with_input=True, clearable=True) \
            .props("outlined dense").classes("w-full")

        def link():
            if not pick.value:
                ui.notify("Wybierz materiał albo utwórz nowy")
                return
            m = S.inv.materials[pick.value]
            kw = (key.value or "").strip()
            if kw and kw.lower() not in m.keywords:
                m.pasuje_do = ", ".join([*(k for k in [m.pasuje_do] if k), kw])
            _save(f"{m.kod} pasuje teraz do {kw}")
            dlg.close()
            after()

        def create():
            dlg.close()
            material_dialog_prefill((key.value or "").strip(), after)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Nowy wkład…", icon="add", on_click=create).props("flat no-caps color=primary")
            ui.button("Przypisz", icon="link", on_click=link).props("unelevated no-caps color=primary")
    dlg.open()


def material_dialog_prefill(keyword: str, after) -> None:
    """Nowy materiał z wypełnionym polem „Pasuje do”."""
    material_dialog(None, after, template=Material(kod="", pasuje_do=keyword))
