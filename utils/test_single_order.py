import sys
import threading
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from trade_dirs.trader import IBKR_API, run_loop

# --- Configuration ---


def test_single_order():
    """Test placing an overnight order."""
    print("--- Testing Overnight Market Order ---")
    print("Current time: Sunday ~9:00 PM ET (overnight session)")

    try:
        app = IBKR_API()
        app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))

        api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
        api_thread.start()

        time.sleep(3)  # Wait for connection and market data type setup

        # Test with AAPL - $500 to ensure we get at least 1 share
        print("\nPlacing overnight test order for $500 of AAPL...")
        app.place_dollar_order("AMD", "BUY", 500, use_market=False)

        print("\nWaiting for order to process...")
        time.sleep(10)

        app.disconnect()
        print("\n--- Test Complete ---")
        print("Check IBKR TWS Activity Monitor > Orders tab for the AAPL order")
        print("Order should show as 'PreSubmitted' or 'Submitted' for overnight execution")

    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_single_order()
