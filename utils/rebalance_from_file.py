import threading
import time
import sys
import os
from datetime import datetime
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

from trade_dirs.trader import IBKR_API, run_loop

# --- Configuration ---


def normalize_symbol(symbol):
    """
    Normalize stock symbols to handle variations.
    E.g., 'BRK B' -> 'BRK.B', 'BRK.B' -> 'BRK.B'
    """
    # Replace space with dot for Class B/A stocks
    symbol = symbol.replace(' ', '.')
    return symbol


def ibkr_symbol(symbol):
    """
    Convert normalized symbol to IBKR format for orders.
    E.g., 'BRK.B' -> 'BRK B' (IBKR uses spaces for share classes)
    """
    # Convert dot back to space for IBKR API
    if '.' in symbol and len(symbol.split('.')) == 2:
        parts = symbol.split('.')
        if len(parts[1]) == 1 and parts[1].isalpha():  # Class A, B, etc.
            return f"{parts[0]} {parts[1]}"
    return symbol


def parse_target_file(filepath):
    """
    Parse a text file with target portfolio values.
    
    Supports formats:
    - Tab-separated: Stock\tPercentage\tValue
    - European numbers: 2.727,90 or 2,99%
    - US numbers: 2727.90 or 2.99%
    
    Returns:
        dict: {symbol: target_value, ...}
    """
    targets = {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Skip header line if it contains "Stock" or "Symbol"
    start_line = 0
    for i, line in enumerate(lines):
        if re.search(r'\b(stock|symbol)\b', line, re.IGNORECASE):
            start_line = i + 1
            break
    
    for line in lines[start_line:]:
        line = line.strip()
        if not line:
            continue
        
        # Split by tab or multiple spaces
        parts = re.split(r'\t+|\s{2,}', line)
        
        if len(parts) < 3:
            continue
        
        symbol = parts[0].strip()
        value_str = parts[2].strip()
        
        # Convert European format to US format (2.727,90 -> 2727.90)
        # First remove thousand separators (. or space)
        value_str = value_str.replace('.', '').replace(' ', '')
        # Then convert decimal comma to period
        value_str = value_str.replace(',', '.')
        # Remove any currency symbols
        value_str = re.sub(r'[^\d.]', '', value_str)
        
        try:
            value = float(value_str)
            targets[symbol] = value
            print(f"  {symbol}: ${value:.2f}")
        except ValueError:
            print(f"Warning: Could not parse value for {symbol}: {parts[2]}")
            continue
    
    return targets


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


def rebalance_to_targets(targets, account_id="", use_market=True):
    """
    Rebalances portfolio to match target values from file.
    
    Process:
    1. Gets all current positions with market values
    2. Compares to target values
    3. Buys stocks not in portfolio or below target
    4. Sells stocks above target
    5. Sells stocks not in target list
    6. Reports all movements to a txt file
    
    Args:
        targets: dict of {symbol: target_value}
        account_id: IBKR account ID (optional, defaults to primary account)
        use_market: Use market orders (True) or limit orders (False)
    """
    print("\n" + "="*60)
    print("     PORTFOLIO REBALANCING TO TARGET VALUES")
    print("="*60)
    print(f"Total Target Stocks: {len(targets)}")
    print(f"Total Target Value: ${sum(targets.values()):.2f}")
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
        
        print(f"\n--- Current Portfolio Holdings ({len(positions)} stocks) ---")
        
        # Normalize position symbols (e.g., "BRK B" -> "BRK.B")
        normalized_positions = {}
        for symbol, data in positions.items():
            norm_symbol = normalize_symbol(symbol)
            normalized_positions[norm_symbol] = data
            print(f"{norm_symbol:6} | Market Value: ${data['market_value']:8.2f} | "
                  f"Position: {data['position']:8.4f} @ ${data['avg_cost']:.2f}")
        
        if not normalized_positions:
            print("No current positions found.")
        
        positions = normalized_positions  # Use normalized symbols
        
        # Separate actions into buy, sell, and new
        buys = []
        sells = []
        new_stocks = []
        
        # Check existing positions
        for symbol, target_value in targets.items():
            if symbol in positions:
                current_value = positions[symbol]['market_value']
                difference = target_value - current_value
                
                if abs(difference) < 1:  # Skip if difference is less than $1
                    movements.append({
                        'symbol': symbol,
                        'action': 'HOLD',
                        'current_value': current_value,
                        'target_value': target_value,
                        'amount': 0,
                        'reason': 'Already at target value'
                    })
                    continue
                
                if difference > 0:  # Need to buy more
                    buys.append({
                        'symbol': symbol,
                        'current_value': current_value,
                        'target_value': target_value,
                        'amount': difference
                    })
                else:  # Need to sell some
                    sells.append({
                        'symbol': symbol,
                        'current_value': current_value,
                        'target_value': target_value,
                        'amount': abs(difference)
                    })
            else:
                # New stock to buy
                new_stocks.append({
                    'symbol': symbol,
                    'current_value': 0,
                    'target_value': target_value,
                    'amount': target_value
                })
        
        # Check for stocks to remove (in positions but not in targets)
        for symbol, data in positions.items():
            if symbol not in targets:
                sells.append({
                    'symbol': symbol,
                    'current_value': data['market_value'],
                    'target_value': 0,
                    'amount': data['market_value']
                })
        
        # Execute NEW stock orders first
        if new_stocks:
            print(f"\n--- Buying NEW Stocks ({len(new_stocks)} stocks) ---")
            for item in new_stocks:
                symbol = item['symbol']
                amount = item['amount']
                print(f"\n{symbol}: NEW -> Target ${item['target_value']:.2f}")
                print(f"Buying ${amount:.2f} worth...")
                
                try:
                    # Convert symbol to IBKR format (e.g., BRK.B -> BRK B)
                    order_symbol = ibkr_symbol(symbol)
                    app.place_dollar_order(order_symbol, "BUY", amount, use_market=use_market, 
                                         whole_shares_only=True, account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY_NEW',
                        'current_value': 0,
                        'target_value': item['target_value'],
                        'amount': amount,
                        'reason': 'New position'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing BUY order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY_FAILED',
                        'current_value': 0,
                        'target_value': item['target_value'],
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        # Execute BUY orders for existing stocks
        if buys:
            print(f"\n--- Executing BUY Orders ({len(buys)} stocks) ---")
            for item in buys:
                symbol = item['symbol']
                amount = item['amount']
                print(f"\n{symbol}: Current ${item['current_value']:.2f} -> Target ${item['target_value']:.2f}")
                print(f"Buying additional ${amount:.2f} worth...")
                
                try:
                    # Convert symbol to IBKR format (e.g., BRK.B -> BRK B)
                    order_symbol = ibkr_symbol(symbol)
                    app.place_dollar_order(order_symbol, "BUY", amount, use_market=use_market, 
                                         whole_shares_only=True, account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'current_value': item['current_value'],
                        'target_value': item['target_value'],
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
                        'target_value': item['target_value'],
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        # Execute SELL orders
        if sells:
            print(f"\n--- Executing SELL Orders ({len(sells)} stocks) ---")
            for item in sells:
                symbol = item['symbol']
                amount = item['amount']
                print(f"\n{symbol}: Current ${item['current_value']:.2f} -> Target ${item['target_value']:.2f}")
                print(f"Selling ${amount:.2f} worth...")
                
                try:
                    # Convert symbol to IBKR format (e.g., BRK.B -> BRK B)
                    order_symbol = ibkr_symbol(symbol)
                    app.place_dollar_order(order_symbol, "SELL", amount, use_market=use_market, 
                                         whole_shares_only=True, account=account_id)
                    action = 'SELL_ALL' if item['target_value'] == 0 else 'SELL'
                    movements.append({
                        'symbol': symbol,
                        'action': action,
                        'current_value': item['current_value'],
                        'target_value': item['target_value'],
                        'amount': amount,
                        'reason': 'Above target value' if item['target_value'] > 0 else 'Not in target list'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing SELL order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'SELL_FAILED',
                        'current_value': item['current_value'],
                        'target_value': item['target_value'],
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        print("\nWaiting for orders to process...")
        time.sleep(5)
        app.disconnect()
        
        # Generate report
        report_file = generate_report(movements, targets)
        
        print("\n" + "="*60)
        print(f"Rebalancing Complete! Report saved to: {report_file}")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"An error occurred during rebalancing: {e}")
        if movements:
            # Still generate report even if there was an error
            report_file = generate_report(movements, targets, error=str(e))
            print(f"Partial report saved to: {report_file}")


def generate_report(movements, targets, error=None):
    """Generate a text report of all portfolio movements."""
    # Ensure reports directory exists
    reports_dir = "../reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"rebalance_from_file_{timestamp}.txt"
    filepath = os.path.join(reports_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write("="*70 + "\n")
        f.write("      PORTFOLIO REBALANCING TO TARGET VALUES REPORT\n")
        f.write("="*70 + "\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Target Stocks: {len(targets)}\n")
        f.write(f"Total Target Value: ${sum(targets.values()):.2f}\n")
        f.write("="*70 + "\n\n")
        
        if error:
            f.write(f"ERROR OCCURRED: {error}\n\n")
        
        # Summary statistics
        total_new = sum(1 for m in movements if m['action'] == 'BUY_NEW')
        total_buys = sum(1 for m in movements if m['action'] == 'BUY')
        total_sells = sum(1 for m in movements if m['action'] in ['SELL', 'SELL_ALL'])
        total_holds = sum(1 for m in movements if m['action'] == 'HOLD')
        total_buy_amount = sum(m['amount'] for m in movements if 'BUY' in m['action'])
        total_sell_amount = sum(m['amount'] for m in movements if 'SELL' in m['action'])
        
        f.write("SUMMARY\n")
        f.write("-"*70 + "\n")
        f.write(f"Total Stocks Processed: {len(movements)}\n")
        f.write(f"  - NEW Positions: {total_new:3d}  (Total: ${sum(m['amount'] for m in movements if m['action'] == 'BUY_NEW'):10.2f})\n")
        f.write(f"  - BUY Orders:    {total_buys:3d}  (Total: ${sum(m['amount'] for m in movements if m['action'] == 'BUY'):10.2f})\n")
        f.write(f"  - SELL Orders:   {total_sells:3d}  (Total: ${total_sell_amount:10.2f})\n")
        f.write(f"  - HOLD:          {total_holds:3d}\n")
        f.write(f"Net Movement: ${total_buy_amount - total_sell_amount:+.2f}\n")
        f.write("-"*70 + "\n\n")
        
        # Detailed movements
        f.write("DETAILED MOVEMENTS\n")
        f.write("-"*70 + "\n")
        f.write(f"{'Symbol':<8} {'Action':<12} {'Current':<12} {'Target':<12} {'Amount':<12} {'Reason'}\n")
        f.write("-"*70 + "\n")
        
        # Sort: NEW first, then BUYs, then SELLs, then HOLDs
        action_order = {'BUY_NEW': 1, 'BUY': 2, 'SELL': 3, 'SELL_ALL': 4, 'HOLD': 5, 
                       'BUY_FAILED': 6, 'SELL_FAILED': 7}
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
    """Main function to run portfolio rebalancing from file."""
    print("\n" + "="*60)
    print("    PORTFOLIO REBALANCING FROM FILE")
    print("="*60)
    print("This will adjust all positions to match target values")
    print("from a text file.")
    
    # Check for command line arguments
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python rebalance_from_file.py <targets_file> [--account ACCOUNT_ID] [--limit]")
        print("\nOptions:")
        print("  --account ID  : Specify IBKR account ID")
        print("  --limit       : Use limit orders instead of market orders")
        print("\nExample:")
        print("  python rebalance_from_file.py targets.txt")
        print("  python rebalance_from_file.py targets.txt --account U1234567 --limit")
        return
    
    target_file = sys.argv[1]
    account_id = ""
    use_market = True
    
    # Parse command line arguments
    if "--account" in sys.argv:
        try:
            account_index = sys.argv.index("--account") + 1
            if account_index < len(sys.argv):
                account_id = sys.argv[account_index]
        except (ValueError, IndexError):
            print("Error: --account requires an account ID")
            return
    
    if "--limit" in sys.argv:
        use_market = False
        print("Using limit orders")
    
    # If no account specified, prompt for selection
    if not account_id:
        account_id = select_account()
    
    # Parse target file
    print(f"\n--- Parsing Target File: {target_file} ---")
    try:
        targets = parse_target_file(target_file)
    except FileNotFoundError:
        print(f"Error: File '{target_file}' not found")
        return
    except Exception as e:
        print(f"Error parsing file: {e}")
        return
    
    if not targets:
        print("No valid targets found in file. Exiting.")
        return
    
    print(f"\nParsed {len(targets)} target stocks")
    print(f"Total target value: ${sum(targets.values()):.2f}")
    print(f"Selected Account: {account_id if account_id else 'Primary Account'}")
    print(f"Order Type: {'MARKET' if use_market else 'LIMIT'}")
    
    confirm = input(f"\nReady to rebalance portfolio? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        rebalance_to_targets(targets, account_id, use_market)
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()

