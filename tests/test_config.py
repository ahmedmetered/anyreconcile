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


def test_aud3_max_rate_age_days_defaults_to_seven_and_loads_from_toml(tmp_path):
    assert Config().max_rate_age_days == 7
    f = tmp_path / "c.toml"
    f.write_text("max_rate_age_days = 10\n")
    assert load_config(f).max_rate_age_days == 10


def test_aud4_early_days_defaults_to_one_and_loads_from_toml(tmp_path):
    assert Config().early_days == 1
    f = tmp_path / "c.toml"
    f.write_text("early_days = 0\n")
    assert load_config(f).early_days == 0
