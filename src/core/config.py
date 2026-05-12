from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskConfig(BaseModel):
    max_drawdown_pct: float = 20.0
    max_position_size_pct: float = 10.0
    max_open_positions: int = 3
    daily_loss_limit_pct: float = 5.0
    leverage: int = 3

    def update(self, key: str, value: str) -> None:
        if not hasattr(self, key):
            raise ValueError(f"Unknown risk parameter: {key}")
        field_type = type(getattr(self, key))
        try:
            setattr(self, key, field_type(value))
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid value '{value}' for parameter '{key}' (expected {field_type.__name__})"
            ) from e


class BacktestConfig(BaseModel):
    fee_rate: float = 0.00055
    slippage_pct: float = 0.05
    initial_capital: float = 250.0


class StrategyEntry(BaseModel):
    name: str
    enabled: bool = True
    symbols: list[str] = ["BTCUSDT"]
    interval: str = "5"
    params: dict[str, Any] = {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_testnet: bool = True
    telegram_token: str = ""
    telegram_chat_id: str = ""

    risk: RiskConfig = RiskConfig()
    backtesting: BacktestConfig = BacktestConfig()
    strategies: list[StrategyEntry] = []

    @classmethod
    def from_yaml(cls, yaml_path: Path = Path("config/config.yaml")) -> Settings:
        data: dict[str, Any] = {}
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
        return cls(**data)
