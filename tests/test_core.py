import pytest

from core import format_process_number


def test_format_process_number_valid():
    raw = "07006722020198070001"
    expected = "0700672-20.2019.8.07.0001"
    assert format_process_number(raw) == expected


@pytest.mark.parametrize("value", [
    "123",
    "070067220201980700012",  # too long
])
def test_format_process_number_invalid(value):
    with pytest.raises(ValueError):
        format_process_number(value)

