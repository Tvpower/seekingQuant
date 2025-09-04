
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
BROWSER_PROFILE_PATH = r"PASTE_YOUR_BRAVE_PROFILE_PATH_HERE"

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

    options.add_argument("--start-maximized")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-pop-blocking")

    print(f"Using brower's profile path: {profile_path}")
    print(f"Using brower's executable path: {executable_path}")

    # We still use ChomeDriverManager because Brave is based on chronium this might change tho
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

