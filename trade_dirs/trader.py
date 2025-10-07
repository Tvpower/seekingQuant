from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading
import time


class IBKR_API(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        self.current_price = None
        self.price_received = False
        self.close_price = None  # For fallback
        self.positions = {}  # Store positions data
        self.positions_received = False
        self.accounts = []  # Store available accounts
        self.accounts_received = False
        self.position_prices = {}  # Store current prices for positions
        self.pending_price_requests = 0  # Track pending price requests

    def error(self, reqId, errorCode, errorString):
        # Filter out informational messages (2104, 2106, 2158 are connection status messages)
        if errorCode not in [2104, 2106, 2158]:
            super().error(reqId, errorCode, errorString)
            print(f"Error: {reqId}, {errorCode}, {errorString}")

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextOrderId = orderId
        print(f"Next valid order ID: {orderId}")

        # Enable real-time market data (Type 1)
        self.reqMarketDataType(1)  # Real-time
        print("Enabled real-time market data")

    def tickPrice(self, reqId, tickType, price, attrib):
        """Callback for receiving price data"""
        # Check if this is a position price request
        if reqId >= 10000:  # Position price requests use IDs >= 10000
            symbol_idx = reqId - 10000
            symbols = list(self.positions.keys())
            if symbol_idx < len(symbols):
                symbol = symbols[symbol_idx]
                if tickType == 4:  # Last price
                    self.position_prices[symbol] = price
                    self.pending_price_requests -= 1
                    print(f"{symbol}: Current price ${price:.2f}")
                    self.cancelMktData(reqId)
                elif tickType == 9 and symbol not in self.position_prices:  # Close price fallback
                    self.position_prices[symbol] = price
                    self.pending_price_requests -= 1
                    print(f"{symbol}: Using close price ${price:.2f}")
                    self.cancelMktData(reqId)
        else:
            # Regular price request for orders
            if tickType == 4:  # Last price (real-time)
                self.current_price = price
                self.price_received = True
                print(f"Received real-time price: ${price:.2f}")
            elif tickType == 9:  # Close price (fallback)
                self.close_price = price
                # Only print if we don't have real-time price yet
                if not self.price_received:
                    print(f"Received close price: ${price:.2f}")
            elif tickType == 68:  # Delayed last price
                if self.current_price is None:  # Only use if no real-time available
                    self.current_price = price
                    self.price_received = True
                    print(f"Received delayed price: ${price:.2f}")

    def position(self, account, contract, position, avgCost):
        """Callback for receiving position data"""
        # Filter by account if specified
        if hasattr(self, 'filter_account') and self.filter_account and account != self.filter_account:
            return
            
        if contract.secType == "STK":  # Only track stocks
            symbol = contract.symbol
            # Store position data temporarily - will update with market value later
            self.positions[symbol] = {
                'account': account,
                'position': position,
                'avg_cost': avgCost,
                'market_value': 0,  # Will be updated with current price
                'contract': contract  # Store contract for price request
            }
            print(f"Position: {symbol} - Quantity: {position}, Avg Cost: ${avgCost:.2f}")

    def positionEnd(self):
        """Called when all positions have been received"""
        # Now fetch current prices for all positions
        print(f"All positions received. Total stocks: {len(self.positions)}")
        print("Fetching current market prices...")
        self.fetch_position_prices()
    
    def fetch_position_prices(self):
        """Fetch current market prices for all positions"""
        symbols = list(self.positions.keys())
        for idx, symbol in enumerate(symbols):
            data = self.positions[symbol]
            if 'contract' in data:
                req_id = 10000 + idx  # Use IDs >= 10000 for position prices
                self.pending_price_requests += 1
                self.reqMktData(req_id, data['contract'], "", False, False, [])
                time.sleep(0.1)  # Small delay between requests
        
        # Mark that we've received all positions
        self.positions_received = True

    def managedAccounts(self, accountsList):
        """Callback for receiving managed accounts list"""
        self.accounts = accountsList.split(',') if accountsList else []
        self.accounts_received = True
        print(f"Available accounts: {self.accounts}")

    def get_available_accounts(self):
        """Request and return list of available accounts"""
        self.accounts = []
        self.accounts_received = False
        print("Requesting available accounts...")
        self.reqManagedAccts()
        
        # Wait for accounts data
        timeout = 0
        while not self.accounts_received and timeout < 50:  # 5 second timeout
            time.sleep(0.1)
            timeout += 1
        
        return self.accounts

    def get_account_positions(self, account_id=""):
        """Request all positions for the account"""
        self.positions = {}
        self.positions_received = False
        self.position_prices = {}
        self.pending_price_requests = 0
        self.filter_account = account_id  # Set account filter
        print(f"Requesting account positions for: {account_id if account_id else 'Primary Account'}...")
        self.reqPositions()
        
        # Wait for positions data and price updates
        timeout = 0
        while (not self.positions_received or self.pending_price_requests > 0) and timeout < 200:  # 20 second timeout
            time.sleep(0.1)
            timeout += 1
        
        self.cancelPositions()
        
        # Update market values with fetched prices
        for symbol, data in self.positions.items():
            if symbol in self.position_prices:
                current_price = self.position_prices[symbol]
                data['market_value'] = data['position'] * current_price
                data['current_price'] = current_price
                print(f"{symbol}: {data['position']} shares @ ${current_price:.2f} = ${data['market_value']:.2f}")
            else:
                # Fallback to cost basis if price not available
                data['market_value'] = data['position'] * data['avg_cost']
                print(f"{symbol}: Using cost basis for market value")
        
        return self.positions

    def place_dollar_order(self, symbol, action, amount, use_market=False, whole_shares_only=False, account=""):
        """Places an order for a specific dollar amount.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            action: 'BUY' or 'SELL'
            amount: Dollar amount to trade
            use_market: If True, uses MKT order (RTH only). If False, uses LMT order with outsideRth
            whole_shares_only: If True, rounds down to whole shares (no fractional)
            account: Account ID to place order for (required for multiple accounts)
        """
        if self.nextOrderId is None:
            print("Waiting for next valid order ID...")
            return

        # Create a contract object for a US stock
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        # Request current market price
        self.current_price = None
        self.close_price = None
        self.price_received = False
        req_id = self.nextOrderId

        print(f"Requesting market price for {symbol}...")
        self.reqMktData(req_id, contract, "", False, False, [])

        # Wait for price data (longer timeout for overnight session)
        timeout = 0
        while not self.price_received and timeout < 100:  # 10 second timeout
            time.sleep(0.1)
            timeout += 1

        self.cancelMktData(req_id)

        # Use close price as fallback if no live price available
        if not self.price_received or self.current_price is None:
            if self.close_price is not None:
                print(f"Using Friday's close price: ${self.close_price:.2f}")
                self.current_price = self.close_price
            else:
                print(f"Could not get price for {symbol}, skipping order")
                return

        # Calculate quantity based on dollar amount
        if whole_shares_only:
            quantity = int(amount / self.current_price)  # Round down to whole shares
            if quantity < 1:
                print(f"Calculated quantity is less than 1 share for {symbol} (price: ${self.current_price:.2f}), skipping order")
                return
        else:
            quantity = round(amount / self.current_price, 8)  # Up to 8 decimal places
            if quantity < 0.000001:
                print(f"Calculated quantity is too small for {symbol} (price: ${self.current_price:.2f}), skipping order")
                return

        order = Order()
        order.action = action
        
        # Specify account if provided (required for multiple account setups)
        if account:
            order.account = account

        if use_market:
            # Market order - only works during RTH
            order.orderType = "MKT"
            order.tif = "DAY"
        else:
            # Limit order - works outside RTH (overnight/after-hours)
            order.orderType = "LMT"
            # Set competitive limit price for overnight session
            if action == "BUY":
                order.lmtPrice = round(self.current_price * 1.02, 2)  # 2% above for overnight
            else:
                order.lmtPrice = round(self.current_price * 0.98, 2)  # 2% below
            order.outsideRth = True  # Allow overnight/after-hours execution
            order.tif = "GTC"  # Good Till Cancelled

        order.totalQuantity = quantity  # Can be fractional

        # Fix for TWS 983+ deprecated attributes error
        order.eTradeOnly = False
        order.firmQuoteOnly = False

        self.placeOrder(self.nextOrderId, contract, order)

        if use_market:
            if whole_shares_only:
                print(f"Placed {action} MARKET order for {int(quantity)} shares (${quantity * self.current_price:.2f}) of {symbol}")
            else:
                print(f"Placed {action} MARKET order for {quantity:.6f} shares (${quantity * self.current_price:.2f}) of {symbol}")
        else:
            if whole_shares_only:
                print(f"Placed {action} LIMIT order for {int(quantity)} shares at ${order.lmtPrice:.2f} (total ~${quantity * order.lmtPrice:.2f}) of {symbol}")
            else:
                print(f"Placed {action} LIMIT order for {quantity:.6f} shares at ${order.lmtPrice:.2f} (total ~${quantity * order.lmtPrice:.2f}) of {symbol}")
            print(f"Order placed with limit price; outsideRth permitted")

        self.nextOrderId += 1


def run_loop(app):
    app.run()
