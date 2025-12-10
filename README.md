# NASDAQ-100 Real-Time Stock Tracker

An automated system that tracks NASDAQ-100 stocks using Yahoo Finance API, stores real-time price data in SQLite, and sends email alerts when abnormal price drops are detected relative to the market benchmark (QQQ).

## Features

- Real-time price tracking for NASDAQ-100 stocks (every 10 minutes during market hours)
- Smart benchmark comparison using QQQ (NASDAQ-100 ETF)
- Filters out market-wide movements to detect true anomalies
- Smart data storage: only saves when prices actually change
- All timestamps in EST (America/New_York) for consistency with NASDAQ trading hours
- Multiple alert types: relative drops, absolute drops, and hourly drops
- Spam prevention: same alert type suppressed for configurable duration
- Email notifications for significant price movements
- Full automation via GitHub Actions

## How It Works

The tracker runs every 10 minutes during NYSE/NASDAQ market hours (Mon-Fri, 09:30-16:00 EST) and:

1. Fetches current market prices from Yahoo Finance (including QQQ benchmark)
2. Calculates benchmark (QQQ) daily change
3. Compares each stock's movement relative to the benchmark
4. Alerts only when a stock drops significantly more than the market
5. Saves price data only if changed (avoids duplicate data)

### Alert Logic

| Scenario | QQQ | Stock | Relative | Alert? |
|----------|-----|-------|----------|--------|
| Market down, stock follows | -3% | -4% | -1% | No |
| Market down, stock crashes | -2% | -7% | -5% | Yes (RELATIVE_DROP) |
| Market flat, stock drops | +0.5% | -6% | -6.5% | Yes (ABSOLUTE_DROP) |
| Sudden intraday drop | N/A | -4% in 10min | N/A | Yes (HOURLY_DROP) |

## Alert Types

| Type | Description | Default Threshold |
|------|-------------|-------------------|
| RELATIVE_DROP | Stock dropped more than QQQ by threshold | 3% |
| ABSOLUTE_DROP | Stock dropped significantly while market is flat | 5% (when QQQ > -2%) |
| HOURLY_DROP | Sudden drop since last recorded price | 3% |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DROP_THRESHOLD | 5.0 | Absolute daily drop threshold (%) |
| HOURLY_DROP_THRESHOLD | 3.0 | Intraday drop threshold (%) |
| RELATIVE_DROP_THRESHOLD | 3.0 | Drop vs benchmark threshold (%) |
| MIN_PRICE_FOR_ALERT | 5.0 | Ignore stocks below this price ($) |
| MIN_ABS_MOVE_DOLLAR | 0.50 | Ignore moves smaller than this ($) |
| MIN_MINUTES_BETWEEN_SAME_ALERT | 60 | Spam prevention window (minutes) |

### GitHub Secrets

| Secret Name | Description |
|-------------|-------------|
| EMAIL_SENDER | Sender email address (Gmail recommended) |
| EMAIL_PASSWORD | Gmail App Password |
| EMAIL_RECIPIENT | Email address to receive alerts |

## Database Schema

### realtime_prices

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

### alerts

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| symbol | TEXT | Stock ticker symbol |
| alert_type | TEXT | RELATIVE_DROP, ABSOLUTE_DROP, or HOURLY_DROP |
| alert_message | TEXT | Description of the alert |
| price_change_percent | REAL | Stock's percentage change |
| benchmark_change_percent | REAL | QQQ's percentage change |
| relative_change_percent | REAL | Difference (stock - benchmark) |
| current_price | REAL | Price at alert time |
| previous_price | REAL | Reference price |
| created_at | DATETIME | Alert timestamp (EST) |
| email_sent | BOOLEAN | Whether email was sent |

### fetch_logs

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| fetch_timestamp | DATETIME | Operation timestamp (EST) |
| fetch_type | TEXT | REALTIME or SKIPPED |
| market_state | TEXT | Market state at fetch time |
| symbols_fetched | INTEGER | Number of symbols processed |
| records_added | INTEGER | Records inserted |
| records_skipped | INTEGER | Records skipped (unchanged) |
| benchmark_change | REAL | QQQ daily change (%) |
| errors | TEXT | Any errors encountered |
| duration_seconds | REAL | Operation duration |

## Installation

### 1. Fork or Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/nasdaq-tracker.git
cd nasdaq-tracker
```

### 2. Configure GitHub Secrets

Navigate to Settings > Secrets and variables > Actions and add:

- EMAIL_SENDER
- EMAIL_PASSWORD
- EMAIL_RECIPIENT

### 3. Create Gmail App Password

1. Enable 2-Step Verification in Google Account
2. Go to Security > App passwords
3. Generate password for "Mail"
4. Use the 16-character password as EMAIL_PASSWORD

### 4. Configure Variables (Optional)

In Settings > Secrets and variables > Actions > Variables, you can customize thresholds.

## Usage

### Automatic Execution

GitHub Actions runs every 10 minutes during market hours:
- Monday-Friday
- 09:30-16:00 EST (14:30-21:00 UTC)

### Manual Execution

1. Go to Actions tab
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

# Get price history with benchmark comparison
df = pd.read_sql_query('''
    SELECT 
        r1.symbol,
        r1.price,
        r1.previous_close,
        r1.fetch_timestamp,
        r2.price as qqq_price,
        r2.previous_close as qqq_prev_close
    FROM realtime_prices r1
    LEFT JOIN realtime_prices r2 
        ON r2.symbol = 'QQQ' 
        AND r2.fetch_timestamp = r1.fetch_timestamp
    WHERE r1.symbol != 'QQQ'
    ORDER BY r1.symbol, r1.fetch_timestamp
''', conn)

# Calculate relative performance
df['stock_change'] = (df['price'] - df['previous_close']) / df['previous_close'] * 100
df['qqq_change'] = (df['qqq_price'] - df['qqq_prev_close']) / df['qqq_prev_close'] * 100
df['relative_change'] = df['stock_change'] - df['qqq_change']

conn.close()
```

## Tracked Stocks

QQQ (benchmark) plus all NASDAQ-100 components:

AAPL, MSFT, AMZN, NVDA, META, GOOGL, GOOG, TSLA, AVGO, COST, NFLX, AMD, PEP, ADBE, CSCO, TMUS, INTC, CMCSA, TXN, QCOM, INTU, AMGN, HON, AMAT, ISRG, BKNG, SBUX, VRTX, MDLZ, GILD, ADP, REGN, ADI, LRCX, PANW, KLAC, SNPS, MELI, CDNS, ASML, MAR, ABNB, PYPL, CRWD, ORLY, CTAS, MNST, NXPI, CSX, MRVL, PCAR, WDAY, CEG, ROP, ADSK, CPRT, DXCM, FTNT, CHTR, AEP, PAYX, ODFL, MCHP, KDP, KHC, FAST, ROST, AZN, EXC, EA, VRSK, CTSH, LULU, GEHC, IDXX, XEL, CCEP, DDOG, CSGP, BKR, TTWO, ANSS, ON, ZS, GFS, FANG, CDW, BIIB, ILMN, WBD, MDB, TEAM, MRNA, DLTR, SIRI, LCID, RIVN, ARM, SMCI, COIN

## Resource Usage

- GitHub Actions free tier: 2000 minutes/month
- Each run: ~1 minute
- Schedule: ~42 runs/day on trading days
- Monthly usage: ~900 minutes

## Market Hours Reference

| Timezone | Market Open | Market Close |
|----------|-------------|--------------|
| EST | 09:30 | 16:00 |
| UTC | 14:30 | 21:00 |
| Turkey (TRT) | 17:30 | 00:00 |

## License

MIT
