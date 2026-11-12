"""Ścieżki i ustawienia programu (lokalnie, w folderze dane/ — poza gitem).

Układ folderu danych:

    dane/
      zrodla/            pliki od innych — program je tylko CZYTA (kopie przy wczytaniu)
        plany/           PDF-y planu z aSc
        ewidencja/       zestawienia .xls od księgowej (każdy import w swoim podfolderze)
      program/           to, co prowadzi program
        plan.json        aktywny plan lekcji (odczytany z PDF-a)
        zasoby.xlsx      sprzęt, historia, sale, zaplecze, modele drukarek
        ustawienia.json
      kopie/             automatyczne kopie zapasowe
        zasoby/          zasoby.xlsx sprzed każdego zapisu (ostatnie 30)
        plany/           poprzednie wersje planu (do przywrócenia)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_dir() -> Path:
    """Folder aplikacja\\ (kod programu)."""
    if getattr(sys, "frozen", False):        # spakowany .exe leży w aplikacja\
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    """Główny folder projektu: aplikacja\\, dane\\, dokumentacja\\, start.bat."""
    return app_dir().parent


def data_dir() -> Path:
    """Folder danych: dane\\ w głównym folderze (albo WOLNESALE_DANE — np. do testów)."""
    d = Path(os.environ["WOLNESALE_DANE"]) if os.environ.get("WOLNESALE_DANE") else project_root() / "dane"
    d.mkdir(exist_ok=True)
    return d


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def zrodla(self) -> Path:
        return self.root / "zrodla"

    @property
    def zrodla_plany(self) -> Path:
        return self.zrodla / "plany"

    @property
    def zrodla_ewidencja(self) -> Path:
        return self.zrodla / "ewidencja"

    @property
    def program(self) -> Path:
        return self.root / "program"

    @property
    def plan(self) -> Path:
        return self.program / "plan.json"

    @property
    def zasoby(self) -> Path:
        return self.program / "zasoby.xlsx"

    @property
    def ustawienia(self) -> Path:
        return self.program / "ustawienia.json"

    @property
    def kopie(self) -> Path:
        return self.root / "kopie"

    @property
    def kopie_zasoby(self) -> Path:
        return self.kopie / "zasoby"

    @property
    def kopie_plany(self) -> Path:
        return self.kopie / "plany"

    def ensure(self) -> "Paths":
        for d in (self.zrodla_plany, self.zrodla_ewidencja, self.program, self.kopie_zasoby, self.kopie_plany):
            d.mkdir(parents=True, exist_ok=True)
        readme = self.root / "CZYTAJ.txt"
        if not readme.exists():
            readme.write_text(README_TXT, encoding="utf-8")
        return self


README_TXT = """Folder danych programu Wolne Sale

zrodla\\     pliki od innych (PDF planu z aSc, zestawienia od księgowej).
            Program ich nie zmienia — przy wczytaniu zapisuje tu kopię, żeby było wiadomo,
            z czego powstały dane.
program\\    dane, które prowadzi program:
            plan.json   - aktywny plan lekcji (odczytany z PDF-a)
            zasoby.xlsx - sprzęt, historia zmian, sale, zaplecze, modele drukarek
                          (można otwierać w Excelu; nie edytuj jednocześnie w programie)
kopie\\      automatyczne kopie zapasowe (zasoby.xlsx sprzed każdego zapisu, poprzednie plany).

Twoje własne pliki możesz trzymać bezpośrednio w tym folderze albo w zrodla\\ — program ich nie rusza.
"""


def paths() -> Paths:
    p = Paths(data_dir())
    migrate_old_layout(p)
    return p.ensure()


def _move(src: Path, dst: Path, moved: list[str]) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    moved.append(f"{src} → {dst}")


def migrate_old_layout(p: Paths) -> list[str]:
    """Przenosi pliki PROGRAMU ze starego układu (dane/plany, dane/zasoby.xlsx…) do nowego.

    Nie rusza plików użytkownika leżących bezpośrednio w dane/ (PDF-y, xls od księgowej).
    """
    moved: list[str] = []
    r = p.root
    _move(r / "plany" / "aktywny.json", p.plan, moved)
    arch = r / "plany" / "archiwum"
    if arch.exists():
        for f in sorted(arch.iterdir()):
            target = (p.kopie_plany if f.suffix.lower() == ".json" else p.zrodla_plany) / f.name
            _move(f, target, moved)
        _rmdir_if_empty(arch)
    _rmdir_if_empty(r / "plany")
    _move(r / "zasoby.xlsx", p.zasoby, moved)
    _move(r / "ustawienia.json", p.ustawienia, moved)
    old_backups = r / "kopie"
    if old_backups.exists():
        for f in sorted(old_backups.glob("zasoby_*.xlsx")):
            _move(f, p.kopie_zasoby / f.name, moved)
    incoming = r / "przyjete"
    if incoming.exists():
        for f in sorted(incoming.iterdir()):
            if f.is_dir():
                _move(f, p.zrodla_ewidencja / f.name, moved)
            elif f.suffix.lower() == ".pdf":
                _move(f, p.zrodla_plany / f.name, moved)
            else:
                _move(f, p.zrodla_ewidencja / f.name, moved)
        _rmdir_if_empty(incoming)
    return moved


def open_in_system(path: Path) -> None:
    """Otwiera plik domyślnym programem systemu (Excel / Numbers / LibreOffice…)."""
    import subprocess
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607


def _rmdir_if_empty(d: Path) -> None:
    try:
        if d.exists() and d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass


@dataclass
class Settings:
    last_pdf_dir: str = ""
    window_geometry: str = ""
    extra: dict = field(default_factory=dict)

    @staticmethod
    def path() -> Path:
        return paths().ustawienia

    @classmethod
    def load(cls) -> "Settings":
        try:
            with cls.path().open(encoding="utf-8") as f:
                d = json.load(f)
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        with self.path().open("w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
