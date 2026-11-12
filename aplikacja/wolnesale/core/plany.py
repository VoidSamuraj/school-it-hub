"""Przechowywanie wersji planu: aktywny plan jako JSON, poprzednie wersje i kopie PDF-ów."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import Timetable
from .sale import sort_key


@dataclass
class RoomDiff:
    room: str
    before: int    # liczba zajętych lekcji w tygodniu
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


class PlanStore:
    """
    active_path  — aktywny plan (program/plan.json)
    versions_dir — poprzednie wersje JSON (kopie/plany)
    sources_dir  — kopie PDF-ów, z których powstały plany (zrodla/plany)
    """

    def __init__(self, active_path: Path, versions_dir: Path, sources_dir: Path):
        self.active_path = Path(active_path)
        self.versions_dir = Path(versions_dir)
        self.sources_dir = Path(sources_dir)

    def load_active(self) -> Timetable | None:
        if not self.active_path.exists():
            return None
        with self.active_path.open(encoding="utf-8") as f:
            return Timetable.from_dict(json.load(f))

    def _archive_active(self, stamp: str) -> None:
        if self.active_path.exists():
            self.versions_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.active_path, self.versions_dir / f"{stamp}_poprzedni.json")

    def activate(self, tt: Timetable, pdf: Path) -> Path:
        """Zapisuje plan jako aktywny; poprzedni trafia do wersji, PDF do źródeł (jeśli jeszcze go tam nie ma)."""
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        self._archive_active(stamp)

        pdf = Path(pdf)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        if pdf.resolve().parent == self.sources_dir.resolve():
            pdf_copy = pdf
        else:
            pdf_copy = self.sources_dir / f"{stamp}_{pdf.name}"
            shutil.copy2(pdf, pdf_copy)

        tmp = self.active_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(tt.to_dict(), f, ensure_ascii=False, indent=1)
        tmp.replace(self.active_path)
        return pdf_copy

    def versions(self) -> list[Path]:
        return sorted(self.versions_dir.glob("*.json"), reverse=True) if self.versions_dir.exists() else []

    def restore(self, version: Path) -> Timetable:
        with Path(version).open(encoding="utf-8") as f:
            tt = Timetable.from_dict(json.load(f))
        self._archive_active(datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(version, self.active_path)
        return tt


def diff_plans(old: Timetable | None, new: Timetable) -> list[RoomDiff]:
    """Zmiana liczby zajętych lekcji w tygodniu dla każdej sali."""
    rooms = set(new.rooms) | (set(old.rooms) if old else set())
    out = []
    for r in sorted(rooms, key=sort_key):
        before = old.busy_count(r) if old else 0
        after = new.busy_count(r)
        if before != after:
            out.append(RoomDiff(r, before, after))
    return out
