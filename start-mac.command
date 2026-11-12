#!/bin/bash
# Wolne Sale — uruchomienie na macOS (okno programu). W przeglądarce: dopisz --browser
cd "$(dirname "$0")/aplikacja" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "Najpierw uruchom instalacja-mac.command"
  read -r -p "Naciśnij Enter, aby zamknąć…"
  exit 1
fi
exec .venv/bin/python -m wolnesale "$@"
