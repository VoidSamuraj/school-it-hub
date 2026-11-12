import pytest

from wolnesale.core.sale import (BURSA, GIMNASTYCZNA, GLOWNY, WARSZTAT, building,
                                 looks_like_room, normalize_room, sort_key)


@pytest.mark.parametrize("raw, norm", [
    ("04W", "4W"), ("4w", "4W"), ("16.0", "16"), ("11w", "11W"),
    ("24a", "24A"), ("19wa", "19WA"), ("D1", "D1"), ("m2", "M2"), (" 6b ", "6B"),
])
def test_normalize(raw, norm):
    assert normalize_room(raw) == norm


@pytest.mark.parametrize("room, b", [
    ("11W", WARSZTAT), ("19WA", WARSZTAT), ("6B", BURSA), ("12", GLOWNY),
    ("24A", GLOWNY), ("D1", GIMNASTYCZNA), ("M2", GIMNASTYCZNA),
])
def test_building(room, b):
    assert building(room) == b


@pytest.mark.parametrize("tok, ok", [
    ("37", True), ("11w", True), ("24a", True), ("19wa", True), ("D1", True), ("M2", True),
    ("ezdr", False), ("gr1", False), ("2TM", False), ("r1/r2", False),
])
def test_looks_like_room(tok, ok):
    assert looks_like_room(tok) is ok


def test_sort_key_groups_buildings():
    rooms = ["11W", "2", "6B", "D1", "12", "5W", "24A"]
    assert sorted(rooms, key=sort_key) == ["2", "12", "24A", "5W", "11W", "6B", "D1"]
