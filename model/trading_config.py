#!/usr/bin/env python

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TradingConfig:
    """Configuration class for trading parameters."""
    ticker: str
    contract_id: str
    quantity: Decimal
    max_position_count: Decimal
    take_profit: Decimal
    tick_size: Decimal
    min_quantity: Decimal
    direction: str
    max_orders: int
    base_multiple: int
    wait_time: float
    exchange: str
    public_key: str
    secret_key: str


    @property
    def close_order_side(self) -> str:
        """Get the close order side based on bot direction."""
        return 'buy' if self.direction == "sell" else 'sell'
