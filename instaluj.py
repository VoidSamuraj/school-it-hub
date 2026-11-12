"""Instalacja School IT Hub od zera — Windows, macOS, Linux.

    python instaluj.py           # instalacja / aktualizacja bibliotek
    python instaluj.py --demo    # + przykładowe (fikcyjne) dane w demo-dane/

Co robi:
  1. sprawdza wersję Pythona (wymagany 3.12+),
  2. tworzy środowisko aplikacja/.venv (jeśli go nie ma),
  3. instaluje biblioteki z aplikacja/requirements.txt,
  4. zakłada folder dane/ z podfolderami (zrodla, program, kopie),
  5. na macOS/Linux nadaje skryptom startowym prawo uruchamiania.
Można uruchamiać wielokrotnie — niczego nie kasuje.
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "aplikacja"
VENV = APP / ".venv"
WINDOWS = sys.platform.startswith("win")
PY = VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")


def step(n: int, text: str) -> None:
    print(f"\n[{n}/5] {text}", flush=True)


def fail(text: str) -> None:
    print(f"\n❌ {text}")
    sys.exit(1)


def main() -> None:
    print("School IT Hub — instalacja")
    print(f"Folder projektu: {ROOT}")

    step(1, "Sprawdzam Pythona")
    if sys.version_info < (3, 12):
        fail(f"Potrzebny Python 3.12 lub nowszy (masz {sys.version.split()[0]}). "
             "Pobierz z https://www.python.org/downloads/")
    print(f"   Python {sys.version.split()[0]} ✓")
    if not (APP / "requirements.txt").exists():
        fail("Nie znalazłem aplikacja/requirements.txt — uruchom skrypt z głównego folderu projektu.")

    step(2, "Środowisko aplikacja/.venv")
    if PY.exists():
        print("   już istnieje ✓")
    else:
        print("   tworzę…")
        venv.EnvBuilder(with_pip=True, clear=False, upgrade_deps=False).create(VENV)
        if not PY.exists():
            fail("Nie udało się utworzyć .venv.")
        print("   utworzone ✓")

    step(3, "Instaluję biblioteki (pierwszy raz kilka minut)")
    pip = [str(PY), "-m", "pip", "install", "--disable-pip-version-check"]
    if subprocess.call(pip + ["--upgrade", "pip", "-q"]) != 0:
        fail("Nie udało się zaktualizować pip — sprawdź połączenie z internetem.")
    if subprocess.call(pip + ["-r", str(APP / "requirements.txt")]) != 0:
        fail("Instalacja bibliotek nie powiodła się — komunikat powyżej.")
    print("   biblioteki zainstalowane ✓")

    step(4, "Folder na dane")
    code = "from wolnesale.ustawienia import paths; print(paths().root)"
    out = subprocess.run([str(PY), "-c", code], cwd=APP, capture_output=True, text=True)
    if out.returncode != 0:
        fail("Nie udało się utworzyć folderu dane/:\n" + out.stderr)
    print(f"   {out.stdout.strip()} ✓  (zrodla/, program/, kopie/, CZYTAJ.txt)")

    if "--demo" in sys.argv:
        print("   + dane demonstracyjne…")
        subprocess.call([str(PY), "-m", "wolnesale.demo", str(ROOT / "demo-dane")], cwd=APP)

    step(5, "Skrypty startowe")
    if not WINDOWS:
        for name in ("start-mac.command", "instalacja-mac.command"):
            p = ROOT / name
            if p.exists():
                os.chmod(p, 0o755)
        print("   start-mac.command gotowy ✓")
    else:
        print("   start.bat gotowy ✓")

    start = "start.bat" if WINDOWS else "./start-mac.command"
    py_rel = PY.relative_to(APP)
    print(f"""
✅ Gotowe!

Uruchom program:   {start}   (dwuklik)
Albo w terminalu:  cd aplikacja,  potem  {py_rel} -m wolnesale
Dane demo:         {start} --demo
""")


if __name__ == "__main__":
    main()
