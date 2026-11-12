"""Zakładka Sprzęt: drzewko lokalizacji, tabela, edycja, przenoszenie, import ewidencji."""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSplitter, QTableWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..core.ewidencja import import_files, merge
from ..core.sale import BUILDINGS, building, sort_key
from ..core.sprzet import (NIEPEWNA, NIEZNANA, PEWNOSCI, SERWIS, STATUSY, WYCOFANY, WYPOZYCZONY,
                           Inventory, InventoryLockedError, Item)
from .common import item

C_UNSURE = QColor("#fff3bf")
C_UNKNOWN = QColor("#ffd8a8")
C_SERVICE = QColor("#d0ebff")
C_LOANED = QColor("#e5dbff")
C_RETIRED = QColor("#e9ecef")

COLS = ["ID", "Kategoria", "Nazwa", "Sala", "Pewność", "Status", "Użytkownik", "Sprawdzono",
        "Wg ewidencji", "Uwagi", "Projekt"]
ALL = "— wszystkie —"


def row_color(it: Item) -> QColor | None:
    if it.status == SERWIS:
        return C_SERVICE
    if it.status == WYPOZYCZONY:
        return C_LOANED
    if it.status == WYCOFANY:
        return C_RETIRED
    if it.pewnosc == NIEZNANA or not it.sala:
        return C_UNKNOWN
    if it.pewnosc == NIEPEWNA:
        return C_UNSURE
    return None


class EditDialog(QDialog):
    def __init__(self, inv: Inventory, it: Item, locations: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sprzęt {it.id}")
        self.resize(560, 600)
        info = QLabel(
            f"<b>{it.nazwa}</b><br>{it.kategoria} · nr inw. {it.inv} · projekt {it.projekt}<br>"
            f"przyjęty {it.data or '?'} · wartość {f'{it.wartosc:.2f} zł' if it.wartosc else '?'}<br>"
            f"<span style='color:#555'>Ewidencja: sala <b>{it.sala_ewid or '?'}</b> — „{it.opis_ewid}”"
            f"{'' if it.w_ewidencji == 'tak' else ' · <b>brak w ostatnim zestawieniu!</b>'}</span>")
        info.setWordWrap(True)
        self.sala = QComboBox()
        self.sala.setEditable(True)
        self.sala.addItems(locations)
        self.sala.setCurrentText(it.sala)
        self.pewnosc = QComboBox()
        self.pewnosc.addItems(PEWNOSCI)
        self.pewnosc.setCurrentText(it.pewnosc)
        self.status = QComboBox()
        self.status.addItems(STATUSY)
        self.status.setCurrentText(it.status)
        self.user = QLineEdit(it.uzytkownik)
        self.user.setPlaceholderText("kto używa / komu wypożyczony")
        self.checked = QLineEdit(it.sprawdzono)
        today = QPushButton("dziś")
        today.clicked.connect(lambda: self.checked.setText(date.today().isoformat()))
        chk = QHBoxLayout()
        chk.addWidget(self.checked)
        chk.addWidget(today)
        self.notes = QPlainTextEdit(it.uwagi)
        self.notes.setMaximumHeight(80)
        hist = QPlainTextEdit("\n".join(
            f"{e.data}  {e.zdarzenie}  {e.z} → {e.do}  {e.opis}".rstrip() for e in inv.item_history(it.id))
            or "brak zmian")
        hist.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Sala (faktycznie):", self.sala)
        form.addRow("Pewność lokalizacji:", self.pewnosc)
        form.addRow("Status:", self.status)
        form.addRow("Użytkownik:", self.user)
        form.addRow("Sprawdzono:", chk)
        form.addRow("Uwagi:", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Zapisz")
        buttons.button(QDialogButtonBox.Cancel).setText("Anuluj")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(form)
        lay.addWidget(QLabel("Historia:"))
        lay.addWidget(hist, 1)
        lay.addWidget(buttons)

    def changes(self) -> dict:
        return dict(sala=self.sala.currentText().strip(), pewnosc=self.pewnosc.currentText(),
                    status=self.status.currentText(), uzytkownik=self.user.text().strip(),
                    sprawdzono=self.checked.text().strip(), uwagi=self.notes.toPlainText().strip())


class ReportDialog(QDialog):
    def __init__(self, title: str, html: str, text: str, ok_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 600)
        head = QLabel(html)
        head.setWordWrap(True)
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        buttons = QDialogButtonBox()
        buttons.addButton(ok_label, QDialogButtonBox.AcceptRole)
        buttons.addButton("Anuluj", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(box, 1)
        lay.addWidget(buttons)


class SprzetView(QWidget):
    changed = Signal()

    def __init__(self, inventory_path: Path, backup_dir: Path, parent=None):
        super().__init__(parent)
        self.inv_path = inventory_path
        self.backup_dir = backup_dir
        self.inv = Inventory(inventory_path)
        self.plan_rooms: list[str] = []
        self._sel: tuple = ("all",)

        # --- pasek filtrów
        self.import_btn = QPushButton("📥 Importuj ewidencję…")
        self.import_btn.clicked.connect(self.import_ewidencja)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Szukaj: nazwa, nr inw., użytkownik, uwagi…")
        self.search.setClearButtonEnabled(True)
        self.cat = QComboBox()
        self.status = QComboBox()
        self.proj = QComboBox()
        self.only_unsure = QCheckBox("tylko do sprawdzenia")
        self.only_moved = QCheckBox("tylko przeniesione (≠ ewidencja)")
        for w in (self.cat, self.status, self.proj):
            w.currentIndexChanged.connect(self.fill_table)
        self.search.textChanged.connect(self.fill_table)
        self.only_unsure.toggled.connect(self.fill_table)
        self.only_moved.toggled.connect(self.fill_table)
        bar = QHBoxLayout()
        bar.addWidget(self.import_btn)
        bar.addWidget(self.search, 1)
        for lab, w in (("Kategoria:", self.cat), ("Status:", self.status), ("Projekt:", self.proj)):
            bar.addWidget(QLabel(lab))
            bar.addWidget(w)
        bar.addWidget(self.only_unsure)
        bar.addWidget(self.only_moved)

        # --- drzewko + tabela
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Lokalizacja", "Szt."])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.edit_row(r))
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.count = QLabel()

        self.edit_btn = QPushButton("✏ Edytuj")
        self.move_btn = QPushButton("➡ Przenieś zaznaczone…")
        self.check_btn = QPushButton("✔ Sprawdzone dziś")
        self.edit_btn.clicked.connect(lambda: self.edit_row(self.table.currentRow()))
        self.move_btn.clicked.connect(self.move_selected)
        self.check_btn.clicked.connect(self.mark_checked)
        legend = QLabel(
            f"<span style='background:{C_UNSURE.name()}'>&nbsp;niepewna&nbsp;</span> "
            f"<span style='background:{C_UNKNOWN.name()}'>&nbsp;nieznana&nbsp;</span> "
            f"<span style='background:{C_SERVICE.name()}'>&nbsp;serwis&nbsp;</span> "
            f"<span style='background:{C_LOANED.name()}'>&nbsp;wypożyczony&nbsp;</span>")
        actions = QHBoxLayout()
        for b in (self.edit_btn, self.move_btn, self.check_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(legend)
        actions.addSpacing(12)
        actions.addWidget(self.count)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.table, 1)
        rl.addLayout(actions)
        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(right)
        split.setSizes([260, 1100])
        lay = QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        self._update_buttons()

    # ------------------------------------------------------------------
    def load(self) -> str | None:
        try:
            self.inv = Inventory.load(self.inv_path)
        except Exception as e:  # noqa: BLE001
            self.inv = Inventory(self.inv_path)
            return f"Nie udało się wczytać {self.inv_path.name}: {e}"
        self.refresh()
        return None

    def set_plan_rooms(self, rooms: list[str]) -> None:
        self.plan_rooms = list(rooms)

    def locations(self) -> list[str]:
        return sorted(set(self.inv.locations()) | set(self.plan_rooms), key=sort_key)

    def save(self) -> bool:
        try:
            self.inv.save(backup_dir=self.backup_dir)
            return True
        except InventoryLockedError as e:
            QMessageBox.warning(self, "Nie zapisano", str(e) + "\n\nZmiany są w programie — "
                                "zapiszą się przy następnej zmianie po zamknięciu Excela.")
            return False

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        items = list(self.inv.items.values())
        for combo, values in ((self.cat, {i.kategoria for i in items}),
                              (self.status, {i.status for i in items}),
                              (self.proj, {i.projekt for i in items})):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([ALL] + sorted(v for v in values if v))
            combo.setCurrentIndex(max(combo.findText(cur), 0))
            combo.blockSignals(False)
        self._fill_tree()
        self.fill_table()
        self.changed.emit()

    def _fill_tree(self) -> None:
        items = list(self.inv.items.values())
        self.tree.blockSignals(True)
        self.tree.clear()

        def node(parent, text, n, key):
            w = QTreeWidgetItem(parent, [text, str(n)])
            w.setData(0, Qt.UserRole, key)
            w.setTextAlignment(1, Qt.AlignRight)
            return w

        root = node(self.tree, "📦 Wszystko", len(items), ("all",))
        unsure = [i for i in items if i.pewnosc != "pewna" or not i.sala]
        node(self.tree, "❓ Do sprawdzenia", len(unsure), ("unsure",))
        by_loc: dict[str, int] = {}
        for i in items:
            by_loc[i.sala] = by_loc.get(i.sala, 0) + 1
        for b in BUILDINGS:
            locs = [l for l in by_loc if l and building(l) == b]
            if not locs:
                continue
            bn = node(self.tree, b, sum(by_loc[l] for l in locs), ("building", b))
            for l in sorted(locs, key=sort_key):
                label = l.replace("-ZAPL", " · zaplecze") if l.endswith("-ZAPL") else l
                node(bn, label, by_loc[l], ("loc", l))
        if by_loc.get(""):
            node(self.tree, "⚠ Bez lokalizacji", by_loc[""], ("loc", ""))
        # przywróć zaznaczenie
        target = None
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            w = stack.pop()
            if w.data(0, Qt.UserRole) == self._sel:
                target = w
            stack.extend(w.child(k) for k in range(w.childCount()))
        (target or root).setSelected(True)
        if target and target.parent():
            target.parent().setExpanded(True)
        self.tree.blockSignals(False)

    def _tree_selected(self) -> None:
        sel = self.tree.selectedItems()
        self._sel = sel[0].data(0, Qt.UserRole) if sel else ("all",)
        self.fill_table()

    def select_location(self, room: str) -> None:
        """Pokaż sprzęt danej sali (z widoku Sala)."""
        self._sel = ("loc", room)
        self.search.clear()
        self._fill_tree()
        self.fill_table()

    def _visible(self) -> list[Item]:
        key = self._sel
        q = self.search.text().strip().lower()
        out = []
        for i in self.inv.items.values():
            if key[0] == "unsure" and not (i.pewnosc != "pewna" or not i.sala):
                continue
            if key[0] == "building" and (not i.sala or building(i.sala) != key[1]):
                continue
            if key[0] == "loc" and i.sala != key[1]:
                continue
            if self.cat.currentText() not in (ALL, "") and i.kategoria != self.cat.currentText():
                continue
            if self.status.currentText() not in (ALL, "") and i.status != self.status.currentText():
                continue
            if self.proj.currentText() not in (ALL, "") and i.projekt != self.proj.currentText():
                continue
            if self.only_unsure.isChecked() and i.pewnosc == "pewna" and i.sala:
                continue
            if self.only_moved.isChecked() and not i.moved:
                continue
            if q and q not in " ".join([i.id, i.nazwa, i.uzytkownik, i.uwagi, i.opis_ewid, i.sala,
                                         i.kategoria]).lower():
                continue
            out.append(i)
        out.sort(key=lambda i: (sort_key(i.sala) if i.sala else (99,), i.kategoria, i.id))
        return out

    def fill_table(self) -> None:
        t = self.table
        t.setSortingEnabled(False)
        rows = self._visible()
        t.setRowCount(len(rows))
        for r, i in enumerate(rows):
            color = row_color(i)
            ewid = i.sala_ewid + (" ⇄" if i.moved else "")
            vals = [i.id, i.kategoria, i.nazwa, i.sala or "?", i.pewnosc, i.status, i.uzytkownik,
                    i.sprawdzono, ewid, i.uwagi, i.projekt]
            for c, v in enumerate(vals):
                cell = item(str(v), color, align=Qt.AlignLeft | Qt.AlignVCenter)
                if c == 0:
                    cell.setData(Qt.UserRole, i.id)
                if c == 8:
                    cell.setToolTip(f"Ewidencja: „{i.opis_ewid}”")
                t.setItem(r, c, cell)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
        t.setColumnWidth(2, min(t.columnWidth(2), 320))
        t.setColumnWidth(9, min(t.columnWidth(9), 220))
        t.horizontalHeader().setStretchLastSection(True)
        self.count.setText(f"{len(rows)} szt.")
        self._update_buttons()

    def _selected_ids(self) -> list[str]:
        rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def _update_buttons(self) -> None:
        n = len(self._selected_ids())
        self.edit_btn.setEnabled(n == 1)
        self.move_btn.setEnabled(n >= 1)
        self.check_btn.setEnabled(n >= 1)

    # --- akcje ------------------------------------------------------------
    def edit_row(self, row: int) -> None:
        if row < 0:
            return
        iid = self.table.item(row, 0).data(Qt.UserRole)
        dlg = EditDialog(self.inv, self.inv.items[iid], self.locations(), self)
        if dlg.exec() == QDialog.Accepted:
            self.inv.update(iid, **dlg.changes())
            self.save()
            self.refresh()

    def move_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        loc, ok = QInputDialog.getItem(self, "Przenieś sprzęt", f"Nowa sala dla {len(ids)} szt.:",
                                       self.locations(), 0, True)
        if not ok or not loc.strip():
            return
        for iid in ids:
            self.inv.update(iid, sala=loc.strip(), pewnosc="pewna")
        self.save()
        self.refresh()

    def mark_checked(self) -> None:
        today = date.today().isoformat()
        for iid in self._selected_ids():
            self.inv.update(iid, sprawdzono=today, pewnosc="pewna")
        self.save()
        self.refresh()

    def import_ewidencja(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Wybierz zestawienia z ewidencji (można zaznaczyć wiele)", str(self.inv_path.parent),
            "Excel (*.xls *.xlsx)")
        if not paths:
            return
        paths = [Path(p) for p in paths if Path(p).resolve() != self.inv_path.resolve()]
        items, rep = import_files(paths, verified_label="ewidencja: zgadza się")
        preview = copy.deepcopy(self.inv)
        mrep = merge(preview, items)
        first = not self.inv.items

        html = (f"<h3>Import ewidencji</h3>Plików: <b>{len(rep.files)}</b> · wierszy: {rep.rows} · "
                f"sztuk: <b>{rep.items}</b> · rozbite numery: {len(rep.split_rows)} · "
                f"duplikaty pominięte: {len(rep.duplicates)} · do sprawdzenia: <b>{len(rep.uncertain)}</b>")
        if not first:
            html += (f"<br>Względem obecnego spisu: nowe <b>{len(mrep.added)}</b> · zaktualizowane "
                     f"{mrep.updated} · zmieniony opis w ewidencji <b>{len(mrep.changed_desc)}</b> · "
                     f"zniknęły z ewidencji <b>{len(mrep.missing)}</b><br>"
                     "<i>Twoje pola (sala faktyczna, status, użytkownik, uwagi) nie zostaną zmienione.</i>")
        lines = []
        if rep.warnings:
            lines += ["⚠️ Ostrzeżenia:"] + ["   " + w for w in rep.warnings] + [""]
        if not first:
            if mrep.changed_desc:
                lines += ["✏ Zmienił się opis lokalizacji w ewidencji:"] + ["   " + s for s in mrep.changed_desc] + [""]
            if mrep.missing:
                lines += ["➖ Nie ma ich w nowym zestawieniu:"] + ["   " + s for s in mrep.missing] + [""]
            if mrep.added:
                lines += ["🆕 Nowe:"] + ["   " + s for s in mrep.added] + [""]
        lines += ["❓ Lokalizacja do sprawdzenia:"] + ["   " + s for s in rep.uncertain] + [""]
        lines += ["✂ Numery z kilkoma sztukami (rozbite na #1, #2…):"] + ["   " + s for s in rep.split_rows]
        if rep.duplicates:
            lines += ["", "♊ Duplikaty (ten sam numer w kilku plikach — wzięty pierwszy):"] + \
                     ["   " + s for s in rep.duplicates]
        dlg = ReportDialog("Import ewidencji", html, "\n".join(lines), "Importuj", self)
        if dlg.exec() != QDialog.Accepted:
            return
        merge(self.inv, items)
        self.inv.ensure_rooms(self.plan_rooms + self.inv.locations())
        if self.save():
            QMessageBox.information(self, "Import", f"Zapisano spis: {self.inv_path}")
        self.refresh()
