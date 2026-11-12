"""Stan aplikacji współdzielony przez ekrany (jeden użytkownik, lokalnie)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..core.model import Timetable
from ..core.plany import PlanStore
from ..core.sprzet import Inventory, InventoryLockedError
from ..ustawienia import paths


class AppState:
    def __init__(self) -> None:
        self.p = paths()
        self.store = PlanStore(self.p.plan, self.p.kopie_plany, self.p.zrodla_plany)
        self.inv_path = self.p.zasoby
        self.backup_dir = self.p.kopie_zasoby
        self.tt: Timetable | None = None
        self.inv: Inventory = Inventory(self.inv_path)
        self.errors: list[str] = []

    def load(self) -> None:
        try:
            self.tt = self.store.load_active()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"Nie udało się wczytać zapisanego planu: {e}")
        self.reload_inventory()

    def reload_inventory(self) -> str | None:
        try:
            self.inv = Inventory.load(self.inv_path)
            return None
        except Exception as e:  # noqa: BLE001
            self.inv = Inventory(self.inv_path)
            msg = f"Nie udało się wczytać {self.inv_path.name}: {e}"
            self.errors.append(msg)
            return msg

    def save_inventory(self) -> str | None:
        """Zapisuje spis; zwraca komunikat błędu albo None."""
        try:
            self.inv.save(backup_dir=self.backup_dir)
            return None
        except InventoryLockedError as e:
            return str(e)

    def plan_rooms(self) -> list[str]:
        return self.tt.rooms if self.tt else []

    def plan_upload_path(self, name: str) -> Path:
        """Gdzie zapisać wczytany PDF planu (źródła)."""
        return self.p.zrodla_plany / f"{datetime.now():%Y-%m-%d_%H%M%S}_{Path(name).name}"

    def ewidencja_upload_dir(self) -> Path:
        """Nowy podfolder na zestawienia z jednego importu (źródła)."""
        d = self.p.zrodla_ewidencja / f"{datetime.now():%Y-%m-%d_%H%M%S}"
        d.mkdir(parents=True, exist_ok=True)
        return d


S = AppState()
