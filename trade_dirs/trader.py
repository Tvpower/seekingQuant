from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading


class IBKR_API(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        self.current_price = None
        self.price_received = False

    def error(self, reqId, errorCode, errorString):
        super().error(reqId, errorCode, errorString)
        print(f"Error: {reqId}, {errorCode}, {errorString}")

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextOrderId = orderId
        print(f"Next valid order ID: {orderId}")
    
    def tickPrice(self, reqId, tickType, price, attrib):
        """Callback for receiving price data"""
        if tickType == 4:  # Last price
            self.current_price = price
            self.price_received = True

    def place_dollar_order(self, symbol, action, amount):
        """Places an order for a specific dollar amount."""
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
        self.price_received = False
        self.reqMktData(self.nextOrderId, contract, "", False, False, [])
        
        # Wait for price data
        import time
        timeout = 0
        while not self.price_received and timeout < 50:  # 5 second timeout
            time.sleep(0.1)
            timeout += 1
        
        self.cancelMktData(self.nextOrderId)
        
        if not self.price_received or self.current_price is None:
            print(f"Could not get price for {symbol}, skipping order")
            return
        
        # Calculate quantity based on dollar amount
        quantity = int(amount / self.current_price)
        if quantity == 0:
            print(f"Calculated quantity is 0 for {symbol} (price: ${self.current_price:.2f}), skipping order")
            return

        order = Order()
        order.action = action
        order.orderType = "MKT"  # Market order
        order.totalQuantity = quantity

        self.placeOrder(self.nextOrderId, contract, order)
        print(f"Placed {action} order for {quantity} shares (${quantity * self.current_price:.2f}) of {symbol}")
        self.nextOrderId += 1


def run_loop(app):
    app.run()