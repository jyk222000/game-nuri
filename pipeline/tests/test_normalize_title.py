from refiner.rules.normalize_title import normalize_title


def test_removes_platform_and_edition():
    assert normalize_title("SONY PS5 엘든 링 한글판 (초회한정)") == "엘든 링"
