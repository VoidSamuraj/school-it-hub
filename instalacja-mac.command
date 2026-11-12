#!/bin/bash
# Wolne Sale — instalacja (jednorazowo) na macOS
cd "$(dirname "$0")/aplikacja" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Nie znaleziono Pythona 3. Zainstaluj go z https://www.python.org/downloads/ i uruchom ponownie."
  read -r -p "Naciśnij Enter, aby zamknąć…"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Tworzę środowisko .venv …"
  python3 -m venv .venv || exit 1
fi

echo "Instaluję biblioteki (kilka minut) …"
.venv/bin/python -m pip install --upgrade pip
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo "Instalacja nie powiodła się — sprawdź komunikaty powyżej."
  read -r -p "Naciśnij Enter, aby zamknąć…"
  exit 1
fi

chmod +x ../start-mac.command 2>/dev/null
echo
echo "Gotowe. Program uruchamiasz plikiem start-mac.command"
read -r -p "Naciśnij Enter, aby zamknąć…"
