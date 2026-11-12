@echo off
rem School IT Hub — instalacja na Windows (dwuklik). Robi wszystko skrypt instaluj.py.
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 instaluj.py %*
  goto koniec
)
where python >nul 2>nul
if not errorlevel 1 (
  python instaluj.py %*
  goto koniec
)
echo Nie znaleziono Pythona. Zainstaluj Python 3.12+ z https://www.python.org/downloads/
echo (w instalatorze zaznacz "Add python.exe to PATH") i uruchom ten plik ponownie.
:koniec
pause
