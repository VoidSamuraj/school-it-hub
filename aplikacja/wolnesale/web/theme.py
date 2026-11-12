"""Wygląd: kolory, CSS, wspólne elementy (nagłówek ekranu, karty, etykiety sal)."""
from __future__ import annotations

import html

from nicegui import ui

from ..core.sale import BURSA, GIMNASTYCZNA, GLOWNY, INNE, WARSZTAT, building

ACCENT = "#4f46e5"
BCOL = {GLOWNY: "#4f46e5", WARSZTAT: "#ea580c", BURSA: "#0d9488", GIMNASTYCZNA: "#db2777", INNE: "#64748b"}
BSHORT = {GLOWNY: "Główny", WARSZTAT: "Warsztat", BURSA: "Bursa", GIMNASTYCZNA: "Sala gim.", INNE: "Inne"}

CSS = r"""
:root{--bg:#f4f6fb;--card:#fff;--ink:#1e2433;--mut:#6b7280;--line:#e7eaf2;--acc:#4f46e5;--acc2:#eef2ff;
      --free:#15803d;--freebg:#dcfce7;--busy:#fde2e1;--busy2:#fbcfcd}
body{background:var(--bg);color:var(--ink);font-family:Inter,'Segoe UI',sans-serif;font-size:15px}
.nicegui-content{padding:0}
/* menu boczne */
.ws-nav{background:#141a2e!important;color:#c9cfe3}
.ws-logo{font-weight:700;font-size:19px;color:#fff;display:flex;gap:10px;align-items:center;margin:4px 8px 18px}
.ws-logo span{background:linear-gradient(135deg,#6366f1,#22d3ee);border-radius:10px;width:34px;height:34px;display:grid;place-items:center}
.ws-nav .q-btn.ws-navbtn{width:100%;justify-content:flex-start;border-radius:10px;padding:9px 14px;color:#c9cfe3!important;font-weight:500;text-transform:none;font-size:15px}
.ws-nav .ws-navbtn .q-btn__content{justify-content:flex-start;gap:12px;flex-wrap:nowrap;width:100%}
.ws-nav .ws-navbtn:hover{background:#222a44}
.ws-nav .q-btn.ws-navbtn.on{background:#2a3352!important;color:#fff!important}
.ws-navbtn.soon{opacity:.45}
.ws-sec{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#6c7593;margin:16px 14px 4px}
.ws-soon{margin-left:auto;font-size:10px;background:#2a3352;border-radius:99px;padding:1px 7px;color:#9aa3c2}
/* strona */
.ws-page{padding:26px 34px;width:100%;gap:18px}
.ws-h1{font-size:26px;font-weight:700;margin:0}
.ws-pill{background:var(--acc2);color:var(--acc);border-radius:99px;padding:5px 12px;font-size:13px;font-weight:600}
.ws-card{background:var(--card);border-radius:18px;box-shadow:0 1px 3px #0000000d,0 8px 24px #1e24330a;padding:20px 22px;width:100%}
.ws-flabel{display:block;font-size:12px;font-weight:600;color:var(--mut);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
.ws-mut{color:var(--mut)}
.q-btn{text-transform:none;font-weight:600;border-radius:12px}
.ws-seg{background:#f1f3f9;border-radius:12px;padding:4px;gap:4px}
.ws-seg .q-btn{border-radius:9px;color:var(--mut);padding:4px 13px;min-height:34px}
.ws-seg .q-btn.on{background:#fff!important;color:var(--acc)!important;box-shadow:0 1px 3px #0002}
.ws-seg .q-btn.disabled{opacity:.4!important}
/* filtry: wszystkie grupy od góry, kontrolki tej samej wysokości (42px) */
.ws-filters>.q-column,.ws-filters>.nicegui-column{justify-content:flex-start}
.ws-filters .ws-seg,.ws-filters .ws-range{min-height:42px;align-items:center}
.ws-filters .ws-flabel{line-height:16px;height:16px}
.ws-chipbtn{border:1px solid var(--line);border-radius:99px!important;background:#fff;color:var(--ink)!important;font-weight:500;padding:3px 13px;min-height:34px}
.ws-chipbtn.on{border-color:var(--acc);background:var(--acc2)!important;color:var(--acc)!important}
.ws-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px}
/* etykiety sal i okienka */
.ws-badge{color:#fff;font-weight:700;border-radius:10px;padding:6px 0;width:62px;text-align:center;font-size:15px;display:inline-block;text-decoration:none}
.ws-chip{display:inline-flex;gap:6px;align-items:baseline;white-space:nowrap;background:var(--freebg);color:var(--free);border-radius:9px;padding:5px 10px;margin:3px 5px 3px 0;font-weight:700;font-size:14px}
.ws-chip small{font-weight:500;font-size:11.5px;color:#16a34a}
.ws-none{color:#c3c8d4}
.ws-bar{height:6px;background:#eef0f6;border-radius:9px;margin-top:6px}
.ws-bar i{display:block;height:100%;border-radius:9px;background:linear-gradient(90deg,#22c55e,#16a34a)}
/* tabela wolnych sal */
.ws-fgrid .ws-head,.ws-fgrid .ws-row{display:grid;gap:10px;align-items:center}
.ws-fgrid .ws-head{font-size:12px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;padding:0 12px 10px}
.ws-fgrid .ws-row{padding:10px 12px;border-radius:14px;cursor:pointer;color:inherit;text-decoration:none}
.ws-fgrid .ws-row:hover{background:#f5f6fd}
.ws-fgrid .ws-row+.ws-row{border-top:1px solid var(--line)}
/* siatka tygodnia */
.ws-week{overflow:auto;max-height:calc(100vh - 210px)}
.ws-week table{border-collapse:separate;border-spacing:0}
.ws-week th{position:sticky;top:0;background:#fff;z-index:2;font-size:12px;color:var(--mut);font-weight:600;padding:2px 0}
.ws-week th.day{font-size:13px;color:var(--ink);font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.ws-week td{padding:2px}
.ws-week td.gap,.ws-week th.gap{width:18px;min-width:18px}
.ws-week td.room{position:sticky;left:0;background:#fff;z-index:1;padding-right:10px;white-space:nowrap}
.ws-week td.free{color:var(--mut);font-size:12px;padding-left:12px;white-space:nowrap}
.ws-c{width:24px;height:24px;border-radius:6px;display:block}
.ws-c.f{background:var(--freebg)} .ws-c.b{background:var(--busy2)}
.ws-c:hover{outline:2px solid var(--acc);outline-offset:1px}
/* plan dnia / sali */
.ws-tt{display:grid;gap:6px}
.ws-tt .h{font-size:12px;font-weight:700;color:var(--mut);text-align:center;text-transform:uppercase;letter-spacing:.05em}
.ws-tt .h small{display:block;font-weight:500;text-transform:none;letter-spacing:0}
.ws-tt .r{font-weight:700;display:flex;align-items:center}
.ws-tt .cell{border-radius:10px;padding:6px 8px;font-size:13px;line-height:1.3;min-height:44px}
.ws-tt .cell.f{background:var(--freebg);color:var(--free);font-weight:600;display:grid;place-items:center}
.ws-tt .cell.b{background:var(--busy)}
.ws-tt .cell.b b{display:block}
.ws-tt .cell .t{color:var(--mut);font-size:12px}
/* dymek */
#ws-tip{position:fixed;z-index:9999;pointer-events:none;background:#141a2e;color:#fff;border-radius:12px;padding:10px 13px;
        font-size:13px;line-height:1.45;white-space:pre-line;max-width:360px;box-shadow:0 10px 30px #0004;display:none}
#ws-tip b{color:#a5b4fc}
/* sprzęt */
.ws-tree .q-tree__node-header{border-radius:9px}
.ws-st{border-radius:99px;padding:2px 9px;font-size:12px;font-weight:600;display:inline-block}
/* odznaka komputerów */
.ws-pc{border-radius:99px;padding:2px 9px;font-size:12px;font-weight:600;display:inline-flex;gap:4px;align-items:center;
       background:#f1f5f9;color:#475569;white-space:nowrap}
.ws-pc.it{background:#dbeafe;color:#1d4ed8}
.ws-hint{font-size:12px;color:var(--mut);margin-top:4px}
/* mój plan */
.ws-tt .cell.off,.ws-c.off{background-image:repeating-linear-gradient(45deg,transparent 0 5px,#0000000d 5px 10px)}
.ws-tt .cell.off{background-color:#f8fafc}
.ws-plus{color:#cbd5e1;font-size:18px;display:grid;place-items:center;height:100%;opacity:0}
.ws-tt .cell:hover .ws-plus{opacity:1}
.ws-entry{background:#e0e7ff;border-left:4px solid var(--acc);border-radius:8px;padding:4px 7px;margin:1px 0;font-size:12.5px}
.ws-entry.cont{background:#eef2ff;border-left-style:dashed}
.ws-entry.clash{background:#fee2e2;border-left-color:#dc2626}
.ws-chip[data-fill]{cursor:pointer}
.ws-tag{color:#fff;font-weight:700;font-size:11.5px;border-radius:6px;padding:1px 7px;text-decoration:none;
        white-space:nowrap;line-height:18px}
a.ws-tag:hover{filter:brightness(1.15);box-shadow:0 0 0 2px #fff,0 0 0 3px currentColor}
.ws-chip.night{background:#ede9fe;color:#6d28d9}
.ws-chip.night small{color:#7c3aed}
"""

TOOLTIP_JS = r"""
<div id="ws-tip"></div>
<script>
document.addEventListener('mouseover', e => {
  const el = e.target.closest('[data-tip]'); const tip = document.getElementById('ws-tip');
  if (!el) { tip.style.display = 'none'; return; }
  tip.innerHTML = el.getAttribute('data-tip'); tip.style.display = 'block';
});
document.addEventListener('mousemove', e => {
  const tip = document.getElementById('ws-tip'); if (tip.style.display !== 'block') return;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 16, y = e.clientY + 16;
  if (x + w > window.innerWidth - 8) x = e.clientX - w - 16;
  if (y + h > window.innerHeight - 8) y = e.clientY - h - 16;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
});
</script>
"""


def set_on(btn, on: bool) -> None:
    """Stan przycisku-przełącznika (segment / chip): klasa + kolor tekstu Quasara."""
    if on:
        btn.classes(add="on").props("color=primary")
    else:
        btn.classes(remove="on").props("color=grey-8")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def badge(room: str, link: bool = True) -> str:
    color = BCOL.get(building(room), "#64748b")
    tag = f'<a href="/sala/{esc(room)}"' if link else "<span"
    end = "</a>" if link else "</span>"
    return f'{tag} class="ws-badge" style="background:{color}">{esc(room)}{end}'


def _pl(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


PC_NAMES = {"Komputer": ("komputer", "komputery", "komputerów"),
            "Laptop": ("laptop", "laptopy", "laptopów"),
            "Chromebook": ("chromebook", "chromebooki", "chromebooków")}


def pc_badge(inv, room: str, detailed: bool = False) -> str:
    """Odznaka komputerów.

    W widokach ogólnych suma: '💻 16 PC'. W szczegółowych rozbicie: '💻 16 laptopów · 1 komputer'.
    Po najechaniu zawsze widać rozbicie na rodzaje.
    """
    if not inv or not inv.items:
        return ""
    kind, br = inv.room_kind(room), inv.pc_breakdown(room)
    n = sum(br.values())
    if not kind and not n:
        return ""
    parts = [f"{c} {_pl(c, *PC_NAMES[k])}" for k, c in br.most_common()]
    tip = "&#10;".join(parts) or "brak w spisie"
    head = "Sala komputerowa" if kind == "it" else "Komputer w sali"
    text = " · ".join(parts) if detailed else f"{n} PC"
    cls = "ws-pc it" if kind == "it" else "ws-pc"
    icon = "💻" if kind == "it" else "🖥"
    return f'<span class="{cls}" data-tip="<b>{head}</b>&#10;{tip}">{icon} {text}</span>'


def page_header(title: str, pill: str | None = None):
    """Wiersz nagłówka; zwraca kontener na przyciski po prawej."""
    with ui.row().classes("w-full items-center gap-3"):
        ui.html(f'<h1 class="ws-h1">{esc(title)}</h1>', sanitize=False)
        if pill:
            ui.html(f'<span class="ws-pill">{esc(pill)}</span>', sanitize=False)
        ui.space()
        actions = ui.row().classes("items-center gap-2")
    return actions


def card():
    return ui.element("div").classes("ws-card")


def empty_plan_notice():
    with card():
        ui.label("Brak wczytanego planu").classes("text-xl font-bold")
        ui.label("Wydrukuj w aSc plany nauczycieli do PDF i wczytaj go przyciskiem "
                 "„Wczytaj plan (PDF)” w menu po lewej.").classes("ws-mut")
