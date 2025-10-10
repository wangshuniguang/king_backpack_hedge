#!/usr/bin/env python


import os
import asyncio
import json
import time
import base64
from typing import Dict, Any, List, Optional, Tuple
import sys
import websockets

from cryptography.hazmat.primitives.asymmetric import ed25519

from helpers.logger import setup_logger

logger = setup_logger('bp_ws_manager')


class BackpackWebSocketManager:
    """WebSocket manager for Backpack order updates."""

    def __init__(self, public_key: str, secret_key: str, symbol: str, order_update_callback):
        self.public_key = public_key
        self.secret_key = secret_key
        self.symbol = symbol
        self.order_update_callback = order_update_callback
        self.websocket = None
        self.running = False
        self.ws_url = "wss://ws.backpack.exchange"
        self.logger = logger

        # Initialize ED25519 private key from base64 decoded secret
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(secret_key)
        )

    def _generate_signature(self, instruction: str, timestamp: int, window: int = 5000) -> str:
        """Generate ED25519 signature for WebSocket authentication."""
        # Create the message string in the same format as BPX package
        message = f"instruction={instruction}&timestamp={timestamp}&window={window}"

        # Sign the message using ED25519 private key
        signature_bytes = self.private_key.sign(message.encode())

        # Return base64 encoded signature
        return base64.b64encode(signature_bytes).decode()

    async def connect(self):
        """Connect to Backpack WebSocket."""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.running = True

            # Subscribe to order updates for the specific symbol
            timestamp = int(time.time() * 1000)
            signature = self._generate_signature("subscribe", timestamp)

            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": [f"account.orderUpdate.{self.symbol}"],
                "signature": [
                    self.public_key,
                    signature,
                    str(timestamp),
                    "5000"
                ]
            }

            await self.websocket.send(json.dumps(subscribe_message))
            if self.logger:
                self.logger.info(f"Subscribed to order updates for {self.symbol}")

            # Start listening for messages
            await self._listen()

        except Exception as e:
            if self.logger:
                self.logger.error(f"WebSocket connection error: {e}")
            raise

    async def _listen(self):
        """Listen for WebSocket messages."""
        try:
            async for message in self.websocket:
                if not self.running:
                    break

                try:
                    data = json.loads(message)
                    self.logger.info(f'listen data: {data}')
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    if self.logger:
                        self.logger.error(f"Failed to parse WebSocket message: {e}")
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Error handling WebSocket message: {e}")

        except websockets.exceptions.ConnectionClosed:
            if self.logger:
                self.logger.warning("WebSocket connection closed")
        except Exception as e:
            if self.logger:
                self.logger.error(f"WebSocket listen error: {e}")

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket messages."""
        try:
            stream = data.get('stream', '')
            payload = data.get('data', {})

            self.logger.info(f'handle message, stream: {stream}, payload: {payload}')

            if 'orderUpdate' in stream:
                await self._handle_order_update(payload)
            else:
                self.logger.error(f"Unknown WebSocket message: {data}")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling WebSocket message: {e}")

    async def _handle_order_update(self, order_data: Dict[str, Any]):
        """Handle order update messages."""
        try:
            # Call the order update callback if it exists
            if hasattr(self, 'order_update_callback') and self.order_update_callback:
                await self.order_update_callback(order_data)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error handling order update: {e}")

    async def disconnect(self):
        """Disconnect from WebSocket."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            if self.logger:
                self.logger.info("WebSocket disconnected")

    def set_logger(self, logger):
        """Set the logger instance."""
        self.logger = logger
