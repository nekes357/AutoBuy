from src.currency import cny_to_rub


def test_cny_to_rub_uses_settings_rate():
    # CNY_RUB_RATE=12.5 set in conftest
    assert cny_to_rub(100.0) == 1250.00
    assert cny_to_rub(0.0) == 0.0
    assert cny_to_rub(1.234) == round(1.234 * 12.5, 2)
