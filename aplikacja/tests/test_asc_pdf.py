"""Testy na prawdziwym PDF-ie z aSc (leży lokalnie w dane/, poza gitem)."""
from pathlib import Path

import pytest

from wolnesale.core.asc_pdf import parse_pdf

PDF = Path(__file__).resolve().parents[2] / "dane" / "05.10.2026.pdf"   # <projekt>\dane
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="brak lokalnego PDF-a z planem")


@pytest.fixture(scope="module")
def parsed():
    return parse_pdf(PDF)


def test_structure(parsed):
    tt, rep = parsed
    assert rep.pages == 19
    assert len(tt.teachers) >= 70
    assert [p.nr for p in tt.periods] == list(range(1, 11))
    assert tt.period_by_nr[1].label == "7:30–8:15"
    assert tt.period_by_nr[10].label == "15:20–16:05"
    assert tt.days == [0, 1, 2, 3, 4]
    assert tt.generated == "30.09.2026"


def test_rooms(parsed):
    tt, _ = parsed
    for r in ["11W", "37", "6B", "24A", "19WA", "D1", "D2", "M1", "M2"]:
        assert r in tt.rooms, r


def test_quality(parsed):
    tt, rep = parsed
    assert rep.lessons >= 1500
    assert rep.ok, rep.warnings[:20]
    assert rep.lessons_without_room <= rep.lessons * 0.02


def test_known_lesson(parsed):
    tt, _ = parsed
    # środa, 6. lekcja: ezdr w sali 37, klasa 2b
    ls = [l for l in tt.lessons_at("37", 2, 6) if l.subject == "ezdr"]
    assert ls and ls[0].subject == "ezdr" and ls[0].cls == "2b"


def test_group_and_class_split(parsed):
    tt, _ = parsed
    # wtorek 1. lekcja: zp-rmal 14w, klasa 2t, grupa gr1
    ls = [l for l in tt.lessons_at("14W", 1, 1) if l.subject == "zp-rmal"]
    assert ls and ls[0].cls == "2t" and ls[0].group == "gr1"
