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
    
    Supports two formats:
    
    Format 1 (Explicit Operations): Ticker\tValue\tOperation
    - Value uses European decimal format (comma as separator)
    - Negative values mean Buy, positive values mean Sell
    - Operation column explicitly says "Buy" or "Sell"
    
    Format 2 (Target Values): Stock\tPercentage\tValue
    - Lists target values for each stock
    - Will automatically determine BUY/SELL by comparing with current portfolio
    
    Returns:
        list: [{symbol: str, amount: float, action: str (optional)}, ...]
        Note: action may be None if using Format 2, will be determined later
    """
    trades = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Detect file format by looking at header
    file_format = None
    start_line = 0
    
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if 'OPERATION' in line_upper or 'ACTION' in line_upper:
            file_format = 'explicit'
            start_line = i + 1
            break
        elif 'PERCENTAGE' in line_upper or ('STOCK' in line_upper and 'VALUE' in line_upper):
            file_format = 'target'
            start_line = i + 1
            break
        elif re.search(r'\b(TICKER|SYMBOL)\b', line, re.IGNORECASE):
            # Default to explicit format if only Ticker is mentioned
            file_format = 'explicit'
            start_line = i + 1
            break
    
    # If no header found, try to auto-detect from first data line
    if file_format is None:
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'\t+|\s{2,}', line)
            if len(parts) >= 3:
                # Check if third column looks like operation or percentage
                third_col = parts[2].strip().upper()
                if 'BUY' in third_col or 'SELL' in third_col:
                    file_format = 'explicit'
                elif '%' in third_col or '.' in parts[1]:
                    file_format = 'target'
                    start_line = i
                break
    
    # Default to target format if still unknown
    if file_format is None:
        file_format = 'target'
    
    print(f"Detected format: {'Explicit Operations' if file_format == 'explicit' else 'Target Values'}")
    
    # Parse based on format
    for line in lines[start_line:]:
        line = line.strip()
        if not line or line.lower().startswith('total'):
            continue
        
        # Split by tab or multiple spaces
        parts = re.split(r'\t+|\s{2,}', line)
        
        if len(parts) < 2:
            continue
        
        symbol = parts[0].strip()
        
        if file_format == 'explicit':
            # Format 1: Ticker\tValue\tOperation
            if len(parts) < 3:
                continue
                
            value_str = parts[1].strip()
            operation = parts[2].strip().upper()
            
            # Convert European format to US format
            value_str = value_str.replace(',', '.')
            value_str = re.sub(r'[^\d.\-]', '', value_str)
            
            try:
                value = float(value_str)
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
                
        else:
            # Format 2: Stock\tPercentage\tValue
            # Get target value (could be in column 1 or 2)
            value_str = None
            if len(parts) >= 3:
                # Try third column first (likely the Value column)
                value_str = parts[2].strip()
            elif len(parts) >= 2:
                # Try second column
                value_str = parts[1].strip()
            
            if not value_str:
                continue
            
            # Convert European format to US format
            value_str = value_str.replace(',', '.')
            value_str = value_str.replace('%', '')
            value_str = re.sub(r'[^\d.\-]', '', value_str)
            
            try:
                target_value = float(value_str)
                
                trades.append({
                    'symbol': symbol,
                    'target_value': target_value,
                    'action': None  # Will be determined by comparing with current portfolio
                })
                print(f"  {symbol}: Target ${target_value:.2f}")
                
            except ValueError:
                print(f"Warning: Could not parse value for {symbol}: {value_str}")
                continue
    
    return trades


def determine_trades_from_targets(targets, positions):
    """
    Determine BUY/SELL operations by comparing target values with current positions.
    
    Args:
        targets: List of {symbol: str, target_value: float}
        positions: Dict of {symbol: {market_value: float, ...}}
        
    Returns:
        list: [{symbol: str, amount: float, action: str}, ...]
    """
    trades = []
    threshold = 5.0  # Minimum dollar difference to trigger a trade
    
    print_section(f"Comparing Current vs Target Values (threshold: ${threshold:.2f})")
    
    for target in targets:
        symbol = target['symbol']
        target_value = target['target_value']
        current_value = positions.get(symbol, {}).get('market_value', 0)
        
        difference = target_value - current_value
        
        if abs(difference) < threshold:
            print(f"{symbol:6}: Current ${current_value:8.2f} ≈ Target ${target_value:8.2f} → SKIP")
            continue
        
        if difference > 0:
            # Need to buy more
            action = 'BUY'
            amount = difference
            print(f"{symbol:6}: Current ${current_value:8.2f} < Target ${target_value:8.2f} → BUY ${amount:.2f}")
        else:
            # Need to sell
            action = 'SELL'
            amount = abs(difference)
            print(f"{symbol:6}: Current ${current_value:8.2f} > Target ${target_value:8.2f} → SELL ${amount:.2f}")
        
        trades.append({
            'symbol': symbol,
            'amount': amount,
            'action': action,
            'target_value': target_value,
            'current_value': current_value
        })
    
    return trades


def execute_trades_from_file(trades, account_id="", use_market=True):
    """
    Execute trades from file instructions.
    
    Process:
    1. Gets current portfolio positions
    2. If trades have target values, determines BUY/SELL by comparing current vs target
    3. Executes buy/sell orders
    4. Uses market orders that execute when market opens
    5. Rounds down share quantities for IBKR compatibility
    6. Reports all movements to a txt file
    
    Args:
        trades: list of {symbol: str, amount: float, action: str} OR
                list of {symbol: str, target_value: float, action: None}
        account_id: IBKR account ID (optional, defaults to primary account)
        use_market: Use market orders (True) or limit orders (False)
    """
    print_header("EXECUTING TRADES FROM FILE")
    
    movements = []
    
    try:
        # Connect to IBKR
        app, _ = connect_to_ibkr()
        
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
        
        # Check if we need to determine trades from targets
        if trades and trades[0].get('action') is None:
            # Target-based format - determine trades by comparing current vs target
            print("\n")
            trades = determine_trades_from_targets(trades, positions)
            
            if not trades:
                print("\nNo trades needed - portfolio matches targets within threshold.")
                disconnect_from_ibkr(app)
                return
        
        # Calculate totals
        total_buys = sum(t['amount'] for t in trades if t['action'] == 'BUY')
        total_sells = sum(t['amount'] for t in trades if t['action'] == 'SELL')
        buy_count = sum(1 for t in trades if t['action'] == 'BUY')
        sell_count = sum(1 for t in trades if t['action'] == 'SELL')
        
        print(f"\n--- Trade Summary ---")
        print(f"Total Trades: {len(trades)}")
        print(f"  - BUY:  {buy_count} trades, ${total_buys:.2f}")
        print(f"  - SELL: {sell_count} trades, ${total_sells:.2f}")
        print(f"Account: {account_id if account_id else 'Primary Account'}")
        print(f"Order Type: {'MARKET' if use_market else 'LIMIT'} (executes when market opens)")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
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
                    
                    movement = {
                        'symbol': symbol,
                        'action': 'SELL',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': 'Rebalance to target'
                    }
                    if 'target_value' in trade:
                        movement['target_value'] = trade['target_value']
                    movements.append(movement)
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing SELL order for {symbol}: {e}")
                    movement = {
                        'symbol': symbol,
                        'action': 'SELL_FAILED',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    }
                    if 'target_value' in trade:
                        movement['target_value'] = trade['target_value']
                    movements.append(movement)
        
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
                    
                    movement = {
                        'symbol': symbol,
                        'action': 'BUY',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': 'Rebalance to target'
                    }
                    if 'target_value' in trade:
                        movement['target_value'] = trade['target_value']
                    movements.append(movement)
                    time.sleep(1)  # Delay between orders
                except Exception as e:
                    print(f"Error placing BUY order for {symbol}: {e}")
                    movement = {
                        'symbol': symbol,
                        'action': 'BUY_FAILED',
                        'current_value': current_value,
                        'amount': amount,
                        'reason': f'Error: {str(e)}'
                    }
                    if 'target_value' in trade:
                        movement['target_value'] = trade['target_value']
                    movements.append(movement)
        
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
    print("This will execute buy/sell orders from a file.")
    print("Supports two formats:")
    print("  1. Explicit operations (Ticker/Value/Operation)")
    print("  2. Target values (automatically determines BUY/SELL by comparing with current positions)")
    print("\nOrders will be market orders that execute when market opens.")
    print("Share quantities will be rounded down for IBKR compatibility.")
    
    # Check for command line arguments
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python rebalance_from_file.py <trades_file> [--account ACCOUNT_ID] [--limit]")
        print("\nFile Format 1 - Explicit Operations (tab-separated):")
        print("  Ticker    Value    Operation")
        print("  AAPL      -100,50  Buy")
        print("  MSFT      50,25    Sell")
        print("\nFile Format 2 - Target Values (tab-separated):")
        print("  Stock     Percentage  Value")
        print("  AAPL      10.5%       2500.00")
        print("  MSFT      8.3%        2000.00")
        print("  (Automatically determines BUY/SELL based on current portfolio)")
        print("\nOptions:")
        print("  --account ID  : Specify IBKR account ID")
        print("  --limit       : Use limit orders instead of market orders (default: market)")
        print("\nExample:")
        print("  python rebalance_from_file.py trades.txt")
        print("  python rebalance_from_file.py input2.txt --account U1234567")
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
    
    # Check if we're using target-based format
    if trades[0].get('action') is None:
        # Target-based format
        total_target = sum(t.get('target_value', 0) for t in trades)
        print(f"\nParsed {len(trades)} target positions:")
        print(f"  Total Target Value: ${total_target:.2f}")
        print(f"Selected Account: {args['account_id'] if args['account_id'] else 'Primary Account'}")
        print(f"Order Type: {'MARKET' if args['use_market'] else 'LIMIT'}")
        print("\nNote: Actual BUY/SELL operations will be determined by comparing with current portfolio.")
    else:
        # Explicit operations format
        buy_count = sum(1 for t in trades if t['action'] == 'BUY')
        sell_count = sum(1 for t in trades if t['action'] == 'SELL')
        total_buy = sum(t.get('amount', 0) for t in trades if t['action'] == 'BUY')
        total_sell = sum(t.get('amount', 0) for t in trades if t['action'] == 'SELL')
        
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

