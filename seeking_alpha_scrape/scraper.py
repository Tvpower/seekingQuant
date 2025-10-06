import os
from playwright.sync_api import sync_playwright

# --- Configuration ---
# For Snap browsers, we'll use a temporary profile and copy cookies
USE_EXISTING_SESSION = False  # Using fresh Chromium with copied cookies/state

BROWSER_USER_DATA_DIR = os.path.expanduser("~/snap/brave/current/.config/BraveSoftware/Brave-Browser")  # Brave profile directory
BROWSER_PROFILE_NAME = "Default"  # Brave profile name
TEMP_PROFILE_DIR = os.path.expanduser("~/.playwright_seeking_alpha_profile")  # Temporary profile
REMOTE_DEBUGGING_PORT = None  # Not needed for Playwright
BROWSER_EXECUTABLE_PATH = None  # Use Playwright's Chromium

# URLs
CURRENT_PICKS_URL = "https://seekingalpha.com/pro-quant-portfolio/picks/current"
PORTFOLIO_HISTORY_URL = "https://seekingalpha.com/pro-quant-portfolio/portfolio-history"


def check_if_login_needed(page):
    """
    Check if user needs to login to Seeking Alpha.
    Returns True if login is needed, False if already logged in.
    """
    try:
        # Navigate to the picks page
        page.goto(CURRENT_PICKS_URL, timeout=30000)
        page.wait_for_timeout(2000)
        
        # Check if we're redirected to login or see login-related elements
        current_url = page.url
        
        # If we're on a login page or see login prompts
        if 'login' in current_url.lower() or 'sign-in' in current_url.lower():
            return True
        
        # Check for subscription/paywall
        if page.locator('text=/subscribe|sign up|create account/i').count() > 0:
            return True
        
        # Check for both table selectors (infinite and regular)
        if page.locator('tbody[data-test-id="table-body"]').count() > 0:
            return False
        if page.locator('tbody[data-test-id="table-body-infinite"]').count() > 0:
            return False
        
        # Default to needing login
        return True
    except:
        return True


def setup_driver(user_data_dir, profile_name, executable_path, use_existing_session, remote_debugging_port=None, headless=False):
    """
    Set up Playwright browser with stealth mode using persistent context.
    
    Args:
        user_data_dir: Path to Chrome user data directory
        profile_name: Chrome profile name to use
        executable_path: Path to Chrome executable
        use_existing_session: Whether to use persistent browser context
        remote_debugging_port: Not used in Playwright (kept for compatibility)
        headless: Whether to run browser in headless mode (for automation)
    
    Returns:
        tuple: (playwright, context, page)
    """
    playwright = sync_playwright().start()
    
    # Use a dedicated profile directory for Seeking Alpha scraping
    profile_path = TEMP_PROFILE_DIR
    os.makedirs(profile_path, exist_ok=True)
    
    if not headless:
        print(f"Launching browser with persistent profile: {profile_path}")
        print("This profile will save your login session for future runs.")
    
    # Launch browser with persistent context (saves login between runs)
    context = playwright.chromium.launch_persistent_context(
        profile_path,
        headless=headless,  # Configurable headless mode
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
        ],
        ignore_default_args=['--enable-automation'],
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Get or create a page
    if len(context.pages) > 0:
        page = context.pages[0]
    else:
        page = context.new_page()
    
    # Apply stealth techniques via JavaScript
    page.add_init_script("""
        // Overwrite the `navigator.webdriver` property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        
        // Overwrite the `plugins` property to use a custom getter
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Overwrite the `languages` property
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        // Pass the Chrome Test
        window.chrome = {
            runtime: {},
        };
        
        // Pass the Permissions Test
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    return (playwright, context, page)


def scrape_current_picks(page, navigate=True):
    """
    Scrape current picks from Seeking Alpha Pro Quant Portfolio.
    URL: https://seekingalpha.com/pro-quant-portfolio/picks/current
    
    Args:
        navigate: If True, navigate to the page. If False, assume already on the page.
    
    Returns:
        list: List of dictionaries with: company, symbol, picked_price, sector, weight, quant_rating, price_return
    """
    if navigate:
        print(f"\nNavigating to: {CURRENT_PICKS_URL}")
        page.goto(CURRENT_PICKS_URL, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(3000)
    
    # Try both table selectors
    selectors = [
        'tbody[data-test-id="table-body-infinite"]',
        'tbody[data-test-id="table-body"]'
    ]
    
    table_data = []
    
    for selector in selectors:
        print(f"\nLooking for table with selector: {selector}")
        
        if page.locator(selector).count() == 0:
            print(f"No table found with selector: {selector}")
            continue
        
        print(f"Found table with selector: {selector}")
        rows = page.locator(f"{selector} tr").all()
        print(f"Found {len(rows)} rows")
        
        for i, row in enumerate(rows):
            try:
                cells = row.locator('td').all()
                if len(cells) < 5:
                    continue
                
                row_data = {}
                
                # Column 0: Company name (link)
                company_link = cells[0].locator('a').first
                if company_link.count() > 0:
                    row_data['company'] = company_link.inner_text().strip()
                else:
                    row_data['company'] = cells[0].inner_text().strip()
                
                # Column 1: Symbol
                row_data['symbol'] = cells[1].inner_text().strip()
                
                # Column 2: Picked Price (may contain date + price)
                picked_text = cells[2].inner_text().strip()
                row_data['picked_price'] = picked_text
                
                # Column 3: Sector
                row_data['sector'] = cells[3].inner_text().strip()
                
                # Column 4: Weight (percentage)
                row_data['weight'] = cells[4].inner_text().strip()
                
                # Column 5: Quant Rating (if exists)
                if len(cells) > 5:
                    row_data['quant_rating'] = cells[5].inner_text().strip()
                
                # Column 6: Price Return (if exists)
                if len(cells) > 6:
                    row_data['price_return'] = cells[6].inner_text().strip()
                
                if row_data.get('symbol'):
                    table_data.append(row_data)
                    print(f"Row {i}: {row_data['symbol']} - {row_data.get('company', 'N/A')} - Weight: {row_data.get('weight', 'N/A')}")
                
            except Exception as e:
                print(f"Error processing row {i}: {e}")
                continue
        
        if table_data:
            break
    
    print(f"\n=== Scraped {len(table_data)} picks ===\n")
    return table_data


def scrape_portfolio_history(page, filter_last_friday=True):
    """
    Scrape portfolio history from Seeking Alpha Pro Quant Portfolio.
    URL: https://seekingalpha.com/pro-quant-portfolio/portfolio-history
    
    Args:
        filter_last_friday: If True, only return the most recent date's movements
    
    Returns:
        list: List of dictionaries with: symbol, date, action, starting_weight, new_weight, change_weight, price_share
    """
    print(f"\nNavigating to: {PORTFOLIO_HISTORY_URL}")
    page.goto(PORTFOLIO_HISTORY_URL, wait_until='networkidle', timeout=60000)
    page.wait_for_timeout(3000)
    
    # Try both table selectors
    selectors = [
        'tbody[data-test-id="table-body-infinite"]',
        'tbody[data-test-id="table-body"]'
    ]
    
    table_data = []
    
    for selector in selectors:
        print(f"\nLooking for table with selector: {selector}")
        
        if page.locator(selector).count() == 0:
            print(f"No table found with selector: {selector}")
            continue
        
        print(f"Found table with selector: {selector}")
        rows = page.locator(f"{selector} tr").all()
        print(f"Found {len(rows)} rows")
        
        latest_date = None
        
        for i, row in enumerate(rows):
            try:
                cells = row.locator('td').all()
                if len(cells) < 7:
                    continue
                
                row_data = {}
                
                # Column 0: Symbol
                row_data['symbol'] = cells[0].inner_text().strip()
                
                # Column 1: Date
                row_data['date'] = cells[1].inner_text().strip()
                
                # Track the latest date
                if latest_date is None:
                    latest_date = row_data['date']
                
                # Column 2: Action (Buy/Sell/Rebalance)
                row_data['action'] = cells[2].inner_text().strip()
                
                # Column 3: Starting Weight %
                row_data['starting_weight'] = cells[3].inner_text().strip()
                
                # Column 4: New Weight %
                row_data['new_weight'] = cells[4].inner_text().strip()
                
                # Column 5: Change In Weight %
                row_data['change_weight'] = cells[5].inner_text().strip()
                
                # Column 6: Price/Share
                row_data['price_share'] = cells[6].inner_text().strip()
                
                if row_data.get('symbol'):
                    table_data.append(row_data)
                    print(f"Row {i}: {row_data['symbol']} - {row_data['date']} - {row_data['action']} - Change: {row_data.get('change_weight', 'N/A')}")
                
            except Exception as e:
                print(f"Error processing row {i}: {e}")
                continue
        
        if table_data:
            break
    
    # Filter to only the latest date if requested
    if filter_last_friday and latest_date and table_data:
        filtered_data = [row for row in table_data if row['date'] == latest_date]
        print(f"\n=== Filtered to latest date ({latest_date}): {len(filtered_data)} movements ===\n")
        return filtered_data
    
    print(f"\n=== Scraped {len(table_data)} history entries ===\n")
    return table_data


def scrape_portfolio_data(driver_tuple, filter_to_recent=True):
    """
    Scrape portfolio data from Seeking Alpha Pro Quant Portfolio.
    This function scrapes the portfolio history (movements).
    
    Args:
        driver_tuple: Tuple of (playwright, context, page)
        filter_to_recent: If True, only return the latest date's movements
    
    Returns:
        list: List of dictionaries with portfolio history data formatted for trading
    """
    _, _, page = driver_tuple
    
    # Scrape portfolio history (movements like Buy/Sell/Rebalance)
    history_data = scrape_portfolio_history(page, filter_last_friday=filter_to_recent)
    
    # Convert to format expected by trading system
    # The trading system expects: Symbol, Action (BUY/SELL)
    trading_data = []
    
    for entry in history_data:
        symbol = entry.get('symbol', '')
        action = entry.get('action', '').upper()
        change_weight = entry.get('change_weight', '0%')
        
        # Determine if we should BUY or SELL based on action and weight change
        if 'BUY' in action:
            trading_action = 'BUY'
        elif 'SELL' in action:
            trading_action = 'SELL'
        elif 'REBALANCE' in action:
            # For rebalance, determine action from weight change
            change_val = float(change_weight.replace('%', '').replace('+', ''))
            if change_val > 0.1:  # Threshold for buying more
                trading_action = 'BUY'
            elif change_val < -0.1:  # Threshold for selling
                trading_action = 'SELL'
            else:
                trading_action = 'HOLD'  # Minor rebalance, skip
        else:
            trading_action = 'HOLD'
        
        if trading_action in ['BUY', 'SELL']:
            trading_data.append({
                'Symbol': symbol,
                'Action': trading_action,
                'Weight': entry.get('new_weight', ''),
                'Change': change_weight,
                'Date': entry.get('date', '')
            })
    
    return trading_data


def get_portfolio_data_automated(scrape_type='current_picks', headless=True):
    """
    Automated function to scrape portfolio data without manual intervention.
    Use this function when calling from trading scripts.
    
    Args:
        scrape_type: 'current_picks', 'latest_history', or 'all_history'
        headless: Whether to run browser in headless mode
    
    Returns:
        list: Scraped data or None if error
    """
    driver_tuple = None
    try:
        # Setup browser
        driver_tuple = setup_driver(
            BROWSER_USER_DATA_DIR,
            BROWSER_PROFILE_NAME,
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION,
            headless=headless
        )
        
        playwright, context, page = driver_tuple
        
        # Check if login is needed (but don't prompt)
        needs_login = check_if_login_needed(page)
        
        if needs_login:
            print("⚠️  WARNING: Login required. Please run scraper.py manually first to log in.")
            return None
        
        # Scrape based on type
        if scrape_type == 'current_picks':
            page.goto(CURRENT_PICKS_URL, wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(2000)
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


def test_html_parsing():
    """
    Test HTML parsing with a sample file.
    """
    print("=== Test Mode: HTML Parsing ===")
    print("This function is for testing purposes.")
    print("Place your HTML sample in a file and modify this function to test parsing.")


def main():
    """
    Main function for testing the scraper independently.
    """
    import sys
    
    driver_tuple = None
    try:
        # Setup browser
        print("Setting up Playwright browser...")
        driver_tuple = setup_driver(
            BROWSER_USER_DATA_DIR,
            BROWSER_PROFILE_NAME,
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION
        )
        
        playwright, context, page = driver_tuple
        
        # Check if login is needed
        print("\n=== Checking Login Status ===")
        needs_login = check_if_login_needed(page)
        
        if needs_login:
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
            
            # Verify login was successful
            print("\nVerifying login...")
            page.goto(CURRENT_PICKS_URL, timeout=30000)
            page.wait_for_timeout(2000)
            
            # Check both table selectors
            has_table = (page.locator('tbody[data-test-id="table-body"]').count() > 0 or 
                        page.locator('tbody[data-test-id="table-body-infinite"]').count() > 0)
            
            if not has_table:
                print("\n⚠️  WARNING: Could not detect table. Make sure you're logged in.")
                print("Continuing anyway (automated mode)...")
        else:
            print("✓ Already logged in! Session restored from previous run.\n")
        
        # Check if user wants to scrape current picks or history
        print("\n=== Seeking Alpha Pro Quant Portfolio Scraper ===")
        print("1. Scrape Current Picks")
        print("2. Scrape Portfolio History (latest movements)")
        print("3. Scrape Portfolio History (all)")
        
        if len(sys.argv) > 1:
            choice = sys.argv[1]
        else:
            choice = input("\nEnter choice (1/2/3): ").strip()
        
        if choice == '1':
            # Scrape current picks
            print("\n=== SCRAPING CURRENT PICKS ===")
            # Navigate to the page
            page.goto(CURRENT_PICKS_URL, wait_until='networkidle', timeout=60000)
            page.wait_for_timeout(2000)
            picks_data = scrape_current_picks(page, navigate=False)
            
            if picks_data:
                print("\n=== CURRENT PICKS DATA ===")
                for i, item in enumerate(picks_data, 1):
                    print(f"\n--- Pick {i} ---")
                    print(f"Company: {item.get('company', 'N/A')}")
                    print(f"Symbol: {item.get('symbol', 'N/A')}")
                    print(f"Picked Price: {item.get('picked_price', 'N/A')}")
                    print(f"Sector: {item.get('sector', 'N/A')}")
                    print(f"Weight: {item.get('weight', 'N/A')}")
                    print(f"Quant Rating: {item.get('quant_rating', 'N/A')}")
                    print(f"Price Return: {item.get('price_return', 'N/A')}")
            else:
                print("\nNo picks scraped.")
        
        elif choice == '2':
            # Scrape latest portfolio history
            print("\n=== SCRAPING LATEST PORTFOLIO HISTORY ===")
            history_data = scrape_portfolio_history(page, filter_last_friday=True)
            
            if history_data:
                print("\n=== PORTFOLIO HISTORY DATA (LATEST) ===")
                for i, item in enumerate(history_data, 1):
                    print(f"\n--- Movement {i} ---")
                    print(f"Symbol: {item.get('symbol', 'N/A')}")
                    print(f"Date: {item.get('date', 'N/A')}")
                    print(f"Action: {item.get('action', 'N/A')}")
                    print(f"Starting Weight: {item.get('starting_weight', 'N/A')}")
                    print(f"New Weight: {item.get('new_weight', 'N/A')}")
                    print(f"Change: {item.get('change_weight', 'N/A')}")
                    print(f"Price/Share: {item.get('price_share', 'N/A')}")
            else:
                print("\nNo history scraped.")
        
        elif choice == '3':
            # Scrape all portfolio history
            print("\n=== SCRAPING ALL PORTFOLIO HISTORY ===")
            history_data = scrape_portfolio_history(page, filter_last_friday=False)
            
            if history_data:
                print("\n=== PORTFOLIO HISTORY DATA (ALL) ===")
                print(f"Total movements: {len(history_data)}")
                for i, item in enumerate(history_data[:10], 1):  # Show first 10
                    print(f"\n--- Movement {i} ---")
                    print(f"Symbol: {item.get('symbol', 'N/A')}")
                    print(f"Date: {item.get('date', 'N/A')}")
                    print(f"Action: {item.get('action', 'N/A')}")
                    print(f"Change: {item.get('change_weight', 'N/A')}")
                if len(history_data) > 10:
                    print(f"\n... and {len(history_data) - 10} more movements")
            else:
                print("\nNo history scraped.")
        
        else:
            print("Invalid choice. Exiting.")
        
        # Auto-close browser (for automation)
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

