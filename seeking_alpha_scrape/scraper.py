import time
import sys
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pandas as pd




def prompt_if_tty(message: str) -> str:
    """Prompt user only if running in an interactive TTY; otherwise skip."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return input(message)
        # non-interactive context: skip prompt
        print(f"{message} [skipped: non-interactive]")
        return ""
    except Exception:
        # in case stdin is closed or any error occurs, skip
        return ""

# --- User config ---
# 1. Path to your Browser user data directory (parent of profile folders).
#    Linux example: "/home/username/.config/BraveSoftware/Brave-Browser"
BROWSER_USER_DATA_DIR = r"/home/tvpower/.config/BraveSoftware/Brave-Browser"

# 2. Profile directory name (usually "Default" for main profile)
BROWSER_PROFILE_NAME = "Default"

# 3. Path to the browser executable file.
#    Linux example: "/opt/brave.com/brave/brave"
BROWSER_EXECUTABLE_PATH = r"/opt/brave.com/brave/brave"

# 4. Option to connect to existing browser session (recommended)
USE_EXISTING_SESSION = False
REMOTE_DEBUGGING_PORT = 9222


def setup_driver(user_data_dir, profile_name, executable_path, use_existing=True, debug_port=9222):
    """ Setup the Selenium webdriver instance with a given profile. """
    if not user_data_dir or not os.path.isdir(user_data_dir):
        raise FileNotFoundError(f"browser's user data directory not found: {user_data_dir}")
    if not executable_path or not os.path.isfile(executable_path):
        raise FileNotFoundError(f"browser's executable path not found: {executable_path}")

    options = uc.ChromeOptions()
    options.binary_location = executable_path

    if use_existing:
        # Connect to existing browser session
        options.add_argument(f"--remote-debugging-port={debug_port}")
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        print(f"Attempting to connect to existing browser on port {debug_port}")
        print("Make sure Brave is running with: brave --remote-debugging-port=9222")
    else:
        # Start new browser with profile
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_name}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")  # save server resources
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-web-security")  # helps with some compatibility issues
        options.add_argument("--disable-features=VizDisplayCompositor")  # compatibility fix

    print(f"Using browser's user data directory: {user_data_dir}")
    print(f"Using browser's profile: {profile_name}")
    print(f"Using browser's executable path: {executable_path}")

    try:
        if use_existing:
            # For existing session, we don't need version matching
            print("Connecting to existing browser session...")
            driver = uc.Chrome(options=options)
            return driver
        else:
            # Method 1: Try with specific version matching your browser (139)
            print("Attempting to create driver with version 139...")
            driver = uc.Chrome(options=options, version_main=139)
            return driver
    except Exception as e:
        if use_existing:
            print(f"clearto existing session: {e}")
            print("Make sure Brave is running with: brave --remote-debugging-port=9222")
            print("Or set USE_EXISTING_SESSION = False to start a new browser instance")
            raise
        else:
            print(f"Version 139 failed: {e}")

            try:
                # Method 2: Clear cache and retry with version 139
                import shutil
                cache_dir = os.path.expanduser("~/.local/share/undetected_chromedriver")
                if os.path.exists(cache_dir):
                    print("Clearing ChromeDriver cache...")
                    shutil.rmtree(cache_dir)

                print("Retrying with version 139 after cache clear...")
                driver = uc.Chrome(options=options, version_main=139)
                return driver
            except Exception as e2:
                print(f"Cache clear and version 139 failed: {e2}")

                try:
                    # Method 3: Let undetected-chromedriver auto-download compatible version
                    print("Attempting auto version detection...")
                    driver = uc.Chrome(options=options, version_main=None)
                    return driver
                except Exception as e3:
                    print(f"Auto version detection failed: {e3}")
                    raise Exception("All ChromeDriver initialization methods failed")


def get_last_friday():
    """Get the date of the last Friday before today"""
    today = datetime.now()
    # Calculate days back to Friday (weekday 4)
    days_back = (today.weekday() - 4) % 7
    if days_back == 0 and today.weekday() == 4:
        # If today is Friday, use today
        last_friday = today
    else:
        # Otherwise, go back to the most recent Friday
        if days_back == 0:
            days_back = 7
        last_friday = today - timedelta(days=days_back)
    
    return last_friday.strftime("%-m/%-d/%Y")  # Format like "9/5/2025"


def scrape_portfolio_data(driver, filter_to_recent=True):
    """Go to the QUANT PRO portfolio page and scrape the data stock data"""
    portfolio_url = "https://seekingalpha.com/pro-quant-portfolio/portfolio-history"  # placeholder for now need to update with actual url
    driver.get(portfolio_url)
    print(f"Navigating to {portfolio_url}")

    # Initial short wait for page navigation; specific table waits occur below
    time.sleep(1)

    # Check if we're logged in by looking for common login indicators
    try:
        # Check current URL to see if we were redirected to login
        current_url = driver.current_url
        print(f"Current URL: {current_url}")

        if "login" in current_url.lower() or "signin" in current_url.lower():
            print("⚠️  Appears to be redirected to login page. You may need to log in manually.")
            input("Please log in manually in the browser window, then press Enter to continue...")
    except Exception as e:
        print(f"Could not check login status: {e}")

    holdings_data = []
    
    # Get the target date for filtering
    target_date = get_last_friday() if filter_to_recent else None
    if filter_to_recent:
        print(f"Filtering data for last Friday: {target_date}")

    try:
        # Try multiple table body selectors to handle different page formats
        table_body_selectors = [
            'tbody[data-test-id="table-body-infinite"]',  # Format used in example.html
            'tbody[data-test-id="table-body"]'            # Format used in debug_page_source.html
        ]
        
        table_body_selector = None
        for selector in table_body_selectors:
            try:
                print(f"Trying table selector: {selector}")
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                table_body_selector = selector
                print(f"Found table with selector: {table_body_selector}")
                break
            except:
                print(f"Selector {selector} not found, trying next...")
                continue
        
        if not table_body_selector:
            raise Exception("Could not find table with any of the expected selectors")
        
        print("Portfolio holdings table is visible.")

        # need to add this delay to make sure all the dynamic content loads
        time.sleep(5)

        rows = driver.find_elements(By.CSS_SELECTOR, f"{table_body_selector} tr")

        if not rows:
            print("Couldn't find any rows in the table. Page structure might have changed.")
            print("Let's check what's actually on the page...")
            print("Page title:", driver.title)
            # Save screenshot for debugging
            try:
                driver.save_screenshot("debug_screenshot.png")
                print("Screenshot saved as debug_screenshot.png")
            except:
                pass
            return None

        print(f"Found {len(rows)} rows in the table. Extracting data...")

        # Batch collect cells for all rows once
        rows_cells = [row.find_elements(By.CSS_SELECTOR, "th, td") for row in rows]

        def extract_symbol(cells):
            try:
                if not cells:
                    return None
                # Try common locations/selectors first
                for idx in [0, 1]:
                    if idx < len(cells):
                        try:
                            el = cells[idx].find_element(By.CSS_SELECTOR, '[data-test-id="portfolio-ticker-link"]')
                            text = el.text.strip()
                            if text:
                                return text
                        except:
                            pass
                # Fallback: any anchor text
                for idx in [0, 1]:
                    if idx < len(cells):
                        try:
                            el = cells[idx].find_element(By.CSS_SELECTOR, 'a')
                            text = el.text.strip()
                            if text:
                                return text
                            href = el.get_attribute('href') or ''
                            if '/symbol/' in href:
                                return href.split('/symbol/')[1].split('#')[0].split('?')[0]
                        except:
                            pass
                return None
            except:
                return None

        def extract_date(cells):
            try:
                for cell in cells:
                    text = (cell.text or '').strip()
                    if '/' in text and any(ch.isdigit() for ch in text):
                        try:
                            datetime.strptime(text, "%m/%d/%Y")
                            return text
                        except:
                            continue
                return None
            except:
                return None

        def extract_price(cells):
            try:
                # Pattern-based
                for cell in cells:
                    text = (cell.text or '').strip()
                    if '$' in text and '.' in text and '%' not in text:
                        return text
                # Positional fallback
                if len(cells) > 6:
                    return (cells[6].text or '').strip()
                return "N/A"
            except:
                return "N/A"

        def extract_weight(cells):
            try:
                for cell in cells:
                    text = (cell.text or '').strip()
                    if '%' in text and '$' not in text and '/' not in text:
                        return text
                for idx in [3, 4, 5]:
                    if idx < len(cells):
                        text = (cells[idx].text or '').strip()
                        if '%' in text and '/' not in text:
                            return text
                return "N/A"
            except:
                return "N/A"

        def extract_action(cells):
            try:
                for cell in cells:
                    text = (cell.text or '').strip()
                    if text in ['Buy', 'Sell', 'Rebalance']:
                        return text
                return "N/A"
            except:
                return "N/A"

        # Parallel extraction
        with ThreadPoolExecutor(max_workers=4) as executor:
            symbol_futures = [executor.submit(extract_symbol, cells) for cells in rows_cells]
            date_futures = [executor.submit(extract_date, cells) for cells in rows_cells]
            price_futures = [executor.submit(extract_price, cells) for cells in rows_cells]
            weight_futures = [executor.submit(extract_weight, cells) for cells in rows_cells]
            action_futures = [executor.submit(extract_action, cells) for cells in rows_cells]

            symbols = [f.result() for f in symbol_futures]
            dates = [f.result() for f in date_futures]
            prices = [f.result() for f in price_futures]
            weights = [f.result() for f in weight_futures]
            actions = [f.result() for f in action_futures]

        for idx, cells in enumerate(rows_cells):
            symbol = symbols[idx]
            if not symbol:
                continue
            row_date = dates[idx]
            if filter_to_recent and target_date and row_date != target_date:
                continue
            holding = {
                'Symbol': symbol,
                'Date': row_date or "N/A",
                'Action': actions[idx] or "N/A",
                'Weight': weights[idx] or "N/A",
                'Price': prices[idx] or "N/A"
            }
            holdings_data.append(holding)
    except Exception as e:
        print(f"Error while scraping: {e}")
        print("Let's see what's on the page...")
        print("Page title:", driver.title)
        print("Current URL:", driver.current_url)
        # Save screenshot and page source for debugging
        try:
            driver.save_screenshot("error_screenshot.png")
            print("Screenshot saved as error_screenshot.png")
        except:
            pass
        try:
            with open("test_data/debug_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Page source saved as debug_page_source.html")
        except:
            pass
        return None

    return holdings_data


def test_html_parsing():
    """Test function to validate HTML parsing with local files"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import os
    
    # Set up a basic Chrome driver for testing
    options = Options()
    options.add_argument('--headless')  # Run in background
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=options)
        
        # Test both HTML files
        test_files = [
            ('example.html', '/home/tvpower/CLionProjects/seekingQuant/seeking-alpha-scrape/example.html'),
            ('debug_page_source.html', '/home/tvpower/CLionProjects/seekingQuant/seeking-alpha-scrape/debug_page_source.html')
        ]
        
        for file_name, file_path in test_files:
            if os.path.exists(file_path):
                print(f"\n=== Testing {file_name} ===")
                driver.get(f"file://{file_path}")
                
                # Use the same logic as scrape_portfolio_data but simplified
                holdings_data = []
                
                # Try multiple table body selectors
                table_body_selectors = [
                    'tbody[data-test-id="table-body-infinite"]',
                    'tbody[data-test-id="table-body"]'
                ]
                
                table_body_selector = None
                for selector in table_body_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            table_body_selector = selector
                            print(f"Found table with selector: {table_body_selector}")
                            break
                    except:
                        continue
                
                if table_body_selector:
                    rows = driver.find_elements(By.CSS_SELECTOR, f"{table_body_selector} tr")
                    print(f"Found {len(rows)} rows")
                    
                    for i, row in enumerate(rows[:3]):  # Test first 3 rows only
                        cells = row.find_elements(By.CSS_SELECTOR, "th, td")
                        if len(cells) >= 2:
                            # Extract symbol
                            try:
                                symbol_element = cells[1].find_element(By.CSS_SELECTOR, '[data-test-id="portfolio-ticker-link"]')
                                symbol = symbol_element.text.strip()
                                print(f"Row {i}: Symbol = {symbol}")
                            except:
                                print(f"Row {i}: Could not extract symbol")
                else:
                    print("No table found with expected selectors")
            else:
                print(f"{file_name} not found at {file_path}")
        
        driver.quit()
        print("\n=== Test completed ===")
        
    except Exception as e:
        print(f"Test failed: {e}")
        print("Note: This test requires chromedriver. Run the main scraper for full functionality.")


if __name__ == "__main__":
    import sys
    
    # Check if test mode is requested
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_html_parsing()
        sys.exit(0)
    
    # Check for --all flag to disable date filtering
    filter_to_recent = "--all" not in sys.argv
    
    if USE_EXISTING_SESSION:
        print("=" * 60)
        print("USING EXISTING BROWSER SESSION")
        print("Please start Brave with remote debugging enabled:")
        print("brave --remote-debugging-port=9222")
        print("=" * 60)
        prompt_if_tty("Press Enter once Brave is running with the above command...")
    else:
        prompt_if_tty("Please ensure all browser windows are closed, then press enter to continue...")
    
    try:
        driver = setup_driver(
            BROWSER_USER_DATA_DIR, 
            BROWSER_PROFILE_NAME, 
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION,
            REMOTE_DEBUGGING_PORT
        )
        try:
            portfolio = scrape_portfolio_data(driver, filter_to_recent=filter_to_recent)
            if portfolio:
                df = pd.DataFrame(portfolio)
                print("\n--- scraped portfolio data ---")
                print(df.to_string())
                print("\n" + "=" * 30)
            else:
                print("\nCouldn't retrieve portfolio data. Check that you are logged in to Seeking Alpha")

        finally:
            if not USE_EXISTING_SESSION:
                print("\nClosing the browser.")
                driver.quit()
            else:
                print("\nScript completed. Browser session remains open.")
    except Exception as e:
        print(f"Failed to initialize driver: {e}")
        print("\nTroubleshooting:")
        if USE_EXISTING_SESSION:
            print("1. Make sure Brave is running with: brave --remote-debugging-port=9222")
            print("2. Or set USE_EXISTING_SESSION = False to start a new browser instance")
        else:
            print("1. Check browser paths are correct")
            print("2. Try setting USE_EXISTING_SESSION = True")