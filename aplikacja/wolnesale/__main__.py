"""Start programu.

    python -m wolnesale              okno programu
    python -m wolnesale --browser    w przeglądarce (http://127.0.0.1:8765)
    python -m wolnesale --siec       w przeglądarce + dostęp z telefonu w tej samej sieci Wi-Fi
    python -m wolnesale --demo       na fikcyjnych danych demonstracyjnych (folder demo-dane/)
    python -m wolnesale --dane DIR   na danych z innego folderu
    python -m wolnesale --qt         stary interfejs Qt
"""
import os
import sys
from pathlib import Path

# folder danych trzeba ustawić, zanim program wczyta stan
if "--dane" in sys.argv:
    i = sys.argv.index("--dane")
    if i + 1 < len(sys.argv):
        os.environ["WOLNESALE_DANE"] = str(Path(sys.argv[i + 1]).resolve())
elif "--demo" in sys.argv:
    from wolnesale.ustawienia import project_root
    demo_dir = project_root() / "demo-dane"
    if not (demo_dir / "program" / "zasoby.xlsx").exists():
        from wolnesale.demo import build
        build(demo_dir)
    os.environ["WOLNESALE_DANE"] = str(demo_dir)

if "--qt" in sys.argv:
    from wolnesale.ui.main_window import run
    sys.exit(run())

from wolnesale.web.app import main  # noqa: E402

if __name__ in {"__main__", "__mp_main__"}:
    show = "--no-show" not in sys.argv
    if "--siec" in sys.argv:
        main(native=False, host="0.0.0.0", show=show)
    else:
        main(native="--browser" not in sys.argv, show=show)
