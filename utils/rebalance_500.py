import sys
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_common import (
    connect_to_ibkr, disconnect_from_ibkr, select_account,
    generate_trade_report, parse_trading_args, print_header,
    print_section, confirm_action
)


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
    print_header("PORTFOLIO REBALANCING SESSION")
    print(f"Target Value per Stock: ${int(os.getenv('TARGET_VALUE_PER_STOCK'))}")
    print(f"Account: {account_id if account_id else 'Primary Account'}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    movements = []
    
    try:
        # Connect to IBKR
        app, _ = connect_to_ibkr()
        
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
            print_section(f"Executing BUY Orders ({len(buys)} stocks)")
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
            print_section(f"Executing SELL Orders ({len(sells)} stocks)")
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
        
        disconnect_from_ibkr(app)
        
        # Generate report
        report_file = generate_trade_report(
            movements,
            report_type="rebalance_report",
            title="PORTFOLIO REBALANCING REPORT",
            additional_info={
                'Target Value per Stock': f"${os.getenv('TARGET_VALUE_PER_STOCK')}",
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
                report_type="rebalance_report",
                title="PORTFOLIO REBALANCING REPORT (PARTIAL)",
                additional_info={
                    'Target Value per Stock': f"${os.getenv('TARGET_VALUE_PER_STOCK')}"
                },
                error=str(e)
            )
            print(f"Partial report saved to: {report_file}")


def main():
    """Main function to run portfolio rebalancing."""
    print_header("PORTFOLIO REBALANCING TOOL")
    print("This will adjust all stock positions to $500 market value each.")
    print("Uses MARKET orders (whole shares only) - queued for market open if closed")
    
    # Parse command line arguments
    args = parse_trading_args(sys.argv)
    if args is None:
        return
    
    # If no account specified and not in auto mode, prompt for selection
    if not args['account_id'] and not args['auto_confirm']:
        args['account_id'] = select_account()
    
    print(f"\nSelected Account: {args['account_id'] if args['account_id'] else 'Primary Account'}")
    print(f"Target Value per Stock: ${int(os.getenv('TARGET_VALUE_PER_STOCK'))}")
    
    if args['auto_confirm'] or confirm_action("Ready to rebalance portfolio?"):
        rebalance_portfolio(args['account_id'])
    else:
        print("Operation cancelled.")


if __name__ == "__main__":
    main()

