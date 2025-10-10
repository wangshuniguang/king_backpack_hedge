#!/usr/bin/env python

import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple

from bpx.account import Account
from bpx.constants.enums import OrderTypeEnum, TimeInForceEnum
from bpx.public import Public

from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP

from helpers.logger import setup_logger
from model.order_info import OrderInfo
from model.order_result import OrderResult
from model.trading_config import TradingConfig

logger = setup_logger('backpack_client')


class BackpackClient(object):

    def __init__(self, config: TradingConfig):
        self.config = config
        self.public_key = config.public_key
        self.secret_key = config.secret_key

        if not self.public_key or not self.secret_key:
            raise ValueError("BACKPACK_PUBLIC_KEY and BACKPACK_SECRET_KEY must be set in environment variables")

        # Initialize Backpack clients using official SDK
        self.public_client = Public()
        self.account_client = Account(
            public_key=self.public_key,
            secret_key=self.secret_key
        )

        self._order_update_handler = None
        self.ws_manager = None
        self.logger = logger

    def round_to_tick(self, price) -> Decimal:
        price = Decimal(price)

        tick = self.config.tick_size
        # quantize forces price to be a multiple of tick
        return price.quantize(tick, rounding=ROUND_HALF_UP)

    @staticmethod
    def align_floor(quantity: Decimal, min_quantity: Decimal) -> Decimal:
        """
        向下对齐到最小交易单位的整数倍

        Args:
            quantity: 原始数量
            min_quantity: 最小数量

        Returns:
            向下对齐后的数量
        """
        multiplier = (quantity / min_quantity).to_integral_value(rounding=ROUND_DOWN)
        return multiplier * min_quantity

    async def batch_place_buy_limit_orders(
            self, contract_id: str, quantity: Decimal,
            order_num: int, position_rate: float):
        align_quantity = BackpackClient.align_floor(quantity, self.config.min_quantity)
        self.logger.info(
            f'batch place sell limit orders, contract id: {contract_id}, '
            f'min quantity: {self.config.min_quantity}, '
            f'quantity: {quantity:.4f}, '
            f'align quantity: {align_quantity}, '
            f'order num: {order_num}')
        order_book = self.public_client.get_depth(contract_id)
        if not isinstance(order_book, dict):
            return OrderResult(success=False, error_message='Unexpected order book response format')

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        orders = []

        side = 'Bid'
        basic_bid = bids[-1][0]

        base_multiple = self.config.base_multiple

        self.logger.info(
            f'place sell limit order, '
            f'position rate: {position_rate}, '
            f'base multiple: {base_multiple}')

        base = base_multiple * (Decimal(asks[0][0]) - Decimal(bids[-1][0]))
        for i in range(order_num):
            order_price = Decimal(basic_bid) - base * (i + 1)
            try:
                order_result = self.account_client.execute_order(
                    symbol=contract_id,
                    side=side,
                    order_type=OrderTypeEnum.LIMIT,
                    quantity=str(align_quantity),
                    price=str(self.round_to_tick(order_price)),
                    post_only=True,
                    time_in_force=TimeInForceEnum.GTC
                )

                if not order_result:
                    self.logger.info(
                        f'exception in place order, symbol: {contract_id}, '
                        f'quantity: {align_quantity}, order price: {order_price}')

                if 'code' in order_result:
                    message = order_result.get('message', 'Unknown error')
                    self.logger.warning(f"[OPEN] Error placing order: {message}")
                    continue

                order_id = order_result.get('id')
                orders.append(order_id)
                if not order_id:
                    self.logger.error(f"[OPEN] No order ID in response: {order_result}")
            except Exception as e:
                self.logger.info(f'exception in batch place orders: {e}')

        return orders

    async def batch_place_sell_limit_orders(
            self, contract_id: str, quantity: Decimal,
            order_num: int, position_rate: float):

        align_quantity = BackpackClient.align_floor(quantity, self.config.min_quantity)

        self.logger.info(
            f'batch place sell limit orders, contract id: {contract_id}, '
            f'min quantity: {self.config.min_quantity}, '
            f'quantity: {quantity:.4f}, '
            f'align quantity: {align_quantity}, '
            f'order num: {order_num}')
        order_book = self.public_client.get_depth(contract_id)
        if not isinstance(order_book, dict):
            return OrderResult(success=False, error_message='Unexpected order book response format')

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        orders = []

        side = 'Ask'
        base_multiple = self.config.base_multiple

        self.logger.info(
            f'place sell limit order, '
            f'position rate: {position_rate}, '
            f'base multiple: {base_multiple}')

        basic_ask = asks[0][0]
        base = base_multiple * (Decimal(asks[0][0]) - Decimal(bids[-1][0]))
        for i in range(order_num):
            order_price = Decimal(basic_ask) + base * (i + 1)
            try:
                order_result = self.account_client.execute_order(
                    symbol=contract_id,
                    side=side,
                    order_type=OrderTypeEnum.LIMIT,
                    quantity=str(align_quantity),
                    price=str(self.round_to_tick(order_price)),
                    post_only=True,
                    time_in_force=TimeInForceEnum.GTC
                )

                if not order_result:
                    self.logger.info(
                        f'exception in place order, symbol: {contract_id}, '
                        f'quantity: {align_quantity}, order price: {order_price}')
                    continue

                if 'code' in order_result:
                    message = order_result.get('message', 'Unknown error')
                    self.logger.warning(f"[OPEN] Error placing order: {message}")
                    continue

                order_id = order_result.get('id')
                orders.append(order_id)
                if not order_id:
                    self.logger.error(f"[OPEN] No order ID in response: {order_result}")
            except Exception as e:
                self.logger.warning(f'exception in batch place orders: {e}')

        return orders

    async def cancel_order(self, order_id: str) -> OrderResult:
        try:
            # Cancel the order using Backpack SDK
            cancel_result = self.account_client.cancel_order(
                symbol=self.config.contract_id,
                order_id=order_id
            )

            if not cancel_result:
                return OrderResult(success=False, error_message='Failed to cancel order')
            if 'code' in cancel_result:
                self.logger.error(
                    f"[CLOSE] Failed to cancel order {order_id}: {cancel_result.get('message', 'Unknown error')}")
                filled_size = self.config.quantity
            else:
                filled_size = Decimal(cancel_result.get('executedQuantity', 0))
            return OrderResult(success=True, filled_size=filled_size)

        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def get_active_orders(self, contract_id: str) -> List[OrderInfo]:
        """Get active orders for a contract using official SDK."""
        try:
            # Get active orders using Backpack SDK
            active_orders = self.account_client.get_open_orders(symbol=contract_id)

            if not active_orders:
                return []

            # Return the orders list as OrderInfo objects
            order_list = active_orders if isinstance(active_orders, list) else active_orders.get('orders', [])
            orders = []

            for order in order_list:
                if isinstance(order, dict):
                    side = 'sell'
                    if order.get('side', '') == 'Bid':
                        side = 'buy'
                    elif order.get('side', '') == 'Ask':
                        side = 'sell'

                    orders.append(OrderInfo(
                        order_id=order.get('id', ''),
                        side=side,
                        size=Decimal(order.get('quantity', 0)),
                        price=Decimal(order.get('price', 0)),
                        status=order.get('status', ''),
                        filled_size=Decimal(order.get('executedQuantity', 0)),
                        remaining_size=Decimal(order.get('quantity', 0)) - Decimal(order.get('executedQuantity', 0))
                    ))

            return orders

        except Exception:
            return []

    async def get_account_all_positions(self) -> List[Dict]:
        account_positions = []
        try:
            positions_data = self.account_client.get_open_positions()
            for position in positions_data:
                account_positions.append({
                    'symbol': position.get('symbol', ''),
                    'netQuantity': Decimal(position.get('netQuantity', 0))
                })
        except Exception as e:
            self.logger.info(f'exception in get account all positions: {e}')

        return account_positions

    async def get_account_positions(self) -> Decimal:
        try:
            positions_data = self.account_client.get_open_positions()
            position_amt = 0
            for position in positions_data:
                if position.get('symbol', '') == self.config.contract_id:
                    position_amt = abs(Decimal(position.get('netQuantity', 0)))
                    break
            return position_amt
        except Exception as e:
            self.logger.warning(f'exception in get account positions: {e}')
            return Decimal(0)

    async def get_contract_attributes(self) -> Tuple[str, Decimal, Decimal]:
        """Get contract ID for a ticker."""
        ticker = self.config.ticker
        if len(ticker) == 0:
            self.logger.error("Ticker is empty")
            raise ValueError("Ticker is empty")

        markets = self.public_client.get_markets()

        min_quantity = 0
        for market in markets:
            if (market.get('marketType', '') == 'PERP' and market.get('baseSymbol', '') == ticker and
                    market.get('quoteSymbol', '') == 'USDC'):
                self.logger.info(f'get contract attributes, ticker: {ticker}, market: {market}')
                self.config.contract_id = market.get('symbol', '')
                min_quantity = Decimal(market.get('filters', {}).get('quantity', {}).get('minQuantity', 0))
                self.config.tick_size = Decimal(market.get('filters', {}).get('price', {}).get('tickSize', 0))
                self.config.min_quantity = min_quantity
                break

        if self.config.contract_id == '':
            self.logger.error("Failed to get contract ID for ticker")
            raise ValueError("Failed to get contract ID for ticker")

        if self.config.quantity < min_quantity:
            self.logger.error(f"Order quantity is less than min quantity: {self.config.quantity} < {min_quantity}")
            raise ValueError(f"Order quantity is less than min quantity: {self.config.quantity} < {min_quantity}")

        if self.config.tick_size == 0:
            self.logger.error("Failed to get tick size for ticker")
            raise ValueError("Failed to get tick size for ticker")

        return self.config.contract_id, self.config.tick_size, self.config.min_quantity
