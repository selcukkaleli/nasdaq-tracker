# NASDAQ-100 Real-Time Stock Tracker

An automated system that tracks NASDAQ-100 stocks using Yahoo Finance API, stores real-time price data in SQLite, and sends email alerts when abnormal price drops are detected.

## Features

- Real-time price tracking for NASDAQ-100 stocks (hourly)
- SQLite database storage with timestamps for each fetch
- Dual alert system: daily drops and hourly drops
- Email notifications for significant price movements
- Full automation via GitHub Actions
- Historical data accumulation for machine learning applications

## How It Works

The tracker fetches current market prices every hour and compares them against:

1. Previous close price (daily drop detection)
2. Price from the last hour (hourly drop detection)

When a stock drops below the configured threshold, an email alert is sent with details about the affected stocks.

## Database Schema

### realtime_prices

Stores current price snapshots taken every hour.

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
| fetch_timestamp | DATETIME | When the data was fetched |

### daily_prices

Stores historical daily OHLCV data.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| symbol | TEXT | Stock ticker symbol |
| date | DATE | Trading date |
| open | REAL | Opening price |
| high | REAL | Daily high |
| low | REAL | Daily low |
| close | REAL | Closing price |
| adj_close | REAL | Adjusted closing price |
| volume | INTEGER | Trading volume |
| fetch_timestamp | DATETIME | When the data was fetched |

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
| created_at | DATETIME | Alert timestamp |
| email_sent | BOOLEAN | Whether email was sent |

### fetch_logs

Tracks each fetch operation for monitoring.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| fetch_timestamp | DATETIME | Operation timestamp |
| fetch_type | TEXT | Type of fetch operation |
| symbols_fetched | INTEGER | Number of symbols processed |
| records_added | INTEGER | Records inserted |
| errors | TEXT | Any errors encountered |
| duration_seconds | REAL | Operation duration |

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
| HOURLY_DROP_THRESHOLD | 3.0 | Hourly drop threshold percentage |

## Usage

### Automatic Execution

GitHub Actions runs the tracker every hour automatically via cron schedule.

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

# Get all real-time price history
df = pd.read_sql_query('''
    SELECT symbol, price, previous_close, volume, fetch_timestamp
    FROM realtime_prices
    ORDER BY symbol, fetch_timestamp
''', conn)

# Get hourly prices for a specific stock
aapl = pd.read_sql_query('''
    SELECT price, fetch_timestamp 
    FROM realtime_prices 
    WHERE symbol = 'AAPL' 
    ORDER BY fetch_timestamp
''', conn)

# Calculate hourly returns
aapl['return'] = aapl['price'].pct_change()

conn.close()
```

## Tracked Stocks

The tracker monitors all NASDAQ-100 components including:

AAPL, MSFT, AMZN, NVDA, META, GOOGL, GOOG, TSLA, AVGO, COST, NFLX, AMD, PEP, ADBE, CSCO, TMUS, INTC, CMCSA, TXN, QCOM, INTU, AMGN, HON, AMAT, ISRG, BKNG, SBUX, VRTX, MDLZ, GILD, ADP, REGN, ADI, LRCX, PANW, KLAC, SNPS, MELI, CDNS, ASML, MAR, ABNB, PYPL, CRWD, ORLY, CTAS, MNST, NXPI, CSX, MRVL, PCAR, WDAY, CEG, ROP, ADSK, CPRT, DXCM, FTNT, CHTR, AEP, PAYX, ODFL, MCHP, KDP, KHC, FAST, ROST, AZN, EXC, EA, VRSK, CTSH, LULU, GEHC, IDXX, XEL, CCEP, DDOG, CSGP, BKR, TTWO, ANSS, ON, ZS, GFS, FANG, CDW, BIIB, ILMN, WBD, MDB, TEAM, MRNA, DLTR, SIRI, LCID, RIVN, ARM, SMCI, COIN

## Resource Usage

- GitHub Actions free tier: 2000 minutes per month
- Each run: approximately 1-2 minutes
- Hourly schedule: approximately 720 minutes per month

## Market Hours Reference

NYSE and NASDAQ trading hours:

| Timezone | Market Open | Market Close |
|----------|-------------|--------------|
| EST | 09:30 | 16:00 |
| UTC | 14:30 | 21:00 |
| Turkey (TRT) | 17:30 | 00:00 |

The tracker runs every hour regardless of market status. During off-hours, prices remain unchanged but the system continues to log data points.

## License

MIT
