import pytest

from dashpi.ranges import parse_range


def test_range_forms():
    assert parse_range(None, 10) is None
    assert parse_range("bytes=2-5", 10) == (2, 5)
    assert parse_range("bytes=7-", 10) == (7, 9)
    assert parse_range("bytes=-3", 10) == (7, 9)


@pytest.mark.parametrize(
    "value", ["items=0-1", "bytes=9-2", "bytes=0-1,4-5", "bytes=20-30"]
)
def test_invalid_range_is_rejected(value):
    with pytest.raises(ValueError):
        parse_range(value, 10)
