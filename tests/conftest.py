from pathlib import Path

import pytest

from anyreconcile.fx import Rates, load_rates

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rates() -> Rates:
    return load_rates(FIXTURES / "ecb_rates.csv")
