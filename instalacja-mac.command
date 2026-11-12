#!/bin/bash
# School IT Hub — instalacja na macOS (dwuklik albo ./instalacja-mac.command). Robi wszystko instaluj.py.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 instaluj.py "$@"
else
  echo "Nie znaleziono Pythona 3. Zainstaluj Python 3.12+ z https://www.python.org/downloads/"
fi
read -r -p "Naciśnij Enter, aby zamknąć…"
