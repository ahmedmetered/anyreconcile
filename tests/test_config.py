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


# Settings from the TOML file are checked, so a typo cannot crash the run or quietly give
# wrong results (a string for hint_words used to be split into single letters).


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ('window_days = "3"', "window_days"),
        ("window_days = -1", "window_days"),
        ("window_days = 2.5", "window_days"),
        ("early_days = true", "early_days"),
        ("max_rate_age_days = -7", "max_rate_age_days"),
        ('fee_tolerance_eur = "abc"', "fee_tolerance_eur"),
        ("fee_tolerance_eur = -1", "fee_tolerance_eur"),
        ('fx_spread_pct = "nan"', "fx_spread_pct"),
        ('hint_words = "STRIPE"', "hint_words"),
        ('hint_words = [""]', "hint_words"),
        ("hint_words = [5]", "hint_words"),
        ("my_accounts = 5", "my_accounts"),
    ],
)
def test_bad_setting_is_an_error_that_names_the_key(tmp_path, line, key):
    f = tmp_path / "c.toml"
    f.write_text(line + "\n")
    with pytest.raises(ValueError, match=key):
        load_config(f)


def test_valid_settings_still_load(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text(
        'window_days = 0\nearly_days = 0\nfee_tolerance_eur = "0.5"\nfx_spread_pct = 2\n'
        'hint_words = ["STRIPE", "PAYOUT"]\nmy_accounts = []\n'
    )
    cfg = load_config(f)
    assert (cfg.window_days, cfg.early_days) == (0, 0)
    assert (cfg.fee_tolerance_eur, cfg.fx_spread_pct) == (Decimal("0.5"), Decimal("2"))
    assert cfg.hint_words == ("STRIPE", "PAYOUT") and cfg.my_accounts == ()
