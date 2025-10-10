#!/usr/bin/env python

import time

import lighter
import pandas as pd

from config.config import lighter_api_key_index, lighter_private_key, lighter_account_index

from helpers.logger import setup_logger

logger = setup_logger('lighter_client')


class LighterClient(object):
    def __init__(self):
        self.url = 'https://mainnet.zklighter.elliot.ai'
        self.api_key_index = lighter_api_key_index
        self.private_key = lighter_private_key
        self.account_index = lighter_account_index
        self.environment = 'Mainnet'
        self.auth_token = None
        self.token_expiry_time = None

        self.logger = logger
        self.signer_client = lighter.SignerClient(
            url=self.url,
            private_key=self.private_key,
            account_index=self.account_index,
            api_key_index=self.api_key_index,
        )

        configuration = lighter.Configuration(
            host="https://mainnet.zklighter.elliot.ai"
        )
        api_client = lighter.ApiClient(configuration)
        self.account_api = lighter.AccountApi(api_client)
        self.order_api = lighter.OrderApi(api_client)

        self.account_total_asset_value = 0
        self.order_book_df = pd.DataFrame()
        self.market_ids = []

    @staticmethod
    def symbol_name(symbol):
        if symbol.find('USDT') >= 0:
            symbol = symbol.replace('USDT', '')
        elif symbol.find('USDC') >= 0:
            symbol = symbol.repace('USDC', '')

        return symbol.upper()

    async def to_lighter_amount(self, symbol, basic_amount):
        if self.order_book_df.shape[0] == 0:
            await self.get_order_book_details()

        new_symbol = LighterClient.symbol_name(symbol)
        tmp_df = self.order_book_df.loc[self.order_book_df.symbol == new_symbol].copy()
        if tmp_df.shape[0] == 0:
            self.logger.info(f'symbol is not found: {new_symbol}, is not supported!')
            return 0

        tmp_df.reset_index(drop=True, inplace=True)
        amount = basic_amount
        if amount < tmp_df.loc[0, 'min_base_amount']:
            amount = tmp_df.loc[0, 'min_base_amount']
            self.logger.info(
                f'amount is less than min base amount, amount: {amount}, '
                f'min base amount: {tmp_df.loc[0, "min_base_amount"]}')

        lighter_amount = 10 ** tmp_df.loc[0, 'size_decimals'] * amount
        self.logger.info(
            f'to lighter amount, symbol: {symbol}, new symbol: {new_symbol}, '
            f'basic_amount: {basic_amount}, amount: {amount}, lighter amount: {lighter_amount}')

        return lighter_amount

    async def get_symbol_market_id(self, symbol):
        if self.order_book_df.shape[0] == 0:
            await self.get_order_book_details()

        new_symbol = LighterClient.symbol_name(symbol)
        tmp_df = self.order_book_df.loc[self.order_book_df.symbol == new_symbol].copy()
        if tmp_df.shape[0] == 0:
            self.logger.info(f'symbol is not found: {new_symbol}, is not supported!')
            return -1

        tmp_df.reset_index(drop=True, inplace=True)

        return int(tmp_df.loc[0, 'market_id'])

    async def get_active_orders(self):
        all_orders = []
        for market_id in self.market_ids:
            try:
                api_response = await self.order_api.account_active_orders(
                    account_index=self.account_index,
                    authorization=self.auth_token,
                    auth=self.auth_token,
                    market_id=market_id
                )
                orders = api_response.orders
                all_orders.extend(orders)
                print(f"The response of OrderApi->account_active_orders:\nmarket_id: {market_id}, orders: {orders}")
            except Exception as e:
                print("Exception when calling OrderApi->account_active_orders: %s\n" % e)

        return all_orders

    async def place_buy_market_order(self, symbol, amount):
        market_index = await self.get_symbol_market_id(symbol)
        lighter_amount = await self.to_lighter_amount(symbol, amount)
        lighter_amount = int(lighter_amount)

        self.logger.info(
            f'place buy market order, symbol: {symbol}, amount: {amount}, '
            f'market index: {market_index}, lighter amount: {lighter_amount}')

        if market_index == -1:
            raise Exception(f'invalid market index: {market_index}, symbol: {symbol}')

        elif lighter_amount == 0:
            raise Exception(f'invalid lighter amount: {lighter_amount}')

        order, _, _ = await self.signer_client.create_market_order_limited_slippage(
            market_index=market_index,
            client_order_index=0,
            base_amount=int(lighter_amount),
            max_slippage=0.1,
            is_ask=False,
        )

        self.logger.info(f'new created order: {order}')

        return order

    async def get_positions(self):
        positions = []
        try:
            # account
            api_response = await self.account_api.account('index', str(self.account_index))
            tmp_positions = api_response.accounts[0].positions
            for i in range(len(tmp_positions)):
                curr_position = tmp_positions[i]
                positions.append({
                    'market_id': curr_position.market_id,
                    'symbol': curr_position.symbol,
                    'open_order_count': curr_position.open_order_count,
                    'pending_order_count': curr_position.pending_order_count,
                    'position_tied_order_count': curr_position.position_tied_order_count,
                    # 此处position是按照真实的position来的。比如，0.01 ETH此处取值就是0.01
                    'position': float(curr_position.position),
                    # sign取值, -1表示做空，1表示做多
                    'sign': curr_position.sign
                })
        except Exception as e:
            print("Exception when calling AccountApi->account: %s\n" % e)

        return positions

    async def place_sell_market_order(self, symbol, amount):
        market_index = await self.get_symbol_market_id(symbol)
        lighter_amount = await self.to_lighter_amount(symbol, amount)
        lighter_amount = int(lighter_amount)

        self.logger.info(
            f'place sell market order, symbol: {symbol}, amount: {amount}, '
            f'market index: {market_index}, lighter amount: {lighter_amount}')

        if market_index == -1:
            raise Exception(f'invalid market index: {market_index}, symbol: {symbol}')

        elif lighter_amount == 0:
            raise Exception(f'invalid lighter amount: {lighter_amount}')

        order, _, _ = await self.signer_client.create_market_order_limited_slippage(
            market_index=market_index,
            client_order_index=0,
            base_amount=int(lighter_amount),
            max_slippage=0.1,
            is_ask=True,
        )

        self.logger.info(f'new created order: {order}')

        return order

    async def get_order_book_details(self):
        df = pd.DataFrame(columns=[
            'symbol', 'market_id', 'status',
            'size_decimals',
            'min_quote_amount',
            'min_base_amount',
            'price_decimals'
        ])

        try:
            # OrderBookDetail(symbol='ETH', market_id=0, status='active', taker_fee='0.0000',
            # maker_fee='0.0000', liquidation_fee='1.0000', min_base_amount='0.0050',
            # min_quote_amount='10.000000', supported_size_decimals=4, supported_price_decimals=2,
            # supported_quote_decimals=6, size_decimals=4, price_decimals=2,
            # quote_multiplier=1, default_initial_margin_fraction=500,
            # min_initial_margin_fraction=200, maintenance_margin_fraction=120,
            # closeout_margin_fraction=80, last_trade_price=4008.19, daily_trades_count=592193,
            # daily_base_token_volume=251879.9602, daily_quote_token_volume=1008932349.808162,
            # daily_price_low=3969.23, daily_price_high=4038, daily_price_change=0.6394741599212646,
            # open_interest=34749.8475, daily_chart={}
            api_response = await self.order_api.order_book_details()
            print("The response of OrderApi->order_book_details:\n")
            order_book_details = api_response.order_book_details
            for i in range(len(order_book_details)):
                order_book_detail = order_book_details[i]
                df.loc[df.shape[0]] = [
                    order_book_detail.symbol,
                    order_book_detail.market_id,
                    order_book_detail.status,
                    order_book_detail.size_decimals,
                    float(order_book_detail.min_quote_amount),
                    float(order_book_detail.min_base_amount),
                    order_book_detail.price_decimals
                ]

            self.order_book_df = df.copy()
            df.to_csv('order_book.csv', index=False)
        except Exception as e:
            print("Exception when calling OrderApi->order_book_details: %s\n" % e)

    async def get_account(self):
        try:
            # account
            api_response = await self.account_api.account('index', str(self.account_index))
            accounts = api_response.accounts
            if len(accounts) > 0:
                self.account_total_asset_value = accounts[0].total_asset_value

            self.logger.info(
                f"The response of AccountApi->account:\n{api_response}, "
                f"account total asset value: {self.account_total_asset_value}")
        except Exception as e:
            print("Exception when calling AccountApi->account: %s\n" % e)

        return self.account_total_asset_value

    async def check_and_refresh_auth_token(self):
        curr_time = int(time.time())
        if self.token_expiry_time is None or curr_time >= self.token_expiry_time:
            try:
                await self.refresh_auth_token()
            except Exception as e:
                self.logger.info(f'exception in check and refresh auth token: {e}')

    async def refresh_auth_token(self):
        try:
            err = self.signer_client.check_client()
            if err is not None:
                self.logger.info(f"Error: Failed to verify client configuration - {err}")
                return

            auth_token, err = self.signer_client.create_auth_token_with_expiry(
                lighter.SignerClient.DEFAULT_10_MIN_AUTH_EXPIRY)

            if err is not None:
                self.logger.info(f"Error: Failed to create auth token - {err}")
                return

            expiry_time = int(time.time() + 8 * 60)
            expiry_readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expiry_time))

            self.auth_token = auth_token
            self.token_expiry_time = expiry_time

            self.logger.info(
                'Auth Token Successfully Created！Token: {auth_token}, '
                'Expires at: {expiry_readable} (in 10 minutes), '
                f'expiry readable: {expiry_readable}')
        except Exception as e:
            self.logger.info(f"Error: {str(e)}")
