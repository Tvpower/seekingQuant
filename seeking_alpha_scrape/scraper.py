import os
from playwright.sync_api import sync_playwright

# Browser Configuration
USE_EXISTING_SESSION = False
BROWSER_USER_DATA_DIR = os.path.expanduser("~/snap/brave/current/.config/BraveSoftware/Brave-Browser")
BROWSER_PROFILE_NAME = "Default"
TEMP_PROFILE_DIR = os.path.expanduser("~/.playwright_seeking_alpha_profile")
BROWSER_EXECUTABLE_PATH = None

# URLs
CURRENT_PICKS_URL = "https://seekingalpha.com/pro-quant-portfolio/picks/current"
PORTFOLIO_HISTORY_URL = "https://seekingalpha.com/pro-quant-portfolio/portfolio-history"

# Table Selectors (try in order)
TABLE_SELECTORS = [
    'tbody[data-test-id="table-body-infinite"]',
    'tbody[data-test-id="table-body"]'
]

# Timeouts (milliseconds)
NAVIGATION_TIMEOUT = 60000
PAGE_LOAD_WAIT = 3000
LOGIN_CHECK_TIMEOUT = 30000
LOGIN_CHECK_WAIT = 2000


def _create_stealth_script():
    """Return JavaScript for stealth mode."""
    return """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });

        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        window.chrome = {
            runtime: {},
        };

        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """


def setup_driver(user_data_dir, profile_name, executable_path, use_existing_session,
                 remote_debugging_port=None, headless=False):
    """
    Set up Playwright browser with stealth mode using persistent context.

    Returns:
        tuple: (playwright, context, page)
    """
    playwright = sync_playwright().start()

    profile_path = TEMP_PROFILE_DIR
    os.makedirs(profile_path, exist_ok=True)

    if not headless:
        print(f"Launching browser with persistent profile: {profile_path}")
        print("This profile will save your login session for future runs.")

    context = playwright.chromium.launch_persistent_context(
        profile_path,
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
        ],
        ignore_default_args=['--enable-automation'],
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    page = context.pages[0] if len(context.pages) > 0 else context.new_page()
    page.add_init_script(_create_stealth_script())

    return (playwright, context, page)


# ============================================================================
# NAVIGATION & LOGIN
# ============================================================================

def _navigate_and_wait(page, url, timeout=NAVIGATION_TIMEOUT, wait_time=PAGE_LOAD_WAIT):
    """Navigate to URL and wait for page to load."""
    page.goto(url, wait_until='networkidle', timeout=timeout)
    page.wait_for_timeout(wait_time)


def _has_table(page):
    """Check if any valid table selector is present on the page."""
    return any(page.locator(selector).count() > 0 for selector in TABLE_SELECTORS)


def check_if_login_needed(page):
    """
    Check if user needs to login to Seeking Alpha.
    Returns True if login is needed, False if already logged in.
    """
    try:
        page.goto(CURRENT_PICKS_URL, timeout=LOGIN_CHECK_TIMEOUT)
        page.wait_for_timeout(LOGIN_CHECK_WAIT)

        current_url = page.url

        # Check for login/subscription pages
        if 'login' in current_url.lower() or 'sign-in' in current_url.lower():
            return True

        if page.locator('text=/subscribe|sign up|create account/i').count() > 0:
            return True

        # Check if table is present
        return not _has_table(page)

    except:
        return True


# ============================================================================
# TABLE SCRAPING UTILITIES
# ============================================================================

def _find_table(page):
    """
    Find and return the table body element using available selectors.
    Returns (selector, row_count) or (None, 0) if not found.
    """
    for selector in TABLE_SELECTORS:
        print(f"Looking for table with selector: {selector}")

        if page.locator(selector).count() == 0:
            print(f"No table found with selector: {selector}")
            continue

        print(f"Found table with selector: {selector}")
        rows = page.locator(f"{selector} tr").all()
        print(f"Found {len(rows)} rows")

        return selector, rows

    return None, []


def _extract_cell_text(cell, use_link=False):
    """Extract text from a cell, optionally from a link."""
    try:
        if use_link:
            link = cell.locator('a').first
            if link.count() > 0:
                return link.inner_text().strip()
        return cell.inner_text().strip()
    except:
        return ''


def _parse_row_generic(cells, column_mapping):
    """
    Parse a row using a column mapping dictionary.

    Args:
        cells: List of cell elements
        column_mapping: Dict with format {index: (key_name, use_link)}

    Returns:
        dict: Parsed row data
    """
    row_data = {}

    for col_idx, (key_name, use_link) in column_mapping.items():
        if col_idx < len(cells):
            row_data[key_name] = _extract_cell_text(cells[col_idx], use_link)

    return row_data


# ============================================================================
# CURRENT PICKS SCRAPER
# ============================================================================

def _get_picks_column_mapping():
    """Return column mapping for current picks table."""
    return {
        0: ('company', True),      # Company name (from link)
        1: ('symbol', False),       # Symbol
        2: ('picked_price', False), # Picked Price
        3: ('sector', False),       # Sector
        4: ('weight', False),       # Weight
        5: ('quant_rating', False), # Quant Rating
        6: ('price_return', False)  # Price Return
    }


def _print_pick(i, data):
    """Print a single pick entry."""
    print(f"Row {i}: {data['symbol']} - {data.get('company', 'N/A')} - Weight: {data.get('weight', 'N/A')}")


def scrape_current_picks(page, navigate=True):
    """
    Scrape current picks from Seeking Alpha Pro Quant Portfolio.

    Returns:
        list: List of dictionaries with pick data
    """
    if navigate:
        print(f"\nNavigating to: {CURRENT_PICKS_URL}")
        _navigate_and_wait(page, CURRENT_PICKS_URL)

    selector, rows = _find_table(page)
    if not selector:
        print("No table found")
        return []

    table_data = []
    column_mapping = _get_picks_column_mapping()

    for i, row in enumerate(rows):
        try:
            # Get both th and td cells (first column might be th)
            cells = row.locator('th, td').all()
            if len(cells) < 5:
                continue

            row_data = _parse_row_generic(cells, column_mapping)

            if row_data.get('symbol'):
                table_data.append(row_data)
                _print_pick(i, row_data)

        except Exception as e:
            print(f"Error processing row {i}: {e}")
            continue

    print(f"\n=== Scraped {len(table_data)} picks ===\n")
    return table_data


# ============================================================================
# PORTFOLIO HISTORY SCRAPER
# ============================================================================

def _get_history_column_mapping():
    """Return column mapping for portfolio history table."""
    return {
        0: ('symbol', False),         # Symbol
        1: ('date', False),           # Date
        2: ('action', False),         # Action
        3: ('starting_weight', False),# Starting Weight
        4: ('new_weight', False),     # New Weight
        5: ('change_weight', False),  # Change In Weight
        6: ('price_share', False)     # Price/Share
    }


def _print_history_entry(i, data):
    """Print a single history entry."""
    print(f"Row {i}: {data['symbol']} - {data['date']} - {data['action']} - Change: {data.get('change_weight', 'N/A')}")


def scrape_portfolio_history(page, filter_last_friday=True):
    """
    Scrape portfolio history from Seeking Alpha Pro Quant Portfolio.

    Args:
        filter_last_friday: If True, only return the most recent date's movements

    Returns:
        list: List of dictionaries with history data
    """
    print(f"\nNavigating to: {PORTFOLIO_HISTORY_URL}")
    _navigate_and_wait(page, PORTFOLIO_HISTORY_URL)

    selector, rows = _find_table(page)
    if not selector:
        print("No table found")
        return []

    table_data = []
    column_mapping = _get_history_column_mapping()
    latest_date = None

    from datetime import datetime
    def _parse_date_string(date_str):
        if not date_str:
            return None
        cleaned = ' '.join(date_str.split())
        for fmt in ('%m/%d/%Y', '%m/%d/%y', '%b %d, %Y', '%B %d, %Y'):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except Exception:
                continue
        return None

    for i, row in enumerate(rows):
        try:
            cells = row.locator('th, td').all()
            if len(cells) < 7:
                continue

            row_data = _parse_row_generic(cells, column_mapping)

            if not row_data.get('symbol'):
                continue

            # **FILTER OUT REBALANCE ACTIONS**
            action = row_data.get('action', '').upper()
            if 'REBALANCE' in action:
                continue

            if filter_last_friday:
                current_date = _parse_date_string(row_data.get('date', ''))

                if latest_date is None:
                    latest_date = current_date
                elif current_date != latest_date:
                    break

                if current_date == latest_date:
                    table_data.append(row_data)
            else:
                table_data.append(row_data)
                _print_history_entry(i, row_data)

        except Exception as e:
            print(f"Error processing row {i}: {e}")
            continue

    if filter_last_friday and table_data:
        print(
            f"\n=== Filtered to latest date ({latest_date.isoformat() if latest_date else 'N/A'}): {len(table_data)} movements (Buy/Sell only) ===\n")
        return table_data

    print(f"\n=== Scraped {len(table_data)} history entries (Buy/Sell only) ===\n")
    return table_data


# ============================================================================
# DATA CONVERSION
# ============================================================================

def _determine_trading_action(action, change_weight):
    """Determine trading action from history entry."""
    action = action.upper()

    if 'BUY' in action:
        return 'BUY'
    elif 'SELL' in action:
        return 'SELL'
    elif 'REBALANCE' in action:
        # Parse weight change to determine action
        try:
            change_val = float(change_weight.replace('%', '').replace('+', ''))
            if change_val > 0.1:
                return 'BUY'
            elif change_val < -0.1:
                return 'SELL'
        except:
            pass

    return 'HOLD'


def scrape_portfolio_data(driver_tuple, filter_to_recent=True):
    """
    Scrape portfolio data and convert to trading format.

    Returns:
        list: List of dictionaries with trading data
    """
    _, _, page = driver_tuple

    history_data = scrape_portfolio_history(page, filter_last_friday=filter_to_recent)

    trading_data = []
    for entry in history_data:
        symbol = entry.get('symbol', '')
        action = entry.get('action', '')
        change_weight = entry.get('change_weight', '0%')

        trading_action = _determine_trading_action(action, change_weight)

        if trading_action in ['BUY', 'SELL']:
            trading_data.append({
                'Symbol': symbol,
                'Action': trading_action,
                'Weight': entry.get('new_weight', ''),
                'Change': change_weight,
                'Date': entry.get('date', '')
            })

    return trading_data


# ============================================================================
# AUTOMATED SCRAPING
# ============================================================================

def get_portfolio_data_automated(scrape_type='current_picks', headless=True):
    """
    Automated function to scrape portfolio data without manual intervention.

    Args:
        scrape_type: 'current_picks', 'latest_history', or 'all_history'
        headless: Whether to run browser in headless mode

    Returns:
        list: Scraped data or None if error
    """
    driver_tuple = None
    try:
        driver_tuple = setup_driver(
            BROWSER_USER_DATA_DIR,
            BROWSER_PROFILE_NAME,
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION,
            headless=headless
        )

        playwright, context, page = driver_tuple

        if check_if_login_needed(page):
            print("⚠️  WARNING: Login required. Please run scraper.py manually first to log in.")
            return None

        # Route to appropriate scraper
        if scrape_type == 'current_picks':
            page.goto(CURRENT_PICKS_URL, wait_until='networkidle', timeout=NAVIGATION_TIMEOUT)
            page.wait_for_timeout(LOGIN_CHECK_WAIT)
            data = scrape_current_picks(page, navigate=False)
        elif scrape_type == 'latest_history':
            data = scrape_portfolio_history(page, filter_last_friday=True)
        elif scrape_type == 'all_history':
            data = scrape_portfolio_history(page, filter_last_friday=False)
        else:
            print(f"Invalid scrape_type: {scrape_type}")
            return None

        return data

    except Exception as e:
        print(f"Error in automated scraping: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if driver_tuple:
            playwright, context, _ = driver_tuple
            context.close()
            playwright.stop()


# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def _display_pick(i, item):
    """Display a single pick entry."""
    print(f"\n--- Pick {i} ---")
    print(f"Company: {item.get('company', 'N/A')}")
    print(f"Symbol: {item.get('symbol', 'N/A')}")
    print(f"Picked Price: {item.get('picked_price', 'N/A')}")
    print(f"Sector: {item.get('sector', 'N/A')}")
    print(f"Weight: {item.get('weight', 'N/A')}")
    print(f"Quant Rating: {item.get('quant_rating', 'N/A')}")
    print(f"Price Return: {item.get('price_return', 'N/A')}")


def _display_history(i, item):
    """Display a single history entry."""
    print(f"\n--- Movement {i} ---")
    print(f"Symbol: {item.get('symbol', 'N/A')}")
    print(f"Date: {item.get('date', 'N/A')}")
    print(f"Action: {item.get('action', 'N/A')}")
    print(f"Starting Weight: {item.get('starting_weight', 'N/A')}")
    print(f"New Weight: {item.get('new_weight', 'N/A')}")
    print(f"Change: {item.get('change_weight', 'N/A')}")
    print(f"Price/Share: {item.get('price_share', 'N/A')}")


def display_results(data, data_type='picks'):
    """Display scraped results."""
    if not data:
        print("\nNo data scraped.")
        return

    print(f"\n=== {data_type.upper()} DATA ===")

    if data_type == 'picks':
        for i, item in enumerate(data, 1):
            _display_pick(i, item)
    elif data_type == 'history':
        for i, item in enumerate(data, 1):
            _display_history(i, item)
    elif data_type == 'history_all':
        print(f"Total movements: {len(data)}")
        for i, item in enumerate(data[:10], 1):
            _display_history(i, item)
        if len(data) > 10:
            print(f"\n... and {len(data) - 10} more movements")


# ============================================================================
# LOGIN HANDLING
# ============================================================================

def handle_login(page):
    """Handle login prompt and verification."""
    print("\n" + "="*60)
    print("LOGIN REQUIRED")
    print("="*60)
    print("\nThe browser has opened. Please:")
    print("1. Click 'Sign In' or navigate to login")
    print("2. Login using your Google account")
    print("3. Make sure you're logged into Seeking Alpha Pro")
    print("4. Verify you can see the portfolio data")
    print("\nPress Enter AFTER you've successfully logged in...")
    input()

    # Verify login
    print("\nVerifying login...")
    page.goto(CURRENT_PICKS_URL, timeout=LOGIN_CHECK_TIMEOUT)
    page.wait_for_timeout(LOGIN_CHECK_WAIT)

    if not _has_table(page):
        print("\n⚠️  WARNING: Could not detect table. Make sure you're logged in.")
        print("Continuing anyway (automated mode)...")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def _get_user_choice():
    """Get scraping choice from user."""
    import sys

    print("\n=== Seeking Alpha Pro Quant Portfolio Scraper ===")
    print("1. Scrape Current Picks")
    print("2. Scrape Portfolio History (latest movements)")
    print("3. Scrape Portfolio History (all)")

    if len(sys.argv) > 1:
        return sys.argv[1]
    else:
        return input("\nEnter choice (1/2/3): ").strip()


def _execute_scraping_choice(choice, page):
    """Execute scraping based on user choice."""
    if choice == '1':
        print("\n=== SCRAPING CURRENT PICKS ===")
        page.goto(CURRENT_PICKS_URL, wait_until='networkidle', timeout=NAVIGATION_TIMEOUT)
        page.wait_for_timeout(LOGIN_CHECK_WAIT)
        data = scrape_current_picks(page, navigate=False)
        display_results(data, 'picks')

    elif choice == '2':
        print("\n=== SCRAPING LATEST PORTFOLIO HISTORY ===")
        data = scrape_portfolio_history(page, filter_last_friday=True)
        display_results(data, 'history')

    elif choice == '3':
        print("\n=== SCRAPING ALL PORTFOLIO HISTORY ===")
        data = scrape_portfolio_history(page, filter_last_friday=False)
        display_results(data, 'history_all')

    else:
        print("Invalid choice. Exiting.")


def main():
    """Main function for testing the scraper independently."""
    driver_tuple = None
    try:
        print("Setting up Playwright browser...")
        driver_tuple = setup_driver(
            BROWSER_USER_DATA_DIR,
            BROWSER_PROFILE_NAME,
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION
        )

        playwright, context, page = driver_tuple

        # Check and handle login
        print("\n=== Checking Login Status ===")
        needs_login = check_if_login_needed(page)

        if needs_login:
            handle_login(page)
        else:
            print("✓ Already logged in! Session restored from previous run.\n")

        # Get user choice and execute
        choice = _get_user_choice()
        _execute_scraping_choice(choice, page)

        print("\nClosing browser...")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver_tuple:
            playwright, context, _ = driver_tuple
            context.close()
            playwright.stop()


if __name__ == "__main__":
    main()
