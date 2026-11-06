from decimal import Decimal

import pytest

from anyreconcile.config import Config, load_config


def test_defaults_when_no_file():
    assert load_config(None) == Config()


def test_file_overrides_defaults(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('fee_tolerance_eur = 0.5\nwindow_days = 5\nmy_accounts = ["wise_eur"]\n')
    cfg = load_config(f)
    assert cfg.fee_tolerance_eur == Decimal("0.5")
    assert cfg.window_days == 5
    assert cfg.my_accounts == ("wise_eur",)
    assert cfg.fx_spread_pct == Decimal("1.5")  # untouched default


def test_unknown_key_is_rejected(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("fee_tolerence_eur = 1\n")
    with pytest.raises(ValueError, match="fee_tolerence_eur"):
        load_config(f)
