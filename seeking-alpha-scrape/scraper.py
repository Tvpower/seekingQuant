
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import os


# --- User config ---
# 1. Path to your Browser user profile data directory.
#    Windows example: r"C:\Users\YourUsername\AppData\Local\BraveSoftware\Brave-Browser\User Data"
#    macOS example:   "/Users/YourUsername/Library/Application Support/BraveSoftware/Brave-Browser"
BROWSER_PROFILE_PATH = r""

# 2. Path to the browser executable file.
#    Windows example: r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
#    macOS example:   "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
BROWSER_EXECUTABLE_PATH = r"PASTE_YOUR_BRAVE_EXECUTABLE_PATH_HERE"


def setup_driver(profile_path, executable_path):
    """ Setup the Selenium webdriver instance with a given profile. """
    if not profile_path or not os.path.isdir(profile_path):
        raise FileNotFoundError(f"brower's profile path not found: {profile_path}")
    if not executable_path or not os.path.isfile(executable_path):
        raise FileNotFoundError(f"brower's executable path not found: {executable_path}")

    options = webdriver.ChromeOptions()

    options.binary_location = executable_path

    options.add_argument(f"user-data-dir={profile_path}") #use local browser profile
    options.add_argument("--start-maximized")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu") #save server resources
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-pop-blocking")

    print(f"Using brower's profile path: {profile_path}")
    print(f"Using brower's executable path: {executable_path}")

    # We still use ChomeDriverManager because Brave is based on chronium this might change tho
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_portfolio_data(driver):
    """Go to the QUANT PRO portfolio page and scrape the data stock data"""
    portfolio_url = "https://seekingalpha.com/pro-quant-portfolio/picks/current" # placeholder for now need to update with actual url
    driver.get(portfolio_url)
    print(f"Navigating to {portfolio_url}")

    holdings_data = []

    try:
        # wait for the main holding table container to be visible
        table_body_selector = 'tbody[data-testid="table-body-infinite"]'
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, table_body_selector))
        )
        print("Portfolio holdings table is visible.")

        #need to add this delay to make sure all the dynamic content loads
        time.sleep(5)

        rows = driver.find_elements(By.CSS_SELECTOR, f"{table_body_selector} tr")

        if not rows:
            print("Couldn't find any rows in the table. Page structure might have changed.")
            return None

        print(f"Found {len(rows)} rows in the table. Extracting data...")

        for row in rows:
            # get all cells in the row. the first is a <th>, the rest are <td>
            cells = row.find_elements(By.CSS_SELECTOR, "th ,td")

            # this ensures the row has enough cells to prevent errors
            if len(cells) >= 6:
                try:
                    #col 2: symbol
                    symbol = cells[1].find_element(By.CSS_SELECTOR,
                                                   '[data-test-id="portfolio-ticker-name"]').text.strip()
                    #col 4: price
                    price = cells[3].text.strip()

                    #col 6: weight
                    weight = cells[5].text.strip()
                    #extra info from the table
                    holding = {
                        'Symbol': symbol,
                        'Price': price,
                        'Weight': weight
                    }
                    holdings_data.append(holding)
                except Exception as cell_err:
                    print(f"Could not process a row, skipping. Error: {cell_err}")
                    return None
    except Exception as e:
        print(f"YOU DID SOMETHING WRONG WHLE SCRAPPING YOU ASSHOLE: {e}")
        return None

    return holdings_data

if __name__ == "__main__":
    if BROWSER_PROFILE_PATH not in os.environ:
        print("=" * 60)
        print("BROWSER_PROFILE_PATH environment variable not set")
        print("=" * 60)
    else:
        input("Please ensure all browser windows are closed, then press enter to continue...")
        driver = setup_driver(BROWSER_PROFILE_PATH, BROWSER_EXECUTABLE_PATH)
        try:
            portfolio = scrape_portfolio_data(driver)
            if portfolio:
                df = pd.DataFrame(portfolio)
                print("\n--- scraped portfolio data ---")
                print(df.to_string())
                print("\n====BLAHEHEH HEH HEHE=========")
            else:
                print("\nCouldn't retrieve portfolio data. Check that you are logged in brave browser")

        finally:
            print("\nClosing the browser.")
            driver.quit()