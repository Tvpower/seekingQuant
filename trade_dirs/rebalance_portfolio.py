import threading
import time
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from trader import IBKR_API, run_loop

# --- Configuration ---


def get_available_accounts():
    """Get list of available accounts from IBKR."""
    print("\nConnecting to IBKR to fetch available accounts...")
    
    try:
        app = IBKR_API()
        app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))
        
        api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
        api_thread.start()
        
        time.sleep(2)  # Wait for connection
        
        accounts = app.get_available_accounts()
        app.disconnect()
        
        return accounts
        
    except Exception as e:
        print(f"Error fetching accounts: {e}")
        return []


def select_account():
    """Interactive account selection with real account fetching."""
    print("\n--- Account Selection ---")
    print("1. Fetch accounts from IBKR")
    print("2. Enter custom account ID")
    print("3. Use Primary Account (default)")
    
    while True:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            accounts = get_available_accounts()
            
            if not accounts:
                print("No accounts found or error occurred.")
                print("Falling back to manual entry...")
                account_id = input("Enter account ID: ").strip()
                return account_id if account_id else ""
            
            print(f"\nFound {len(accounts)} account(s):")
            for i, account in enumerate(accounts, 1):
                account_display = account if account else "Primary Account"
                print(f"  {i}. {account_display}")
            
            while True:
                try:
                    selection = input(f"\nSelect account (1-{len(accounts)}): ").strip()
                    if selection.lower() in ['q', 'quit', 'exit']:
                        return ""
                    
                    index = int(selection) - 1
                    if 0 <= index < len(accounts):
                        return accounts[index]
                    else:
                        print(f"Please enter a number between 1 and {len(accounts)}")
                except ValueError:
                    print("Please enter a valid number or 'q' to quit")
                except KeyboardInterrupt:
                    print("\nOperation cancelled.")
                    return ""
                    
        elif choice == "2":
            account_id = input("Enter account ID: ").strip()
            if account_id:
                return account_id
            else:
                print("Invalid account ID. Please try again.")
        elif choice == "3":
            return ""
        else:
            print("Invalid choice. Please select 1, 2, or 3.")


def rebalance_portfolio(account_id=""):
    """
    Rebalances portfolio by adjusting all stock positions to $500 market value.
    
    Process:
    1. Gets all current positions with market values
    2. Executes BUY orders first for stocks below $500
    3. Executes SELL orders for stocks above $500
    4. Reports all movements to a txt file
    
    Args:
        account_id: IBKR account ID (optional, defaults to primary account)
    """
    print("\n" + "="*60)
    print("     PORTFOLIO REBALANCING SESSION")
    print("="*60)
    print(f"Target Value per Stock: ${int(os.getenv('TARGET_VALUE_PER_STOCK'))}")
    print(f"Account: {account_id if account_id else 'Primary Account'}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")
    
    movements = []
    
    try:
        # Connect to IBKR
        app = IBKR_API()
        app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))
        
        api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
        api_thread.start()
        
        time.sleep(3)  # Wait for connection
        
        # Get all current positions
        positions = app.get_account_positions(account_id)
        
        if not positions:
            print("No positions found in account.")
            app.disconnect()
            return
        
        print(f"\n--- Current Portfolio Holdings ({len(positions)} stocks) ---")
        for symbol, data in positions.items():
            print(f"{symbol:6} | Market Value: ${data['market_value']:8.2f} | "
                  f"Position: {data['position']:8.4f} @ ${data['avg_cost']:.2f}")
        
        # Separate stocks into buy and sell lists
        buys = []
        sells = []
        
        for symbol, data in positions.items():
            market_value = data['market_value']
            difference = int(os.getenv('TARGET_VALUE_PER_STOCK')) - market_value
            
            if abs(difference) < 1:  # Skip if difference is less than $1
                movements.append({
                    'symbol': symbol,
                    'action': 'HOLD',
                    'current_value': market_value,
                    'target_value': int(os.getenv('TARGET_VALUE_PER_STOCK')),
                    'amount': 0,
                    'reason': 'Already at target value'
                })
                continue
            
            if difference > 0:  # Need to buy
                buys.append({
                    'symbol': symbol,
                    'current_value': market_value,
                    'amount': difference
                })
            else:  # Need to sell
                sells.append({
                    'symbol': symbol,
                    'current_value': market_value,
                    'amount': abs(difference)
                })
        
        # Execute BUY orders first
        # Note: Using MARKET orders - if market is closed, orders will queue for market open
        if buys:
            print(f"\n--- Executing BUY Orders ({len(buys)} stocks) ---")
            print("Note: Market orders will execute at market open if placed outside trading hours")
            for item in buys:
                symbol = item['symbol']
                amount = item['amount']
                print(f"\n{symbol}: Current ${item['current_value']:.2f} -> Target ${int(os.getenv('TARGET_VALUE_PER_STOCK')):.2f}")
                print(f"Buying ${amount:.2f} worth...")
                
                try:
                    app.place_dollar_order(symbol, "BUY", amount, use_market=True, whole_shares_only=True, account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'current_value': item['current_value'],
                        'target_value': int(os.getenv('TARGET_VALUE_PER_STOCK')),
                        'amount': amount,
                        'reason': 'Below target value'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing BUY order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY_FAILED',
                        'current_value': item['current_value'],
                        'target_value': int(os.getenv('TARGET_VALUE_PER_STOCK')),
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        # Execute SELL orders
        if sells:
            print(f"\n--- Executing SELL Orders ({len(sells)} stocks) ---")
            for item in sells:
                symbol = item['symbol']
                amount = item['amount']
                print(f"\n{symbol}: Current ${item['current_value']:.2f} -> Target ${int(os.getenv('TARGET_VALUE_PER_STOCK')):.2f}")
                print(f"Selling ${amount:.2f} worth...")
                
                try:
                    app.place_dollar_order(symbol, "SELL", amount, use_market=True, whole_shares_only=True, account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'SELL',
                        'current_value': item['current_value'],
                        'target_value': int(os.getenv('TARGET_VALUE_PER_STOCK')),
                        'amount': amount,
                        'reason': 'Above target value'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing SELL order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'SELL_FAILED',
                        'current_value': item['current_value'],
                        'target_value': int(os.getenv('TARGET_VALUE_PER_STOCK')),
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        print("\nWaiting for orders to process...")
        time.sleep(5)
        app.disconnect()
        
        # Generate report
        report_file = generate_report(movements)
        
        print("\n" + "="*60)
        print(f"Rebalancing Complete! Report saved to: {report_file}")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"An error occurred during rebalancing: {e}")
        if movements:
            # Still generate report even if there was an error
            report_file = generate_report(movements, error=str(e))
            print(f"Partial report saved to: {report_file}")


def generate_report(movements, error=None):
    """Generate a text report of all portfolio movements."""
    # Create reports directory if it doesn't exist
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"rebalance_report_{timestamp}.txt"
    filepath = os.path.join(reports_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write("="*70 + "\n")
        f.write("           PORTFOLIO REBALANCING REPORT\n")
        f.write("="*70 + "\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Target Value per Stock: ${os.getenv('TARGET_VALUE_PER_STOCK')}\n")
        f.write("="*70 + "\n\n")
        
        if error:
            f.write(f"ERROR OCCURRED: {error}\n\n")
        
        # Summary statistics
        total_buys = sum(1 for m in movements if m['action'] == 'BUY')
        total_sells = sum(1 for m in movements if m['action'] == 'SELL')
        total_holds = sum(1 for m in movements if m['action'] == 'HOLD')
        total_buy_amount = sum(m['amount'] for m in movements if m['action'] == 'BUY')
        total_sell_amount = sum(m['amount'] for m in movements if m['action'] == 'SELL')
        
        f.write("SUMMARY\n")
        f.write("-"*70 + "\n")
        f.write(f"Total Stocks Processed: {len(movements)}\n")
        f.write(f"  - BUY Orders:  {total_buys:3d}  (Total: ${total_buy_amount:10.2f})\n")
        f.write(f"  - SELL Orders: {total_sells:3d}  (Total: ${total_sell_amount:10.2f})\n")
        f.write(f"  - HOLD:        {total_holds:3d}\n")
        f.write(f"Net Movement: ${total_buy_amount - total_sell_amount:+.2f}\n")
        f.write("-"*70 + "\n\n")
        
        # Detailed movements
        f.write("DETAILED MOVEMENTS\n")
        f.write("-"*70 + "\n")
        f.write(f"{'Symbol':<8} {'Action':<12} {'Current':<12} {'Target':<12} {'Amount':<12} {'Reason'}\n")
        f.write("-"*70 + "\n")
        
        # Sort: BUYs first, then SELLs, then HOLDs
        action_order = {'BUY': 1, 'SELL': 2, 'HOLD': 3, 'BUY_FAILED': 4, 'SELL_FAILED': 5}
        sorted_movements = sorted(movements, key=lambda x: (action_order.get(x['action'], 99), x['symbol']))
        
        for m in sorted_movements:
            symbol = m['symbol']
            action = m['action']
            current = f"${m['current_value']:.2f}"
            target = f"${m['target_value']:.2f}"
            amount = f"${m['amount']:.2f}" if m['amount'] != 0 else "-"
            reason = m['reason']
            
            f.write(f"{symbol:<8} {action:<12} {current:<12} {target:<12} {amount:<12} {reason}\n")
        
        f.write("-"*70 + "\n")
        f.write("\nEnd of Report\n")
    
    return filepath


def main():
    """Main function to run portfolio rebalancing."""
    print("\n" + "="*50)
    print("    PORTFOLIO REBALANCING TOOL")
    print("="*50)
    print("This will adjust all stock positions to $500 market value each.")
    print("Uses MARKET orders (whole shares only) - queued for market open if closed")
    
    # Check for command line arguments
    account_id = ""
    auto_confirm = False
    
    if len(sys.argv) > 1:
        # Command line mode
        if "--account" in sys.argv:
            try:
                account_index = sys.argv.index("--account") + 1
                if account_index < len(sys.argv):
                    account_id = sys.argv[account_index]
            except (ValueError, IndexError):
                print("Error: --account requires an account ID")
                return
        
        if "--auto" in sys.argv:
            auto_confirm = True
            print("Auto-confirm mode enabled")
    else:
        # Interactive mode
        account_id = select_account()
    
    print(f"\nSelected Account: {account_id if account_id else 'Primary Account'}")
    print(f"Target Value per Stock: ${int(os.getenv('TARGET_VALUE_PER_STOCK'))}")
    
    if auto_confirm:
        print("Auto-confirming rebalancing...")
        rebalance_portfolio(account_id)
    else:
        confirm = input(f"\nReady to rebalance portfolio? (yes/no): ").strip().lower()
        
        if confirm == 'yes':
            rebalance_portfolio(account_id)
        else:
            print("Operation cancelled.")


if __name__ == "__main__":
    main()

