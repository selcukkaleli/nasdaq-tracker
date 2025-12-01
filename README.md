# NASDAQ-100 Real-Time Stock Tracker

An automated system that tracks NASDAQ-100 stocks using Yahoo Finance API, stores real-time price data in SQLite, and sends email alerts when abnormal price drops are detected.

## Features

- Real-time price tracking for NASDAQ-100 stocks (every 10 minutes during market hours)
- Smart data storage: only saves when prices actually change
- All timestamps in EST (America/New_York) for consistency with NASDAQ trading hours
- Dual alert system: daily drops and intraday drops
- Email notifications for significant price movements
- Full automation via GitHub Actions
- Historical data accumulation for machine learning applications

## How It Works

The tracker runs every 10 minutes during NYSE/NASDAQ market hours (Mon-Fri, 09:30-16:00 EST) and:

1. Fetches current market prices from Yahoo Finance
2. Compares against previous close (daily drop detection)
3. Compares against last recorded price (intraday drop detection)
4. Saves only if price has changed (avoids duplicate data)
5. Sends email alert if drop exceeds threshold

The system automatically skips execution during weekends and outside market hours to conserve GitHub Actions minutes.

## Database Schema

### realtime_prices

Stores price snapshots taken every 10 minutes during market hours.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| symbol | TEXT | Stock ticker symbol |
| price | REAL | Current market price |
| previous_close | REAL | Previous day closing price |
| day_high | REAL | Current day high |
| day_low | REAL | Current day low |
| volume | INTEGER | Trading volume |
| market_cap | REAL | Market capitalization |
| market_state | TEXT | REGULAR, PRE, POST, or CLOSED |
| fetch_timestamp | DATETIME | When the data was fetched (EST) |

### fetch_logs

Tracks each fetch operation for monitoring.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| fetch_timestamp | DATETIME | Operation timestamp (EST) |
| fetch_type | TEXT | REALTIME, SKIPPED |
| market_state | TEXT | Market state at fetch time |
| symbols_fetched | INTEGER | Number of symbols processed |
| records_added | INTEGER | Records inserted (price changed) |
| records_skipped | INTEGER | Records skipped (price unchanged) |
| errors | TEXT | Any errors encountered |
| duration_seconds | REAL | Operation duration |

### alerts

Logs all triggered alerts.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| symbol | TEXT | Stock ticker symbol |
| alert_type | TEXT | DAILY_DROP or HOURLY_DROP |
| alert_message | TEXT | Description of the alert |
| price_change_percent | REAL | Percentage change |
| current_price | REAL | Price at alert time |
| previous_price | REAL | Reference price |
| created_at | DATETIME | Alert timestamp (EST) |
| email_sent | BOOLEAN | Whether email was sent |

## Installation

### 1. Fork or Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/nasdaq-tracker.git
cd nasdaq-tracker
```

### 2. Configure GitHub Secrets

Navigate to repository Settings, then Secrets and variables, then Actions. Add the following secrets:

| Secret Name | Description |
|-------------|-------------|
| EMAIL_SENDER | Sender email address (Gmail recommended) |
| EMAIL_PASSWORD | Gmail App Password (not your regular password) |
| EMAIL_RECIPIENT | Email address to receive alerts |

### 3. Create Gmail App Password

1. Go to Google Account and enable 2-Step Verification
2. Navigate to Security, then App passwords
3. Select Mail and Other, enter a name like "NASDAQ Tracker"
4. Copy the 16-character password and use it as EMAIL_PASSWORD

### 4. Configure Variables (Optional)

Navigate to repository Settings, then Secrets and variables, then Actions, then Variables tab:

| Variable Name | Default | Description |
|---------------|---------|-------------|
| DROP_THRESHOLD | 5.0 | Daily drop threshold percentage |
| HOURLY_DROP_THRESHOLD | 3.0 | Intraday drop threshold percentage |

## Usage

### Automatic Execution

GitHub Actions runs the tracker every 10 minutes during market hours:

- Schedule: Every 10 minutes, Monday-Friday, 09:30-16:00 EST (14:30-21:00 UTC)
- Skips weekends and outside market hours automatically

### Manual Execution

1. Go to the Actions tab in your repository
2. Select "NASDAQ Tracker" workflow
3. Click "Run workflow"

### Local Testing

```bash
pip install -r requirements.txt
python nasdaq_tracker.py
```

## Data Access for Machine Learning

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('nasdaq_data.db')

# Get all real-time price history (only actual price changes)
df = pd.read_sql_query('''
    SELECT symbol, price, previous_close, volume, market_state, fetch_timestamp
    FROM realtime_prices
    ORDER BY symbol, fetch_timestamp
''', conn)

# Get prices for a specific stock during regular market hours only
aapl = pd.read_sql_query('''
    SELECT price, volume, fetch_timestamp 
    FROM realtime_prices 
    WHERE symbol = 'AAPL' AND market_state = 'REGULAR'
    ORDER BY fetch_timestamp
''', conn)

# Calculate returns
aapl['return'] = aapl['price'].pct_change()

conn.close()
```

## Tracked Stocks

The tracker monitors all NASDAQ-100 components:

AAPL, MSFT, AMZN, NVDA, META, GOOGL, GOOG, TSLA, AVGO, COST, NFLX, AMD, PEP, ADBE, CSCO, TMUS, INTC, CMCSA, TXN, QCOM, INTU, AMGN, HON, AMAT, ISRG, BKNG, SBUX, VRTX, MDLZ, GILD, ADP, REGN, ADI, LRCX, PANW, KLAC, SNPS, MELI, CDNS, ASML, MAR, ABNB, PYPL, CRWD, ORLY, CTAS, MNST, NXPI, CSX, MRVL, PCAR, WDAY, CEG, ROP, ADSK, CPRT, DXCM, FTNT, CHTR, AEP, PAYX, ODFL, MCHP, KDP, KHC, FAST, ROST, AZN, EXC, EA, VRSK, CTSH, LULU, GEHC, IDXX, XEL, CCEP, DDOG, CSGP, BKR, TTWO, ANSS, ON, ZS, GFS, FANG, CDW, BIIB, ILMN, WBD, MDB, TEAM, MRNA, DLTR, SIRI, LCID, RIVN, ARM, SMCI, COIN

## Resource Usage

- GitHub Actions free tier: 2000 minutes per month
- Each run: approximately 1 minute
- Schedule: ~42 runs per day, only on trading days
- Monthly usage: approximately 900 minutes (well within free tier)

## Market Hours Reference

| Timezone | Market Open | Market Close |
|----------|-------------|--------------|
| EST | 09:30 | 16:00 |
| UTC | 14:30 | 21:00 |
| Turkey (TRT) | 17:30 | 00:00 |

## License

MIT
