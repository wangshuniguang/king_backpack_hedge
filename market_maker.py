#!/usr/bin/env python

import asyncio
import time
import traceback
from decimal import Decimal

from exchanges.backpack_client import BackpackClient
from model.trading_config import TradingConfig
from config.config import backpack_public_key, backpack_secret_key
from helpers.logger import setup_logger

logger = setup_logger('market_maker')


class MarketMaker:
    """Modular Trading Bot - Main trading logic supporting multiple exchanges."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logger

        # Create exchange client
        try:
            self.exchange_client = BackpackClient(config)
        except ValueError as e:
            raise ValueError(f"Failed to create exchange client: {e}")

        # Trading state
        self.active_close_orders = []
        self.all_limit_orders = []
        self.last_log_time = 0

    async def _log_status_periodically(self):
        """Log status information periodically, including positions."""
        if time.time() - self.last_log_time > 60 or self.last_log_time == 0:
            print("--------------------------------")
            try:
                # Get active orders
                active_orders = await self.exchange_client.get_active_orders(self.config.contract_id)

                # Filter close orders
                self.active_close_orders = []
                for order in active_orders:
                    if order.side == self.config.close_order_side:
                        self.active_close_orders.append({
                            'id': order.order_id,
                            'price': order.price,
                            'size': order.size
                        })

                # Get positions
                position_amt = await self.exchange_client.get_account_positions()

                # Calculate active closing amount
                active_close_amount = sum(
                    Decimal(order.get('size', 0))
                    for order in self.active_close_orders
                    if isinstance(order, dict)
                )

                self.logger.info(f"Current Position: {position_amt} | Active closing amount: {active_close_amount}")
            except Exception as e:
                self.logger.error(
                    f"Error in periodic status check: {e}, "
                    f"Traceback: {traceback.format_exc()}")

    async def close_all_orders(self):
        # Get active orders
        active_orders = await self.exchange_client.get_active_orders(self.config.contract_id)

        # Filter close orders
        self.active_close_orders = []
        for order in active_orders:
            self.active_close_orders.append({
                'id': order.order_id,
                'price': order.price,
                'size': order.size
            })

        self.logger.info(
            f'start to close all active orders, active orders count: {len(self.active_close_orders)}, '
            f'active orders: {self.active_close_orders}')

        for i in range(len(self.active_close_orders)):
            try:
                order_id = self.active_close_orders[i].get('id')
                cancel_order_result = await self.exchange_client.cancel_order(order_id)
                self.logger.info(f'cancel order: {order_id}, cancel order result: {cancel_order_result}')
            except Exception as e:
                self.logger.warning(f'exception in cancel order: {e}')

    async def close_all_limit_orders(self):
        # Get active orders
        self.logger.info(
            f'start to close all active orders, active orders count: {len(self.all_limit_orders)}, '
            f'active orders: {self.all_limit_orders}')

        for i in range(len(self.all_limit_orders)):
            try:
                order_id = self.all_limit_orders[i].get('id')
                cancel_order_result = await self.exchange_client.cancel_order(order_id)
                self.logger.info(f'cancel order: {order_id}, cancel order result: {cancel_order_result}')
            except Exception as e:
                self.logger.warning(f'exception in cancel order: {e}')

        self.all_limit_orders = []

    async def run(self):
        """Main trading loop."""
        try:
            (self.config.contract_id, self.config.tick_size,
             self.config.min_quantity) = await self.exchange_client.get_contract_attributes()

            max_position_count = self.config.max_position_count

            while True:
                try:
                    await self.close_all_orders()

                    curr_contract_amount = 0
                    all_positions = await self.exchange_client.get_account_all_positions()
                    for i in range(len(all_positions)):
                        if all_positions[i]['symbol'] == self.config.contract_id:
                            curr_contract_amount = all_positions[i]['netQuantity']
                            break

                    position_rate = round(curr_contract_amount / max_position_count, 2)

                    await self._log_status_periodically()

                    if abs(curr_contract_amount) < max_position_count:
                        await self.exchange_client.batch_place_buy_limit_orders(
                            contract_id=self.config.contract_id,
                            quantity=self.config.quantity,
                            order_num=self.config.max_orders,
                            position_rate=position_rate
                        )

                        await self.exchange_client.batch_place_sell_limit_orders(
                            contract_id=self.config.contract_id,
                            quantity=self.config.quantity,
                            order_num=self.config.max_orders,
                            position_rate=position_rate

                        )
                    elif curr_contract_amount >= max_position_count:
                        self.logger.info(
                            f'curr contract amount: {curr_contract_amount}, '
                            f'only sell it.')
                        await self.exchange_client.batch_place_sell_limit_orders(
                            contract_id=self.config.contract_id,
                            quantity=self.config.quantity,
                            order_num=self.config.max_orders,
                            position_rate=position_rate
                        )
                    else:
                        self.logger.info(
                            f'curr contract amount: {curr_contract_amount}, '
                            f'only buy it.')
                        await self.exchange_client.batch_place_buy_limit_orders(
                            contract_id=self.config.contract_id,
                            quantity=self.config.quantity,
                            order_num=self.config.max_orders,
                            position_rate=position_rate
                        )

                    await asyncio.sleep(self.config.wait_time)
                except Exception as e:
                    self.logger.warning(f"exception in process: {e}")
        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"Critical error: {e}")
            await self.close_all_orders()
        finally:
            try:
                await self.close_all_orders()
            except Exception as e:
                self.logger.error(f"Error disconnecting from exchange: {e}")


async def main():
    config = TradingConfig(
        ticker='ETH',
        contract_id='',  # will be set in the run method
        min_quantity=Decimal(0),  # will be set in the run method
        tick_size=Decimal(0),
        quantity=Decimal(0.01),
        max_position_count=Decimal(0.1),
        take_profit=Decimal(0),
        direction='buy',
        max_orders=1,
        wait_time=2.95,
        exchange='backpack',
        base_multiple=2,
        public_key=backpack_public_key,
        secret_key=backpack_secret_key
    )

    # Create and run the bot
    maker = MarketMaker(config)
    try:
        await maker.run()
    except Exception as e:
        print(f"Bot execution failed: {e}")
        # The bot's run method already handles graceful shutdown
        return


if __name__ == "__main__":
    asyncio.run(main())
