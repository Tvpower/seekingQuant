"""
Common utilities for trading scripts.
Shared functions for account management, symbol normalization, 
IBKR connections, and report generation.
"""
import threading
import time
import os
from datetime import datetime
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_dirs.trader import IBKR_API, run_loop


# ============================================================================
# SYMBOL NORMALIZATION
# ============================================================================

def normalize_symbol(symbol):
    """
    Normalize stock symbols to handle variations.
    E.g., 'BRK B' -> 'BRK.B', 'BRK.B' -> 'BRK.B'
    
    Args:
        symbol: Stock symbol string
        
    Returns:
        str: Normalized symbol
    """
    # Replace space with dot for Class B/A stocks
    symbol = symbol.replace(' ', '.')
    return symbol


def ibkr_symbol(symbol):
    """
    Convert normalized symbol to IBKR format for orders.
    E.g., 'BRK.B' -> 'BRK B' (IBKR uses spaces for share classes)
    
    Args:
        symbol: Normalized stock symbol
        
    Returns:
        str: IBKR-formatted symbol
    """
    # Convert dot back to space for IBKR API
    if '.' in symbol and len(symbol.split('.')) == 2:
        parts = symbol.split('.')
        if len(parts[1]) == 1 and parts[1].isalpha():  # Class A, B, etc.
            return f"{parts[0]} {parts[1]}"
    return symbol


# ============================================================================
# IBKR CONNECTION MANAGEMENT
# ============================================================================

def connect_to_ibkr():
    """
    Connect to IBKR and return the API instance and thread.
    
    Returns:
        tuple: (app, api_thread) - IBKR API instance and thread
    """
    app = IBKR_API()
    app.connect("127.0.0.1", int(os.getenv('IBKR_PORT')), int(os.getenv('IBKR_CLIENT_ID')))
    
    api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
    api_thread.start()
    
    time.sleep(3)  # Wait for connection
    
    return app, api_thread


def disconnect_from_ibkr(app):
    """
    Safely disconnect from IBKR.
    
    Args:
        app: IBKR API instance
    """
    print("\nWaiting for orders to process...")
    time.sleep(5)
    app.disconnect()


# ============================================================================
# ACCOUNT MANAGEMENT
# ============================================================================

def get_available_accounts():
    """
    Get list of available accounts from IBKR.
    
    Returns:
        list: List of account IDs
    """
    print("\nConnecting to IBKR to fetch available accounts...")
    
    try:
        app, _ = connect_to_ibkr()
        time.sleep(1)  # Extra wait for account data
        
        accounts = app.get_available_accounts()
        app.disconnect()
        
        return accounts
        
    except Exception as e:
        print(f"Error fetching accounts: {e}")
        return []


def select_account():
    """
    Interactive account selection with real account fetching.
    
    Returns:
        str: Selected account ID (empty string for primary account)
    """
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


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_trade_report(movements, report_type="rebalance", title=None, 
                          additional_info=None, error=None):
    """
    Generate a text report of trading movements.
    
    Args:
        movements: List of movement dictionaries
        report_type: Type of report (affects filename prefix)
        title: Custom title for report (optional)
        additional_info: Dict of additional info to include in header
        error: Error message if operation failed
        
    Returns:
        str: Path to generated report file
    """
    # Ensure reports directory exists
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{report_type}_{timestamp}.txt"
    filepath = os.path.join(reports_dir, filename)
    
    # Default title
    if not title:
        title = f"{report_type.upper().replace('_', ' ')} REPORT"
    
    with open(filepath, 'w') as f:
        # Header
        f.write("="*70 + "\n")
        f.write(f"      {title}\n")
        f.write("="*70 + "\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Additional info
        if additional_info:
            for key, value in additional_info.items():
                f.write(f"{key}: {value}\n")
        
        f.write("="*70 + "\n\n")
        
        if error:
            f.write(f"ERROR OCCURRED: {error}\n\n")
        
        # Summary statistics
        total_buys = sum(1 for m in movements if 'BUY' in m.get('action', '') and 'FAILED' not in m.get('action', ''))
        total_sells = sum(1 for m in movements if 'SELL' in m.get('action', '') and 'FAILED' not in m.get('action', ''))
        total_holds = sum(1 for m in movements if m.get('action') == 'HOLD')
        total_failed = sum(1 for m in movements if 'FAILED' in m.get('action', ''))
        
        total_buy_amount = sum(m.get('amount', 0) for m in movements if 'BUY' in m.get('action', '') and 'FAILED' not in m.get('action', ''))
        total_sell_amount = sum(m.get('amount', 0) for m in movements if 'SELL' in m.get('action', '') and 'FAILED' not in m.get('action', ''))
        
        f.write("SUMMARY\n")
        f.write("-"*70 + "\n")
        f.write(f"Total Movements: {len(movements)}\n")
        f.write(f"  - BUY Orders:    {total_buys:3d}  (Total: ${total_buy_amount:10.2f})\n")
        f.write(f"  - SELL Orders:   {total_sells:3d}  (Total: ${total_sell_amount:10.2f})\n")
        if total_holds > 0:
            f.write(f"  - HOLD:          {total_holds:3d}\n")
        if total_failed > 0:
            f.write(f"  - FAILED:        {total_failed:3d}\n")
        f.write(f"Net Cash Movement: ${total_buy_amount - total_sell_amount:+.2f}\n")
        f.write("-"*70 + "\n\n")
        
        # Detailed movements
        f.write("DETAILED MOVEMENTS\n")
        f.write("-"*70 + "\n")
        
        # Determine columns based on available data
        has_current = any('current_value' in m for m in movements)
        has_target = any('target_value' in m for m in movements)
        has_date = any('date' in m for m in movements)
        has_status = any('status' in m for m in movements)
        
        # Build header dynamically
        header_parts = [('Symbol', 8), ('Action', 12)]
        
        if has_current:
            header_parts.append(('Current', 12))
        if has_target:
            header_parts.append(('Target', 12))
        
        header_parts.append(('Amount', 12))
        
        if has_date:
            header_parts.append(('Date', 12))
        
        if has_status:
            header_parts.append(('Status', 0))  # Last column, no width limit
        elif 'reason' in movements[0] if movements else False:
            header_parts.append(('Reason', 0))  # Last column, no width limit
        
        # Write header
        for name, width in header_parts[:-1]:
            f.write(f"{name:<{width}} ")
        f.write(f"{header_parts[-1][0]}\n")  # Last column
        f.write("-"*70 + "\n")
        
        # Sort movements
        action_order = {
            'BUY_NEW': 1, 'BUY': 2, 'SELL': 3, 'SELL_ALL': 4, 
            'HOLD': 5, 'BUY_FAILED': 6, 'SELL_FAILED': 7
        }
        sorted_movements = sorted(movements, key=lambda x: (action_order.get(x.get('action', ''), 99), x.get('symbol', '')))
        
        # Write movements
        for m in sorted_movements:
            line_parts = []
            
            # Symbol and Action
            line_parts.append(f"{m.get('symbol', 'N/A'):<8}")
            line_parts.append(f"{m.get('action', 'N/A'):<12}")
            
            # Current value
            if has_current:
                current_val = m.get('current_value', 0)
                line_parts.append(f"${current_val:.2f}"[:12].ljust(12))
            
            # Target value
            if has_target:
                target_val = m.get('target_value', 0)
                line_parts.append(f"${target_val:.2f}"[:12].ljust(12))
            
            # Amount
            amount = m.get('amount', 0)
            amount_str = f"${amount:.2f}" if amount != 0 else "-"
            line_parts.append(f"{amount_str:<12}")
            
            # Date
            if has_date:
                line_parts.append(f"{m.get('date', 'N/A'):<12}")
            
            # Status or Reason
            if has_status:
                line_parts.append(m.get('status', 'N/A'))
            elif 'reason' in m:
                line_parts.append(m.get('reason', 'N/A'))
            
            f.write(' '.join(line_parts) + '\n')
        
        f.write("-"*70 + "\n")
        f.write("\nEnd of Report\n")
    
    return filepath


# ============================================================================
# COMMAND LINE ARGUMENT PARSING
# ============================================================================

def parse_trading_args(argv):
    """
    Parse common trading command line arguments.
    
    Args:
        argv: sys.argv
        
    Returns:
        dict: Parsed arguments {
            'account_id': str,
            'use_market': bool,
            'headless': bool,
            'auto_confirm': bool
        }
    """
    args = {
        'account_id': '',
        'use_market': True,
        'headless': False,
        'auto_confirm': False
    }
    
    if "--account" in argv:
        try:
            account_index = argv.index("--account") + 1
            if account_index < len(argv):
                args['account_id'] = argv[account_index]
        except (ValueError, IndexError):
            print("Error: --account requires an account ID")
            return None
    
    if "--limit" in argv:
        args['use_market'] = False
    
    if "--headless" in argv:
        args['headless'] = True
    
    if "--auto" in argv:
        args['auto_confirm'] = True
    
    return args


# ============================================================================
# DISPLAY UTILITIES
# ============================================================================

def print_header(title, width=60):
    """Print a formatted header."""
    print("\n" + "="*width)
    print(f"     {title}")
    print("="*width)


def print_section(title, width=60):
    """Print a formatted section header."""
    print(f"\n--- {title} ---")


def confirm_action(message="Ready to proceed?"):
    """
    Ask user for confirmation.
    
    Args:
        message: Confirmation message
        
    Returns:
        bool: True if user confirmed, False otherwise
    """
    confirm = input(f"\n{message} (yes/no): ").strip().lower()
    return confirm == 'yes'

