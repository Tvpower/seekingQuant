import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import os

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


def scrape_portfolio_data(driver):
    """Go to the QUANT PRO portfolio page and scrape the data stock data"""
    portfolio_url = "https://seekingalpha.com/pro-quant-portfolio/picks/current"  # placeholder for now need to update with actual url
    driver.get(portfolio_url)
    print(f"Navigating to {portfolio_url}")

    # Wait a bit for the page to load
    time.sleep(3)

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

    try:
        # wait for the main holding table container to be visible
        table_body_selector = 'tbody[data-test-id="table-body-infinite"]'
        print(f"Looking for table with selector: {table_body_selector}")

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, table_body_selector))
        )
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

        for i, row in enumerate(rows):
            # get all cells in the row. the first is a <th>, the rest are <td>
            cells = row.find_elements(By.CSS_SELECTOR, "th, td")

            # this ensures the row has enough cells to prevent errors
            if len(cells) >= 6:
                try:
                    # Debug: Print row structure for first few rows
                    if i < 3:
                        print(f"\n--- Debug Row {i} ---")
                        print(f"Number of cells: {len(cells)}")
                        for j, cell in enumerate(cells):
                            print(f"Cell {j}: tag={cell.tag_name}, text='{cell.text[:50]}...', innerHTML preview='{cell.get_attribute('innerHTML')[:100]}...'")
                    
                    # Extract ticker symbol from Cell 1 (which contains the ticker)
                    symbol = None
                    
                    # Method 1: Try portfolio-ticker-link in cell 1
                    try:
                        symbol_element = cells[1].find_element(By.CSS_SELECTOR, '[data-test-id="portfolio-ticker-link"]')
                        symbol = symbol_element.text.strip()
                    except:
                        pass
                    
                    # Method 2: Try any <a> tag in cell 1
                    if not symbol:
                        try:
                            symbol_element = cells[1].find_element(By.CSS_SELECTOR, 'a')
                            symbol = symbol_element.text.strip()
                        except:
                            pass
                    
                    # Method 3: Extract from href if text is empty
                    if not symbol:
                        try:
                            symbol_element = cells[1].find_element(By.CSS_SELECTOR, 'a')
                            href = symbol_element.get_attribute('href')
                            if '/symbol/' in href:
                                symbol = href.split('/symbol/')[1].split('#')[0].split('?')[0]
                        except:
                            pass
                    
                    # Method 4: Just get all text from cell 1
                    if not symbol:
                        symbol = cells[1].text.strip()
                    
                    if not symbol:
                        print(f"Row {i}: Could not extract symbol, skipping")
                        continue
                    
                    # col 4: price (index 3)
                    price = cells[3].text.strip()

                    # col 6: weight (index 5)
                    weight = cells[5].text.strip()
                    
                    # extra info from the table
                    holding = {
                        'Symbol': symbol,
                        'Price': price,
                        'Weight': weight
                    }
                    holdings_data.append(holding)
                    
                except Exception as cell_err:
                    print(f"Row {i}: Could not process row. Error: {cell_err}")
                    # Save HTML of problematic row for debugging
                    try:
                        with open(f"debug_row_{i}.html", "w") as f:
                            f.write(row.get_attribute('outerHTML'))
                        print(f"Row {i}: HTML saved to debug_row_{i}.html")
                    except:
                        pass
                    continue
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
            with open("debug_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("Page source saved as debug_page_source.html")
        except:
            pass
        return None

    return holdings_data


if __name__ == "__main__":
    if USE_EXISTING_SESSION:
        print("=" * 60)
        print("USING EXISTING BROWSER SESSION")
        print("Please start Brave with remote debugging enabled:")
        print("brave --remote-debugging-port=9222")
        print("=" * 60)
        input("Press Enter once Brave is running with the above command...")
    else:
        input("Please ensure all browser windows are closed, then press enter to continue...")
    
    try:
        driver = setup_driver(
            BROWSER_USER_DATA_DIR, 
            BROWSER_PROFILE_NAME, 
            BROWSER_EXECUTABLE_PATH,
            USE_EXISTING_SESSION,
            REMOTE_DEBUGGING_PORT
        )
        try:
            portfolio = scrape_portfolio_data(driver)
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