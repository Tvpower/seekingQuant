import sys
import os
from datetime import datetime
import re
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_common import (
    normalize_symbol, ibkr_symbol, connect_to_ibkr, disconnect_from_ibkr,
    select_account, generate_trade_report, parse_trading_args,
    print_header, print_section, confirm_action
)


def parse_trades_file(filepath):
    """
    Parse a text file with trade instructions.
    
    Format: Ticker\tValue\tOperation
    - Value uses European decimal format (comma as separator)
    - Negative values mean Buy, positive values mean Sell
    - Operation column explicitly says "Buy" or "Sell"
    
    Returns:
        list: [{symbol: str, amount: float, action: str}, ...]
    """
    trades = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Skip header line if it contains "Ticker" or "Operation"
    start_line = 0
    for i, line in enumerate(lines):
        if re.search(r'\b(ticker|operation|symbol)\b', line, re.IGNORECASE):
            start_line = i + 1
            break
    
    for line in lines[start_line:]:
        line = line.strip()
        if not line or line.lower().startswith('total'):
            continue
        
        # Split by tab or multiple spaces
        parts = re.split(r'\t+|\s{2,}', line)
        
        if len(parts) < 3:
            continue
        
        symbol = parts[0].strip()
        value_str = parts[1].strip()
        operation = parts[2].strip().upper()
        
        # Convert European format to US format (15,30 -> 15.30)
        # Replace comma with period for decimal separator
        value_str = value_str.replace(',', '.')
        # Remove any non-numeric characters except decimal point and minus
        value_str = re.sub(r'[^\d.\-]', '', value_str)
        
        try:
            value = float(value_str)
            # Take absolute value since we use the Operation column for direction
            amount = abs(value)
            
            # Determine action from Operation column
            if 'BUY' in operation:
                action = 'BUY'
            elif 'SELL' in operation:
                action = 'SELL'
            else:
                print(f"Warning: Unknown operation '{operation}' for {symbol}, skipping")
                continue
            
            trades.append({
                'symbol': symbol,
                'amount': amount,
                'action': action
            })
            print(f"  {symbol}: {action} ${amount:.2f}")
            
        except ValueError:
            print(f"Warning: Could not parse value for {symbol}: {parts[1]}")
            continue
    
    return trades


def execute_trades_from_file(trades, account_id="", use_market=True):
    """
    Execute trades from file instructions.
    
    Process:
    1. Gets current portfolio positions for reference
    2. Executes buy/sell orders as specified in file
    3. Uses market orders that execute when market opens
    4. Rounds down share quantities for IBKR compatibility
    5. Reports all movements to a txt file
    
    Args:
        trades: list of {symbol: str, amount: float, action: str}
        account_id: IBKR account ID (optional, defaults to primary account)
        use_market: Use market orders (True) or limit orders (False)
    """
    print_header("EXECUTING TRADES FROM FILE")
    
    total_buys = sum(t['amount'] for t in trades if t['action'] == 'BUY')
    total_sells = sum(t['amount'] for t in trades if t['action'] == 'SELL')
    buy_count = sum(1 for t in trades if t['action'] == 'BUY')
    sell_count = sum(1 for t in trades if t['action'] == 'SELL')
    
    print(f"Total Trades: {len(trades)}")
    print(f"  - BUY:  {buy_count} trades, ${total_buys:.2f}")
    print(f"  - SELL: {sell_count} trades, ${total_sells:.2f}")
    print(f"Account: {account_id if account_id else 'Primary Account'}")
    print(f"Order Type: MARKET (executes when market opens)")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    movements = []
    
    try:
        # Connect to IBKR
        app, _ = connect_to_ibkr()
        
        # Get all current positions for reference
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
        
        # Separate trades by action
        buys = [t for t in trades if t['action'] == 'BUY']
        sells = [t for t in trades if t['action'] == 'SELL']
        
        # Execute SELL orders first
        if sells:
            print_section(f"Executing SELL Orders ({len(sells)} stocks)")
            for trade in sells:
                symbol = trade['symbol']
                amount = trade['amount']
                current_value = positions.get(symbol, {}).get('market_value', 0)
                
                print(f"\n{symbol}: Selling ${amount:.2f}")
                if current_value > 0:
                    print(f"  Current position value: ${current_value:.2f}")
                
                try:
                    # Convert symbol to IBKR format (e.g., BRK.B -> BRK B)
                    order_symbol = ibkr_symbol(symbol)
                    app.place_dollar_order(order_symbol, "SELL", amount, 
                                         use_market=use_market, 
                                         whole_shares_only=True, 
                                         round_up=False,
                                         account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'SELL',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': 'File instruction'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing SELL order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'SELL_FAILED',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        # Execute BUY orders
        if buys:
            print_section(f"Executing BUY Orders ({len(buys)} stocks)")
            for trade in buys:
                symbol = trade['symbol']
                amount = trade['amount']
                current_value = positions.get(symbol, {}).get('market_value', 0)
                
                print(f"\n{symbol}: Buying ${amount:.2f}")
                if current_value > 0:
                    print(f"  Current position value: ${current_value:.2f}")
                else:
                    print(f"  New position")
                
                try:
                    # Convert symbol to IBKR format (e.g., BRK.B -> BRK B)
                    order_symbol = ibkr_symbol(symbol)
                    app.place_dollar_order(order_symbol, "BUY", amount, 
                                         use_market=use_market, 
                                         whole_shares_only=True, 
                                         round_up=False,
                                         account=account_id)
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': 'File instruction'
                    })
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing BUY order for {symbol}: {e}")
                    movements.append({
                        'symbol': symbol,
                        'action': 'BUY_FAILED',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    })
        
        disconnect_from_ibkr(app)
        
        # Generate report
        report_file = generate_trade_report(
            movements,
            report_type="rebalance_from_file",
            title="TRADES FROM FILE EXECUTION REPORT",
            additional_info={
                'Total Trades': len(trades),
                'BUY Orders': f"{buy_count} (${total_buys:.2f})",
                'SELL Orders': f"{sell_count} (${total_sells:.2f})",
                'Net Cash Movement': f"${total_buys - total_sells:+.2f}",
                'Account': account_id if account_id else 'Primary Account',
                'Order Type': 'MARKET'
            }
        )
        
        print_header(f"Trade Execution Complete! Report saved to: {report_file}")
        
    except Exception as e:
        print(f"An error occurred during trade execution: {e}")
        if movements:
            # Still generate report even if there was an error
            report_file = generate_trade_report(
                movements,
                report_type="rebalance_from_file",
                title="TRADES FROM FILE EXECUTION REPORT (PARTIAL)",
                additional_info={
                    'Total Trades': len(trades),
                    'BUY Orders': f"{buy_count} (${total_buys:.2f})",
                    'SELL Orders': f"{sell_count} (${total_sells:.2f})"
                },
                error=str(e)
            )
            print(f"Partial report saved to: {report_file}")


def main():
    """Main function to execute trades from file."""
    print_header("EXECUTE TRADES FROM FILE")
    print("This will execute buy/sell orders as specified in the file.")
    print("Orders will be market orders that execute when market opens.")
    print("Share quantities will be rounded down for IBKR compatibility.")
    
    # Check for command line arguments
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python rebalance_from_file.py <trades_file> [--account ACCOUNT_ID] [--limit]")
        print("\nFile Format (tab-separated):")
        print("  Ticker    Value    Operation")
        print("  AAPL      -100,50  Buy")
        print("  MSFT      50,25    Sell")
        print("\nOptions:")
        print("  --account ID  : Specify IBKR account ID")
        print("  --limit       : Use limit orders instead of market orders (default: market)")
        print("\nExample:")
        print("  python rebalance_from_file.py trades.txt")
        print("  python rebalance_from_file.py trades.txt --account U1234567")
        return
    
    trades_file = sys.argv[1]
    
    # Parse command line arguments
    args = parse_trading_args(sys.argv)
    if args is None:
        return
    
    # If no account specified, prompt for selection
    if not args['account_id']:
        args['account_id'] = select_account()
    
    # Parse trades file
    print(f"\n--- Parsing Trades File: {trades_file} ---")
    try:
        trades = parse_trades_file(trades_file)
    except FileNotFoundError:
        print(f"Error: File '{trades_file}' not found")
        return
    except Exception as e:
        print(f"Error parsing file: {e}")
        return
    
    if not trades:
        print("No valid trades found in file. Exiting.")
        return
    
    buy_count = sum(1 for t in trades if t['action'] == 'BUY')
    sell_count = sum(1 for t in trades if t['action'] == 'SELL')
    total_buy = sum(t['amount'] for t in trades if t['action'] == 'BUY')
    total_sell = sum(t['amount'] for t in trades if t['action'] == 'SELL')
    
    print(f"\nParsed {len(trades)} trades:")
    print(f"  - BUY:  {buy_count} trades, ${total_buy:.2f}")
    print(f"  - SELL: {sell_count} trades, ${total_sell:.2f}")
    print(f"Selected Account: {args['account_id'] if args['account_id'] else 'Primary Account'}")
    print(f"Order Type: {'MARKET' if args['use_market'] else 'LIMIT'}")
    
    if args['auto_confirm'] or confirm_action("Ready to execute trades?"):
        execute_trades_from_file(trades, args['account_id'], args['use_market'])
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()

