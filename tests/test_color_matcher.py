from color_matcher import ColorMatcher


def test_exact_match():
    m = ColorMatcher(tolerance=0)
    m.add_background((10, 10, 15))
    m.add_key((240, 80, 90))
    assert m.is_background((10, 10, 15))
    assert m.is_key((240, 80, 90))
    assert m.classify((10, 10, 15)) == "background"
    assert m.classify((240, 80, 90)) == "key"


def test_tolerance_boundary():
    m = ColorMatcher(tolerance=10)
    m.add_key((100, 100, 100))
    assert m.is_key((105, 100, 100))       # 距离 5 <= 10
    assert not m.is_key((130, 100, 100))   # 距离 30 > 10


def test_key_wins_over_background():
    m = ColorMatcher(tolerance=200)
    m.add_background((10, 10, 15))
    m.add_key((20, 20, 25))
    assert m.classify((15, 15, 20)) == "key"


def test_unknown_when_no_match():
    m = ColorMatcher(tolerance=0)
    m.add_background((0, 0, 0))
    assert m.classify((255, 255, 255)) == "unknown"


def test_remove():
    m = ColorMatcher(tolerance=0)
    m.add_key((1, 2, 3))
    assert m.remove_key((1, 2, 3)) is True
    assert not m.is_key((1, 2, 3))
    assert m.remove_key((9, 9, 9)) is False


def test_empty_matcher_is_unknown():
    m = ColorMatcher()
    assert m.classify((0, 0, 0)) == "unknown"
    assert m.background_colors == []
    assert m.key_colors == []


def test_no_duplicates():
    m = ColorMatcher(tolerance=0)
    m.add_key((1, 2, 3))
    m.add_key((1, 2, 3))
    assert len(m.key_colors) == 1
