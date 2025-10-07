import sys
import threading
import time
import pandas as pd
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from seeking_alpha_scrape.scraper import get_portfolio_data_automated
from trade_dirs.trader import IBKR_API, run_loop


# --- Configuration ---


def buy_entire_portfolio(portfolio_df, dollar_amount):
    """Connects to IBKR and buys specified dollar amount of all stocks in portfolio."""
    print("\n--- Starting Portfolio Purchase Session ---")
    print(f"Buying ${dollar_amount} worth of each stock in portfolio\n")
    
    try:
        app = IBKR_API()
        app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))

        api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
        api_thread.start()

        time.sleep(3)  # Wait for connection and market data setup

        for _, row in portfolio_df.iterrows():
            symbol = row['symbol']
            # Use the trader's place_dollar_order method (fetches price and calculates shares)
            app.place_dollar_order(symbol, "BUY", dollar_amount, use_market=True, whole_shares_only=True)
            time.sleep(1)  # Small delay between placing orders

        print("\nWaiting for orders to process...")
        time.sleep(5)
        app.disconnect()
        print("--- Portfolio Purchase Session Finished ---")

    except Exception as e:
        print(f"An error occurred during the trading session: {e}")


def main():
    """Main function to extract portfolio stocks and place buy orders."""
    
    try:
        # Step 1: Scrape current portfolio picks
        print("--- Scraping Current Portfolio Picks ---")
        portfolio_data = get_portfolio_data_automated(scrape_type='current_picks', headless=False)
        
        # If we got portfolio history instead of current picks, extract symbols from the data
        if portfolio_data and 'symbol' in portfolio_data[0]:
            # Check if we have dates as symbols (portfolio history format)
            first_symbol = portfolio_data[0]['symbol']
            if '/' in first_symbol and len(first_symbol.split('/')) == 3:  # Date format like "5/30/2025"
                print("Detected portfolio history format, extracting symbols from company field...")
                # The actual symbols are in the 'company' field when scraping history
                for item in portfolio_data:
                    if 'company' in item and item['company']:
                        item['symbol'] = item['company']
                        item['company'] = item.get('symbol', 'Unknown')  # Move date to company field

        # Step 2: If scraping is successful, buy all stocks
        if portfolio_data:
            df = pd.DataFrame(portfolio_data)
            print("\n--- Current Portfolio Stocks ---")
            print(df[['symbol', 'company', 'weight']].to_string())
            print(f"\nTotal stocks to buy: {len(df)}")
            
            # Confirm before executing
            confirm = input(f"\nReady to buy ${int(os.getenv('TRADE_AMOUNT'))} worth of each stock? (yes/no): ").strip().lower()
            if confirm == 'yes':
                buy_entire_portfolio(df, int(os.getenv('TRADE_AMOUNT')))
            else:
                print("Operation cancelled.")
        else:
            print("\nScraping did not return any data. Trading session will not start.")

    except Exception as e:
        print(f"An error occurred in the main process: {e}")


if __name__ == "__main__":
    main()

