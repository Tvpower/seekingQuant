# Setup Instructions

## Environment Configuration

All sensitive IBKR configuration is now stored in `.env` file (not tracked in git).

### Quick Setup

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your actual values:**
   ```bash
   nano .env  # or use your preferred editor
   ```

3. **Configure your IBKR settings:**
   ```env
   # IBKR Configuration
   IBKR_PORT=7497              # 7497 for paper trading, 7496 for live
   IBKR_CLIENT_ID=YOUR_ID      # Your IBKR client ID

   # Trading Configuration
   TRADE_AMOUNT=500
   TARGET_VALUE_PER_STOCK=500
   ```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `IBKR_PORT` | IBKR TWS/Gateway port (7497=paper, 7496=live) | 7497 |
| `IBKR_CLIENT_ID` | Your IBKR client ID | 0 |
| `TRADE_AMOUNT` | Dollar amount per trade | 500 |
| `TARGET_VALUE_PER_STOCK` | Target value for rebalancing | 500 |

### Security Notes

- ✅ `.env` is in `.gitignore` - your credentials won't be committed
- ✅ Use `.env.example` as a template for sharing configuration
- ⚠️ Never commit `.env` to version control
- ⚠️ Use paper trading (port 7497) for testing

### Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your settings
```

### Switching Between Paper and Live Trading

Simply change `IBKR_PORT` in `.env`:
- **Paper Trading**: `IBKR_PORT=7497`
- **Live Trading**: `IBKR_PORT=7496`

⚠️ **Always test with paper trading first!**

