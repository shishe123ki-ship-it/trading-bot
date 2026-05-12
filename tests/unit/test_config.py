import tempfile
from pathlib import Path
import yaml
from src.core.config import Settings, RiskConfig


def _yaml_settings(data: dict) -> Settings:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(data, f)
        return Settings.from_yaml(Path(f.name))


def test_settings_loads_defaults_from_empty_yaml():
    settings = _yaml_settings({})
    assert settings.risk.leverage == 3
    assert settings.risk.max_open_positions == 3
    assert settings.bybit_testnet is True


def test_settings_overrides_risk_from_yaml():
    settings = _yaml_settings({"risk": {"leverage": 5, "max_open_positions": 2}})
    assert settings.risk.leverage == 5
    assert settings.risk.max_open_positions == 2
    assert settings.risk.max_drawdown_pct == 20.0


def test_settings_loads_strategies_list():
    data = {
        "strategies": [
            {"name": "ema_cross", "enabled": True, "symbols": ["BTCUSDT"], "interval": "5"}
        ]
    }
    settings = _yaml_settings(data)
    assert len(settings.strategies) == 1
    assert settings.strategies[0].name == "ema_cross"
    assert settings.strategies[0].symbols == ["BTCUSDT"]


def test_settings_strategy_has_default_params():
    settings = _yaml_settings({"strategies": [{"name": "grid"}]})
    assert settings.strategies[0].params == {}
    assert settings.strategies[0].enabled is True


def test_risk_config_update_changes_value():
    risk = RiskConfig()
    risk.update("leverage", "7")
    assert risk.leverage == 7


def test_risk_config_update_preserves_other_values():
    risk = RiskConfig(leverage=3, max_open_positions=3)
    risk.update("leverage", "10")
    assert risk.max_open_positions == 3


def test_risk_config_update_unknown_key_raises():
    risk = RiskConfig()
    try:
        risk.update("nonexistent_key", "1")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Unknown risk parameter" in str(e)


def test_risk_config_update_invalid_value_raises():
    risk = RiskConfig()
    try:
        risk.update("leverage", "not_a_number")
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Invalid value" in str(e)
        assert "leverage" in str(e)
