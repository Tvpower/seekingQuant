## Seeking Alpha Quant Portfolio Scraper & Automated Trading System

Playwright-based scraper for Seeking Alpha Pro Quant Portfolio with IBKR integration for automated trading. Supports multiple table formats, persistent login sessions, and fully automated execution.

### Features
- **Persistent Sessions**: Login once, reuse session across runs (saved in `~/.playwright_seeking_alpha_profile`)
- **Multiple Table Support**: Handles both `table-body-infinite` and `table-body` selectors with fallback logic
- **Three Scraping Modes**:
  - Current picks (all 30 stocks in portfolio)
  - Latest portfolio movements (most recent date only)
  - All portfolio history
- **Anti-Bot Detection**: Stealth techniques to bypass automation detection
- **Automated Trading**: Direct integration with Interactive Brokers (IBKR) for automated order execution
- **Headless Mode**: Run completely in background for cron jobs/automation
- **Manual Mode**: Visual browser for initial login and debugging

### Requirements
- Python 3.8+
- Interactive Brokers account (for trading integration)
- Seeking Alpha Pro subscription

Python dependencies (see `requirements.txt`):
- playwright
- pandas
- ibapi (Interactive Brokers API)

### Installation

1) Create and activate virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Install Playwright browsers
```bash
playwright install chromium
```

3) Configure IBKR connection in `main.py`
```python
TRADE_AMOUNT = 500          # Dollar amount per trade
IBKR_PORT = 7497           
IBKR_CLIENT_ID = 0         # Your client ID
```

### First-Time Setup

**Login to Seeking Alpha (one-time setup):**
```bash
python seeking_alpha_scrape/scraper.py 1
```

This will:
1. Open a browser window
2. Navigate to Seeking Alpha
3. Prompt you to login with your credentials
4. Save the session to `~/.playwright_seeking_alpha_profile`

After successful login, the scraper will run in automated/headless mode for all future runs.

### Usage

#### Standalone Scraper (Manual Testing)

```bash
# Scrape current picks (30 stocks)
python seeking_alpha_scrape/scraper.py 1

# Scrape latest portfolio movements
python seeking_alpha_scrape/scraper.py 2

# Scrape all portfolio history
python seeking_alpha_scrape/scraper.py 3
```

#### Automated Trading (Headless)

```bash
# Default: scrape latest movements and execute trades
python main.py

# Use current portfolio picks for trading
python main.py --current

# Use all history movements for trading
python main.py --all
```

#### Execute Seeking Alpha Trades (New Utility)

Automatically scrape latest Seeking Alpha movements and execute trades:

```bash
# Default: Execute trades with primary account
python utils/execute_seeking_alpha_trades.py

# Specify account
python utils/execute_seeking_alpha_trades.py --account U1234567

# Use limit orders instead of market orders
python utils/execute_seeking_alpha_trades.py --limit

# Run in headless mode (no browser UI)
python utils/execute_seeking_alpha_trades.py --headless

# Combined options
python utils/execute_seeking_alpha_trades.py --account U1234567 --limit --headless
```

**How it works:**
1. Scrapes latest portfolio movements from Seeking Alpha (up to last Friday)
2. Executes **BUY** orders first ($500 each)
3. Then executes **SELL** orders (closes positions completely at market value)
4. Generates a detailed report in `reports/` directory

#### Programmatic Integration

```python
from seeking_alpha_scrape.scraper import get_portfolio_data_automated

# Get current picks (headless, fully automated)
picks = get_portfolio_data_automated('current_picks', headless=True)

# Get latest movements
movements = get_portfolio_data_automated('latest_history', headless=True)

# Get all history
history = get_portfolio_data_automated('all_history', headless=True)
```

### Pages Supported

- **Current Picks**: `https://seekingalpha.com/pro-quant-portfolio/picks/current`
  - All 30 stocks currently in the Pro Quant Portfolio
  - Columns: Company, Symbol, Picked Price, Sector, Weight, Quant Rating, Price Return

- **Portfolio History**: `https://seekingalpha.com/pro-quant-portfolio/portfolio-history`
  - Buy/Sell/Rebalance movements
  - Columns: Symbol, Date, Action, Starting Weight, New Weight, Change In Weight, Price/Share

### How It Works

#### Scraping Process
1. **Browser Launch**: Playwright launches Chromium with persistent context
2. **Session Restoration**: Loads saved cookies/session from profile directory
3. **Login Check**: Automatically detects if login is valid by checking for table presence
4. **Data Extraction**: Parses table rows using selectors:
   - `tbody[data-test-id="table-body-infinite"]` (primary)
   - `tbody[data-test-id="table-body"]` (fallback)
5. **Data Processing**: Extracts and formats data for trading system

#### Trading Integration
1. **Scrape**: Get latest portfolio movements
2. **Convert**: Transform movements to BUY/SELL actions
3. **Connect**: Establish connection to IBKR via TWS/Gateway
4. **Execute**: Place dollar-based market orders for each action
5. **Disconnect**: Clean up connection

#### Anti-Detection Features
- Overrides `navigator.webdriver` property
- Custom user agent
- Disables automation flags
- Mimics real browser behavior
- Persistent profile with real browsing history

### Configuration

Located in `seeking_alpha_scrape/scraper.py`:

```python
TEMP_PROFILE_DIR = "~/.playwright_seeking_alpha_profile"  # Session storage
CURRENT_PICKS_URL = "https://seekingalpha.com/pro-quant-portfolio/picks/current"
PORTFOLIO_HISTORY_URL = "https://seekingalpha.com/pro-quant-portfolio/portfolio-history"
```

Located in `main.py`:

```python
TRADE_AMOUNT = 500      # Dollar amount per trade
IBKR_PORT = 7497       # 7497 paper, 7496 live
IBKR_CLIENT_ID = 0     # Your IBKR client ID
```

### Output Format

#### Current Picks
```
Company, Symbol, Picked Price, Sector, Weight, Quant Rating, Price Return
```

#### Portfolio History (Latest)
```
Symbol, Date, Action, Starting Weight, New Weight, Change In Weight, Price/Share
```

#### Trading Format (Converted)
```
Symbol, Action (BUY/SELL), Weight, Change, Date
```

### Troubleshooting

**Login Required Warning**
- Run `python seeking_alpha_scrape/scraper.py 1` manually to login
- Ensure you can see the portfolio table before pressing Enter

**Table Not Found**
- Check if Seeking Alpha changed their HTML structure
- Verify your Pro subscription is active
- Try clearing profile: `rm -rf ~/.playwright_seeking_alpha_profile`

**IBKR Connection Failed**
- Ensure TWS or IB Gateway is running
- Check port configuration (7497 for paper trading)
- Verify client ID is not already in use
- Enable API connections in TWS settings

**Playwright Errors**
- Reinstall browsers: `playwright install chromium`
- Check permissions on profile directory

**Headless Mode Not Working**
- Some sites detect headless mode; try with `headless=False` for debugging
- Check if profile directory has proper permissions

### Project Structure

```
SeekingQuant/
├── main.py                                    # Main trading orchestration
├── requirements.txt                           # Python dependencies
├── README.md                                  # This file
├── seeking_alpha_scrape/
│   ├── scraper.py                             # Playwright scraper with automation
│   └── html-sample/                           # Sample HTML for testing
├── trade_dirs/
│   └── trader.py                              # IBKR API integration
├── utils/
│   ├── trading_common.py                      # Common utilities (symbols, connections, reports)
│   ├── execute_seeking_alpha_trades.py        # Auto-execute Seeking Alpha trades
│   ├── rebalance_from_file.py                 # Rebalance portfolio from file
│   ├── rebalance_500.py                       # Rebalance portfolio to equal weights
│   └── buy_portfolio.py                       # Buy entire portfolio
└── reports/                                   # Trading reports directory
```

### Common Utilities Module

The `utils/trading_common.py` module provides shared functions to eliminate code duplication:

**Symbol Normalization:**
- `normalize_symbol()` - Standardize symbol format
- `ibkr_symbol()` - Convert to IBKR format

**IBKR Connection:**
- `connect_to_ibkr()` - Connect to Interactive Brokers
- `disconnect_from_ibkr()` - Safely disconnect

**Account Management:**
- `get_available_accounts()` - Fetch available accounts
- `select_account()` - Interactive account selection

**Report Generation:**
- `generate_trade_report()` - Universal report generator

**Utilities:**
- `parse_trading_args()` - Parse command line arguments
- `print_header()`, `print_section()` - Formatted output
- `confirm_action()` - User confirmation prompts

See `utils/README_REFACTORING.md` for detailed refactoring information.

### Automation with Cron

Run daily at market close:

```bash
# Add to crontab
0 16 * * 1-5 cd /home/user/PycharmProjects/SeekingQuant && .venv/bin/python main.py >> logs/trading.log 2>&1
```

### Notes

- Respect Seeking Alpha's Terms of Service
- Use paper trading account for testing
- Monitor trades carefully in production
- This is for educational/personal use only
- Past performance does not guarantee future results


