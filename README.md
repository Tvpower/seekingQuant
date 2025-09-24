## Seeking Alpha Quant Portfolio Scraper

Minimal Selenium scraper for Seeking Alpha Quant Portfolio pages. It supports multiple table formats and can filter portfolio movements to just the most recent Friday.

### Features
- Handles multiple table structures (`table-body-infinite` and `table-body`) with fallback logic
- Robust ticker extraction from `portfolio-ticker-link`
- Extracts columns: `Symbol`, `Date`, `Action`, `Weight`, `Price`
- Optional filtering to only the last Friday before today
- Local HTML test mode for quick validation
- Saves debug artifacts on failure (screenshot and page source)

### Requirements
- Python 3.8+
- Google Chrome/Brave (project is set up for Brave)
- `chromedriver` compatible with your browser (handled by `undetected-chromedriver`)

Python deps (see `requirements.txt`):
- selenium
- undetected-chromedriver
- pandas

### Quick Start
1) Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure browser paths in `scraper.py`
- `BROWSER_USER_DATA_DIR` (e.g., `/home/<user>/.config/BraveSoftware/Brave-Browser`)
- `BROWSER_PROFILE_NAME` (usually `Default`)
- `BROWSER_EXECUTABLE_PATH` (e.g., `/opt/brave.com/brave/brave`)
- `USE_EXISTING_SESSION` (True to attach to a running browser; False to launch a new one)
- `REMOTE_DEBUGGING_PORT` (default `9222`)

3) If using an existing session, start Brave with remote debugging first
```bash
brave --remote-debugging-port=9222
``
# This was a test with a downloaded version of brave from snap which didnt work for me.

4) Run the scraper
```bash
# Default: scrapes current picks page
python scraper.py

# Disable date filtering / fetch all rows where applicable
python scraper.py --all
```

### Pages Supported
- Current picks (default):
  - `https://seekingalpha.com/pro-quant-portfolio/picks/current`
- Portfolio history (still supported by the scraper):
  - `https://seekingalpha.com/pro-quant-portfolio/portfolio-history`

Switch pages by changing `portfolio_url` in `scraper.py`.

### Output
- Prints a pandas DataFrame to stdout with the extracted data. Typical columns:
  - `Symbol`: stock ticker (e.g., W, NEM)
  - `Date`: transaction date (present on history pages)
  - `Action`: Buy/Sell/Rebalance (present on history pages)
  - `Weight`: portfolio weight or weight change (percentage)
  - `Price`: price per share (currency or numeric string)

### How It Works
- The scraper waits for one of these selectors (in order):
  - `tbody[data-test-id="table-body-infinite"]`
  - `tbody[data-test-id="table-body"]`
- It extracts rows and uses multiple strategies to obtain the ticker from the first cells via `data-test-id="portfolio-ticker-link"` or link `href`.
- It heuristically finds `Price`/`Weight` by content (e.g., `$`, `%`) and falls back to common column positions.

### Last Friday Filter
- By default the scraper filters rows to only the most recent Friday before today (relevant for the portfolio history page).
- Disable the filter with `--all`.

### Debug Artifacts
On errors, the scraper writes:
- `error_screenshot.png`: screenshot of the page
- `debug_page_source.html`: full HTML source
- `debug_row_*.html`: snippets of problematic rows (when encountered)

### Troubleshooting
- `python: command not found`: use `python3` and ensure your venv is activated
- Cannot attach to existing browser:
  - Ensure Brave is running with `--remote-debugging-port=9222`
  - Or set `USE_EXISTING_SESSION = False` to launch a new instance
- Driver initialization issues:
  - The code already retries with version hints and cache clear; verify your Brave/Chrome version if problems persist
- No rows found:
  - The page may have changed; inspect `debug_page_source.html` and adjust selectors

### Notes
- Respect Seeking Alpha’s Terms of Service when scraping.
- This project is intended for personal/educational purposes.


