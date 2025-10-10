#!/usr/bin/env python

import asyncio
from decimal import Decimal

from exchanges.backpack_client import BackpackClient
from exchanges.lighter_client import LighterClient
from helpers.logger import setup_logger
from model.trading_config import TradingConfig
from config.config import backpack_public_key, backpack_secret_key

logger = setup_logger('king_of_hedge')
logger.info(f'init king of hedge.')


class KingOfHedge(object):
    def __init__(self):
        self.logger = logger

        config = TradingConfig(
            ticker='ETH',
            contract_id='',  # will be set in the bot's run method
            tick_size=Decimal(0),
            quantity=Decimal(0),
            take_profit=Decimal(0),
            max_position_count=Decimal(0),
            min_quantity=Decimal(0),
            base_multiple=2,
            direction='',
            max_orders=0,
            wait_time=0,
            exchange='backpack',
            public_key=backpack_public_key,
            secret_key=backpack_secret_key
        )

        self.backpack_client = BackpackClient(config)
        self.lighter_client = LighterClient()

    async def hedge_with_lighter(self, symbol, quantity):
        lighter_symbol = symbol
        if symbol.find('_') >= 0:
            lighter_symbol = symbol.split('_')[0]

        if quantity < 0:
            await self.lighter_client.place_buy_market_order(lighter_symbol, quantity)

    @staticmethod
    def get_unified_symbol(symbol, platform):
        if platform == 'backpack' or platform == 'edgex':
            res = symbol.split('_')[0].upper()
            if res.find('USDT') >= 0:
                res = res.replace('USDT', '')
            elif res.find('USD') >= 0:
                res = res.replace('USD', '')

            return res

        return symbol

    async def get_need_hedge_positions(self):
        backpack_positions = await self.backpack_client.get_account_all_positions()
        lighter_positions = await self.lighter_client.get_positions()

        self.logger.info(
            f'backpack positions: {backpack_positions}, '
            f'lighter positions: {lighter_positions}')

        need_hedge_positions = []
        for i in range(len(backpack_positions)):
            position = backpack_positions[i]
            symbol = position.get('symbol')
            bp_unified_symbol = KingOfHedge.get_unified_symbol(symbol, 'backpack')
            quantity = position.get('netQuantity')
            self.logger.info(f'symbol: {symbol}, quantity: {quantity}')

            lighter_quantity = 0
            is_found = False
            for j in range(len(lighter_positions)):
                lg_symbol = lighter_positions[j].get('symbol')
                position = float(lighter_positions[j].get('position'))
                sign = lighter_positions[j].get('sign')
                lighter_unified_symbol = KingOfHedge.get_unified_symbol(lg_symbol, 'lighter')

                if abs(position) == 0:
                    continue

                if lighter_unified_symbol == bp_unified_symbol:
                    is_found = True
                    lighter_quantity = position * sign
                    break

            need_hedge_quantity = -float(quantity) - float(lighter_quantity)
            need_hedge_positions.append({
                'symbol': bp_unified_symbol,
                'quantity': need_hedge_quantity
            })

        for j in range(len(lighter_positions)):
            lg_symbol = lighter_positions[j].get('symbol')
            position = float(lighter_positions[j].get('position'))
            sign = lighter_positions[j].get('sign')
            lighter_unified_symbol = KingOfHedge.get_unified_symbol(lg_symbol, 'lighter')
            lighter_quantity = float(position * sign)

            if abs(lighter_quantity) == 0:
                continue

            is_found = False
            for i in range(len(backpack_positions)):
                position = backpack_positions[i]
                symbol = position.get('symbol')
                bp_unified_symbol = KingOfHedge.get_unified_symbol(symbol, 'backpack')
                quantity = position.get('netQuantity')
                self.logger.info(f'symbol: {symbol}, quantity: {quantity}')

                if lighter_unified_symbol == bp_unified_symbol:
                    is_found = True
                    break

            if not is_found:
                need_hedge_positions.append({
                    'symbol': lg_symbol,
                    'quantity': -float(lighter_quantity)
                })

        return need_hedge_positions

    async def do_hedges(self, need_hedge_positions):
        for i in range(len(need_hedge_positions)):
            try:
                symbol = need_hedge_positions[i]['symbol']
                quantity = need_hedge_positions[i]['quantity']
                if quantity >= 0.001:
                    await self.lighter_client.place_buy_market_order(symbol, abs(quantity))
                elif quantity <= -0.001:
                    await self.lighter_client.place_sell_market_order(symbol, abs(quantity))
            except Exception as e:
                self.logger.info(f'exception in do hedges: {e}')

    async def run(self):
        while True:
            try:
                need_hedge_positions = await self.get_need_hedge_positions()
                self.logger.info(f'need hedge positions: {need_hedge_positions}')
                await self.do_hedges(need_hedge_positions)
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.info(f'exception in run: {e}')


async def main():
    # Create and run the bot
    bot = KingOfHedge()
    try:
        await bot.run()
    except Exception as e:
        print(f"Bot execution failed: {e}")
        # The bot's run method already handles graceful shutdown
        return


if __name__ == "__main__":
    asyncio.run(main())
