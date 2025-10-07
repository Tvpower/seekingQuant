import sys
import threading
import time
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# sys.path adjusted: use packages
# sys.path adjusted: use packages

# Import from other project files
from seeking_alpha_scrape.scraper import get_portfolio_data_automated, scrape_portfolio_data, test_html_parsing
from trade_dirs.trader import IBKR_API, run_loop


# --- Configuration ---

def run_trading_session(portfolio_df):
    """Connects to IBKR and executes trades based on the portfolio DataFrame."""
    print("\n--- Starting Trading Session ---")
    try:
        app = IBKR_API()
        app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))

        api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
        api_thread.start()

        time.sleep(2) # Wait for connection and nextOrderId

        for _, row in portfolio_df.iterrows():
            symbol = row['Symbol']
            action = row['Action']

            if action.upper() in ["BUY", "SELL"]:
                app.place_dollar_order(symbol, action.upper(), int(os.getenv('TRADE_AMOUNT')))
                time.sleep(1) # Small delay between placing orders

        print("\nWaiting for orders to process...")
        time.sleep(5)
        app.disconnect()
        print("--- Trading Session Finished ---")

    except Exception as e:
        print(f"An error occurred during the trading session: {e}")


def main():
    """Main function to orchestrate the scraping and trading process."""
    # Handle the test argument
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("--- Running Scraper in Test Mode ---")
        test_html_parsing()
        return

    # Determine scrape type based on arguments
    scrape_type = 'latest_history'  # Default: scrape latest movements for trading
    if "--all" in sys.argv:
        scrape_type = 'all_history'
    elif "--current" in sys.argv:
        scrape_type = 'current_picks'

    try:
        # Step 1: Scrape portfolio data (with visible browser to avoid bot detection)
        print(f"--- Scraping Portfolio Data ({scrape_type}) ---")
        portfolio_data = get_portfolio_data_automated(scrape_type=scrape_type, headless=False)

        # Step 2: If scraping is successful, run the trading logic
        if portfolio_data:
            df = pd.DataFrame(portfolio_data)
            print("\n--- Scraped Portfolio Data ---")
            print(df.to_string())
            run_trading_session(df)
        else:
            print("\nScraping did not return any data. Trading session will not start.")

    except Exception as e:
        print(f"An error occurred in the main process: {e}")


if __name__ == "__main__":
    main()