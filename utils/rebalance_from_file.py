import sys
import os
from datetime import datetime
import re

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_common import (
    normalize_symbol, ibkr_symbol, connect_to_ibkr, disconnect_from_ibkr,
    select_account, generate_trade_report, parse_trading_args,
    print_header, print_section, confirm_action
)


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
    print_header("PORTFOLIO REBALANCING TO TARGET VALUES")
    print(f"Total Target Stocks: {len(targets)}")
    print(f"Total Target Value: ${sum(targets.values()):.2f}")
    print(f"Account: {account_id if account_id else 'Primary Account'}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
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
            print_section(f"Buying NEW Stocks ({len(new_stocks)} stocks)")
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
            print_section(f"Executing BUY Orders ({len(buys)} stocks)")
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
            print_section(f"Executing SELL Orders ({len(sells)} stocks)")
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
        
        disconnect_from_ibkr(app)
        
        # Generate report
        report_file = generate_trade_report(
            movements,
            report_type="rebalance_from_file",
            title="PORTFOLIO REBALANCING TO TARGET VALUES REPORT",
            additional_info={
                'Total Target Stocks': len(targets),
                'Total Target Value': f"${sum(targets.values()):.2f}",
                'Account': account_id if account_id else 'Primary Account'
            }
        )
        
        print_header(f"Rebalancing Complete! Report saved to: {report_file}")
        
    except Exception as e:
        print(f"An error occurred during rebalancing: {e}")
        if movements:
            # Still generate report even if there was an error
            report_file = generate_trade_report(
                movements,
                report_type="rebalance_from_file",
                title="PORTFOLIO REBALANCING TO TARGET VALUES REPORT (PARTIAL)",
                additional_info={
                    'Total Target Stocks': len(targets),
                    'Total Target Value': f"${sum(targets.values()):.2f}"
                },
                error=str(e)
            )
            print(f"Partial report saved to: {report_file}")


def main():
    """Main function to run portfolio rebalancing from file."""
    print_header("PORTFOLIO REBALANCING FROM FILE")
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
    
    # Parse command line arguments
    args = parse_trading_args(sys.argv)
    if args is None:
        return
    
    # If no account specified, prompt for selection
    if not args['account_id']:
        args['account_id'] = select_account()
    
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
    print(f"Selected Account: {args['account_id'] if args['account_id'] else 'Primary Account'}")
    print(f"Order Type: {'MARKET' if args['use_market'] else 'LIMIT'}")
    
    if args['auto_confirm'] or confirm_action("Ready to rebalance portfolio?"):
        rebalance_to_targets(targets, args['account_id'], args['use_market'])
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()

