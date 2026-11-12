"""Okno główne, wczytywanie PDF-a z raportem, przywracanie wersji."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog,
                               QInputDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressDialog, QPushButton, QStackedWidget, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..core.asc_pdf import ParseReport, parse_pdf
from ..core.model import Timetable
from ..core.plany import PlanStore, diff_plans
from ..ustawienia import Settings, data_dir, paths
from .sprzet_view import SprzetView
from .views import DayView, RoomView, SearchView, WeekView


class _ParseWorker(QObject):
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            tt, rep = parse_pdf(self.path)
            self.done.emit(tt, rep)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class ImportDialog(QDialog):
    """Raport z wczytania PDF-a — użytkownik zatwierdza albo anuluje."""

    def __init__(self, tt: Timetable, rep: ParseReport, old: Timetable | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy plan — sprawdź przed zatwierdzeniem")
        self.resize(720, 560)
        icon = "✅" if rep.ok else "⚠️"
        head = QLabel(
            f"<h3>{icon} {tt.source}</h3>"
            f"Wygenerowany w aSc: <b>{tt.generated or '?'}</b><br>"
            f"Stron: {rep.pages} · nauczycieli: <b>{len(tt.teachers)}</b> · lekcji: <b>{rep.lessons}</b>"
            f" · sal: <b>{len(tt.rooms)}</b> · lekcji bez sali: {rep.lessons_without_room}<br>"
            f"Dni: {len(tt.days)} · lekcje: {tt.periods[0].nr}–{tt.periods[-1].nr} "
            f"({tt.periods[0].start}–{tt.periods[-1].end})"
        )
        if not rep.ok:
            head.setText(head.text() + "<p style='color:#b00020'><b>Dużo problemów — "
                                       "sprawdź, czy to właściwy wydruk (plany nauczycieli).</b></p>")
        lines = []
        if old:
            new_rooms = sorted(set(tt.rooms) - set(old.rooms))
            gone = sorted(set(old.rooms) - set(tt.rooms))
            if new_rooms:
                lines.append("🆕 Nowe sale: " + ", ".join(new_rooms))
            if gone:
                lines.append("➖ Sale, których już nie ma w planie: " + ", ".join(gone))
            diffs = diff_plans(old, tt)
            lines.append(f"\n📊 Zmiany zajętości względem poprzedniego planu ({len(diffs)} sal):")
            for d in diffs:
                lines.append(f"   {d.room:>5}: {d.before:2} → {d.after:2}  ({d.delta:+d})")
            if not diffs:
                lines.append("   brak zmian")
        else:
            lines.append("To pierwszy wczytany plan.")
            lines.append("Sale: " + ", ".join(tt.rooms))
        lines.append(f"\n⚠️ Ostrzeżenia ({len(rep.warnings)}):")
        lines.extend("   " + w for w in rep.warnings) if rep.warnings else lines.append("   brak")

        box = QPlainTextEdit("\n".join(lines))
        box.setReadOnly(True)
        buttons = QDialogButtonBox()
        ok = buttons.addButton("Zatwierdź — ustaw jako aktywny plan", QDialogButtonBox.AcceptRole)
        buttons.addButton("Anuluj", QDialogButtonBox.RejectRole)
        ok.setDefault(rep.ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(box, 1)
        lay.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wolne Sale")
        self.resize(1400, 820)
        self.settings = Settings.load()
        p = paths()
        self.store = PlanStore(p.plan, p.kopie_plany, p.zrodla_plany)
        self.tt: Timetable | None = None
        self._thread: QThread | None = None

        self.week = WeekView()
        self.day = DayView()
        self.search = SearchView()
        self.room = RoomView()
        self.views = [self.week, self.day, self.search, self.room]
        self.sprzet = SprzetView(p.zasoby, p.kopie_zasoby)
        self.tabs = QTabWidget()
        for v in self.views:
            v.roomActivated.connect(self.open_room)
        self.room.showEquipment.connect(self.show_equipment)
        self.sprzet.changed.connect(lambda: self.room.set_inventory(self.sprzet.inv))

        # ekran powitalny, gdy nie ma planu
        welcome = QWidget()
        wl = QVBoxLayout(welcome)
        wl.addStretch()
        lab = QLabel("<h2>Brak wczytanego planu</h2>"
                     "Wydrukuj w aSc plany <b>nauczycieli</b> do PDF i wczytaj plik.")
        lab.setAlignment(Qt.AlignCenter)
        btn = QPushButton("📄 Wczytaj PDF z planem…")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.load_pdf)
        wl.addWidget(lab)
        wl.addWidget(btn, 0, Qt.AlignCenter)
        wl.addStretch()

        self.welcome = welcome
        self.tabs.addTab(welcome, "📄 Start")
        self.tabs.addTab(self.search, "🔎 Wolne sale")
        self.tabs.addTab(self.week, "🗓 Tydzień")
        self.tabs.addTab(self.day, "📅 Dzień")
        self.tabs.addTab(self.room, "🚪 Sala")
        self.tabs.addTab(self.sprzet, "🖥 Sprzęt")
        self.setCentralWidget(self.tabs)
        self._menu()

        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(self.settings.window_geometry.encode()))
        err = self.sprzet.load()
        if err:
            QMessageBox.warning(self, "Wolne Sale", err)
        self.room.set_inventory(self.sprzet.inv)
        try:
            self.set_timetable(self.store.load_active())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Wolne Sale", f"Nie udało się wczytać zapisanego planu:\n{e}")
            self.set_timetable(None)

    def _menu(self):
        m = self.menuBar().addMenu("&Plan")
        a = QAction("📄 Wczytaj nowy PDF…", self)
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self.load_pdf)
        m.addAction(a)
        a = QAction("↩ Przywróć poprzednią wersję…", self)
        a.triggered.connect(self.restore_version)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Zakończ", self)
        a.triggered.connect(self.close)
        m.addAction(a)
        s = self.menuBar().addMenu("&Sprzęt")
        a = QAction("📥 Importuj ewidencję (xls)…", self)
        a.triggered.connect(lambda: (self.tabs.setCurrentWidget(self.sprzet), self.sprzet.import_ewidencja()))
        s.addAction(a)
        a = QAction("📂 Otwórz zasoby.xlsx w Excelu", self)
        a.triggered.connect(self.open_inventory_file)
        s.addAction(a)
        a = QAction("🔄 Wczytaj ponownie (po edycji w Excelu)", self)
        a.triggered.connect(self.reload_inventory)
        s.addAction(a)
        h = self.menuBar().addMenu("Pomo&c")
        a = QAction("O programie", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "Wolne Sale", f"Wolne Sale {__version__}\nPlan z aSc (PDF), wolne sale, spis sprzętu."))
        h.addAction(a)

    # ------------------------------------------------------------------
    def set_timetable(self, tt: Timetable | None):
        self.tt = tt
        for v in self.views:
            v.set_timetable(tt)
        self.sprzet.set_plan_rooms(tt.rooms if tt else [])
        self.tabs.setTabVisible(self.tabs.indexOf(self.welcome), tt is None)
        for v in self.views:
            self.tabs.setTabEnabled(self.tabs.indexOf(v), tt is not None)
        self.tabs.setCurrentWidget(self.search if tt else self.welcome)
        if tt:
            self.statusBar().showMessage(
                f"Plan: {tt.source} · wygenerowany {tt.generated or '?'} · "
                f"{len(tt.rooms)} sal · {len(tt.lessons)} lekcji")
        else:
            self.statusBar().showMessage("Brak planu")

    def open_room(self, room: str):
        self.room.show_room(room)
        self.tabs.setCurrentWidget(self.room)

    def show_equipment(self, room: str):
        self.sprzet.select_location(room)
        self.tabs.setCurrentWidget(self.sprzet)

    def open_inventory_file(self):
        p = self.sprzet.inv_path
        if not p.exists():
            QMessageBox.information(self, "Wolne Sale", "Spisu jeszcze nie ma — najpierw zaimportuj ewidencję.")
            return
        QMessageBox.information(
            self, "Edycja w Excelu",
            "Po zapisaniu zmian w Excelu zamknij plik i wybierz Sprzęt → Wczytaj ponownie.\n"
            "Nie edytuj w programie, gdy plik jest otwarty w Excelu.")
        from ..ustawienia import open_in_system
        open_in_system(p)

    def reload_inventory(self):
        err = self.sprzet.load()
        if err:
            QMessageBox.warning(self, "Wolne Sale", err)
        else:
            self.statusBar().showMessage(f"Wczytano spis: {len(self.sprzet.inv.items)} szt.", 6000)

    def load_pdf(self):
        start = self.settings.last_pdf_dir or str(data_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz PDF z planem z aSc", start, "PDF (*.pdf)")
        if not path:
            return
        self.settings.last_pdf_dir = str(Path(path).parent)
        self.settings.save()

        self._progress = QProgressDialog("Czytam plan z PDF-a…", None, 0, 0, self)
        self._progress.setWindowTitle("Wolne Sale")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.show()

        self._pending_pdf = Path(path)
        self._thread = QThread(self)
        self._worker = _ParseWorker(Path(path))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        # sloty to metody okna -> wywołanie w wątku GUI (połączenie kolejkowane)
        self._worker.done.connect(self._parsed)
        self._worker.failed.connect(self._parse_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _parse_failed(self, msg: str):
        self._progress.close()
        QMessageBox.critical(self, "Nie udało się wczytać planu", msg)

    def _parsed(self, tt: Timetable, rep: ParseReport):
        self._progress.close()
        path = self._pending_pdf
        dlg = ImportDialog(tt, rep, self.tt, self)
        if dlg.exec() == QDialog.Accepted:
            self.store.activate(tt, path)
            self.set_timetable(tt)
            self.statusBar().showMessage(f"Wczytano nowy plan: {tt.source}", 8000)

    def restore_version(self):
        versions = self.store.versions()
        if not versions:
            QMessageBox.information(self, "Wolne Sale", "Nie ma jeszcze poprzednich wersji planu.")
            return
        names = [v.name for v in versions]
        name, ok = QInputDialog.getItem(self, "Przywróć plan", "Wersja (data zastąpienia):", names, 0, False)
        if ok and name:
            tt = self.store.restore(versions[names.index(name)])
            self.set_timetable(tt)

    def closeEvent(self, e):
        self.settings.window_geometry = bytes(self.saveGeometry().toHex()).decode()
        self.settings.save()
        super().closeEvent(e)


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Wolne Sale")
    w = MainWindow()
    w.show()
    return app.exec()
