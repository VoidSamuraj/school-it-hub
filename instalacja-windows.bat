@echo off
rem Wolne Sale — instalacja (jednorazowo) na Windows
cd /d "%~dp0aplikacja"
where python >nul 2>nul
if errorlevel 1 (
  echo Nie znaleziono Pythona. Zainstaluj Python 3.12+ z https://www.python.org/downloads/
  echo (zaznacz "Add python.exe to PATH") i uruchom ten plik ponownie.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Tworze srodowisko .venv ...
  python -m venv .venv
)
echo Instaluje biblioteki (kilka minut) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Instalacja nie powiodla sie - sprawdz komunikaty powyzej.
  pause
  exit /b 1
)
echo.
echo Gotowe. Program uruchamiasz plikiem start.bat
pause
