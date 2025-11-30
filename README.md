NASDAQ-100 Stock Tracker 
Automated system that tracks NASDAQ-100 stocks using Yahoo Finance API and sends email notifications on abnormal price drops.
Features

- Hourly NASDAQ-100 stock tracking
- SQLite database storage
- Timestamp logging for each fetch operation
- Abnormal drop detection (default: 5%)
- Email notifications
- Full automation with GitHub Actions

Setup
1. Fork/Clone the Repository
bashgit clone https://github.com/YOUR_USERNAME/nasdaq-tracker.git
cd nasdaq-tracker
2. Configure GitHub Secrets
Go to Repository Settings > Secrets and variables > Actions > New repository secret:
Secret NameDescriptionEMAIL_SENDERSender email address (Gmail recommended)EMAIL_PASSWORDGmail App Password (not your regular password!)EMAIL_RECIPIENTEmail address to receive notifications
3. Create Gmail App Password

Go to Google Account > Security > Enable 2-Step Verification
Go to Google Account > Security > App passwords
Select "Mail" and "Other", then enter a name
Use the generated 16-character password as EMAIL_PASSWORD

4. (Optional) Configure Variables
Go to Repository Settings > Secrets and variables > Actions > Variables:
Variable NameDefaultDescriptionDROP_THRESHOLD5.0Abnormal drop threshold (%)
Usage
Automatic Execution
GitHub Actions runs automatically every hour.
Manual Execution

Go to the Actions tab
Select the "NASDAQ Tracker" workflow
Click "Run workflow"

Local Testing
bashpip install -r requirements.txt
python nasdaq_tracker.py
Database Schema
stock_prices
sql- id: INTEGER PRIMARY KEY
- symbol: TEXT (stock ticker)
- date: DATE
- open, high, low, close, adj_close: REAL (prices)
- volume: INTEGER (trading volume)
- fetch_timestamp: DATETIME (data retrieval time)
fetch_logs
sql- id: INTEGER PRIMARY KEY
- fetch_timestamp: DATETIME
- symbols_fetched: INTEGER
- records_added: INTEGER
- records_updated: INTEGER
- errors: TEXT
- duration_seconds: REAL
alerts
sql- id: INTEGER PRIMARY KEY
- symbol: TEXT
- alert_type: TEXT
- alert_message: TEXT
- price_change_percent: REAL
- created_at: DATETIME
- email_sent: BOOLEAN
Using Data for ML Models
pythonimport sqlite3
import pandas as pd

# Connect to database
conn = sqlite3.connect('nasdaq_data.db')

# Fetch all data
df = pd.read_sql_query('''
    SELECT symbol, date, open, high, low, close, volume, fetch_timestamp
    FROM stock_prices
    ORDER BY symbol, date
''', conn)

# Fetch data for a specific stock
aapl = pd.read_sql_query('''
    SELECT * FROM stock_prices 
    WHERE symbol = 'AAPL' 
    ORDER BY date
''', conn)

conn.close()
Tracked NASDAQ-100 Stocks
AAPL, MSFT, AMZN, NVDA, META, GOOGL, GOOG, TSLA, AVGO, COST, NFLX, AMD, PEP, ADBE, CSCO, TMUS, INTC, CMCSA, TXN, QCOM, INTU, AMGN, HON, AMAT, ISRG, BKNG, SBUX, VRTX, MDLZ, GILD, ADP, REGN, ADI, LRCX, PANW, KLAC, SNPS, MELI, CDNS, ASML, MAR, ABNB, PYPL, CRWD, ORLY, CTAS, MNST, NXPI, CSX, MRVL, PCAR, WDAY, CEG, ROP, ADSK, CPRT, DXCM, FTNT, CHTR, AEP, PAYX, ODFL, MCHP, KDP, KHC, FAST, ROST, AZN, EXC, EA, VRSK, CTSH, LULU, GEHC, IDXX, XEL, CCEP, DDOG, CSGP, BKR, TTWO, ANSS, ON, ZS, GFS, FANG, CDW, BIIB, ILMN, WBD, MDB, TEAM, MRNA, DLTR, SIRI, LCID, RIVN, ARM, SMCI, COIN
Notes

GitHub Actions free tier is limited to 2,000 minutes per month
Each run takes approximately 1-2 minutes
Hourly execution uses ~720 minutes per month
When NYSE is closed (weekends, holidays), data remains unchanged but the system still runs

License
MIT
