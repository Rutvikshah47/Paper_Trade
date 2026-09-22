from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=30)
    expiry: date
    strike: float = Field(gt=0)
    option_type: Literal["CE", "PE"]
    side: Literal["BUY", "SELL"]
    entry_price: float = Field(ge=0)
    lots: int = Field(gt=0, le=10000)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    orders: list[OrderCreate] = Field(min_length=1, max_length=50)


class OrderView(BaseModel):
    id: int
    symbol: str
    instrument_key: str
    trading_symbol: str | None
    expiry: date
    strike: float
    option_type: str
    side: str
    entry_price: float
    lots: int
    lot_size: int
    quantity: int
    status: str
    current_ltp: float | None
    pnl: float | None


class StrategyView(BaseModel):
    id: int
    name: str
    description: str
    status: str
    created_at: datetime
    orders: list[OrderView]
    pnl: float
    priced_legs: int
    total_legs: int


class DashboardView(BaseModel):
    strategies: list[StrategyView]
    total_pnl: float
    open_orders: int
    market_data_mode: str
