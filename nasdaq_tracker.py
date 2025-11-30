"""
NASDAQ-100 Stock Tracker
========================
Yahoo Finance API ile NASDAQ-100 hisselerini çekip SQLite'a kaydeder.
Anormal düşüşlerde email bildirimi gönderir.
"""

import yfinance as yf
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# NASDAQ-100 sembolleri (en büyük 100 şirket)
NASDAQ_100_SYMBOLS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "NFLX", "AMD", "PEP", "ADBE", "CSCO", "TMUS", "INTC", "CMCSA", "TXN", "QCOM",
    "INTU", "AMGN", "HON", "AMAT", "ISRG", "BKNG", "SBUX", "VRTX", "MDLZ", "GILD",
    "ADP", "REGN", "ADI", "LRCX", "PANW", "KLAC", "SNPS", "MELI", "CDNS", "ASML",
    "MAR", "ABNB", "PYPL", "CRWD", "ORLY", "CTAS", "MNST", "NXPI", "CSX", "MRVL",
    "PCAR", "WDAY", "CEG", "ROP", "ADSK", "CPRT", "DXCM", "FTNT", "CHTR", "AEP",
    "PAYX", "ODFL", "MCHP", "KDP", "KHC", "FAST", "ROST", "AZN", "EXC", "EA",
    "VRSK", "CTSH", "LULU", "GEHC", "IDXX", "XEL", "CCEP", "DDOG", "CSGP", "BKR",
    "TTWO", "ANSS", "ON", "ZS", "GFS", "FANG", "CDW", "BIIB", "ILMN", "WBD",
    "MDB", "TEAM", "MRNA", "DLTR", "SIRI", "LCID", "RIVN", "ARM", "SMCI", "COIN"
]

# Veritabanı yolu
DB_PATH = os.environ.get('DB_PATH', 'nasdaq_data.db')

# Email ayarları (GitHub Secrets'tan alınacak)
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_RECIPIENT = os.environ.get('EMAIL_RECIPIENT', '')
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))

# Anormal düşüş eşiği (yüzde olarak)
DROP_THRESHOLD = float(os.environ.get('DROP_THRESHOLD', '5.0'))


def init_database():
    """Veritabanı tablolarını oluşturur."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ana hisse verileri tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date DATE NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adj_close REAL,
            volume INTEGER,
            fetch_timestamp DATETIME NOT NULL,
            UNIQUE(symbol, date)
        )
    ''')
    
    # Fetch log tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_timestamp DATETIME NOT NULL,
            symbols_fetched INTEGER,
            records_added INTEGER,
            records_updated INTEGER,
            errors TEXT,
            duration_seconds REAL
        )
    ''')
    
    # Alertler tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            alert_message TEXT,
            price_change_percent REAL,
            created_at DATETIME NOT NULL,
            email_sent BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # İndeksler
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON stock_prices(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON stock_prices(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_prices(symbol, date)')
    
    conn.commit()
    conn.close()
    logger.info("Veritabanı başarıyla hazırlandı.")


def fetch_stock_data(symbols: list, period: str = "5d") -> pd.DataFrame:
    """
    Yahoo Finance'den hisse verilerini çeker.
    
    Args:
        symbols: Hisse sembolleri listesi
        period: Veri periyodu (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    
    Returns:
        DataFrame with stock data
    """
    logger.info(f"{len(symbols)} hisse için veri çekiliyor...")
    
    try:
        # Tüm sembolleri tek seferde çek (daha verimli)
        data = yf.download(
            tickers=symbols,
            period=period,
            group_by='ticker',
            auto_adjust=False,
            threads=True,
            progress=False
        )
        
        return data
    except Exception as e:
        logger.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()


def save_to_database(data: pd.DataFrame, symbols: list) -> tuple:
    """
    Çekilen verileri SQLite veritabanına kaydeder.
    
    Returns:
        (records_added, records_updated)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    fetch_timestamp = datetime.now().isoformat()
    records_added = 0
    records_updated = 0
    
    for symbol in symbols:
        try:
            # Tek hisse için veri al
            if len(symbols) == 1:
                symbol_data = data
            else:
                if symbol not in data.columns.get_level_values(0):
                    continue
                symbol_data = data[symbol]
            
            if symbol_data.empty:
                continue
            
            for date, row in symbol_data.iterrows():
                # NaN kontrolü
                if pd.isna(row.get('Close')):
                    continue
                
                date_str = date.strftime('%Y-%m-%d')
                
                # Upsert işlemi
                cursor.execute('''
                    INSERT INTO stock_prices 
                    (symbol, date, open, high, low, close, adj_close, volume, fetch_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adj_close = excluded.adj_close,
                    volume = excluded.volume,
                    fetch_timestamp = excluded.fetch_timestamp
                ''', (
                    symbol,
                    date_str,
                    float(row.get('Open', 0)) if not pd.isna(row.get('Open')) else None,
                    float(row.get('High', 0)) if not pd.isna(row.get('High')) else None,
                    float(row.get('Low', 0)) if not pd.isna(row.get('Low')) else None,
                    float(row.get('Close', 0)) if not pd.isna(row.get('Close')) else None,
                    float(row.get('Adj Close', 0)) if not pd.isna(row.get('Adj Close')) else None,
                    int(row.get('Volume', 0)) if not pd.isna(row.get('Volume')) else None,
                    fetch_timestamp
                ))
                
                if cursor.rowcount > 0:
                    records_added += 1
                    
        except Exception as e:
            logger.error(f"{symbol} için kayıt hatası: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    logger.info(f"Kaydedilen: {records_added} kayıt")
    return records_added, records_updated


def check_for_anomalies() -> list:
    """
    Son verilerde anormal düşüş olup olmadığını kontrol eder.
    
    Returns:
        List of (symbol, change_percent, current_price, previous_price)
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Her hisse için son iki günün kapanış fiyatını al
    query = '''
        WITH RankedPrices AS (
            SELECT 
                symbol,
                date,
                close,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
            FROM stock_prices
            WHERE close IS NOT NULL
        )
        SELECT 
            t1.symbol,
            t1.close as latest_close,
            t2.close as previous_close,
            t1.date as latest_date,
            t2.date as previous_date
        FROM RankedPrices t1
        JOIN RankedPrices t2 ON t1.symbol = t2.symbol
        WHERE t1.rn = 1 AND t2.rn = 2
    '''
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    anomalies = []
    
    for _, row in df.iterrows():
        if row['previous_close'] > 0:
            change_percent = ((row['latest_close'] - row['previous_close']) / row['previous_close']) * 100
            
            # Eşik değerini aşan düşüşleri tespit et
            if change_percent <= -DROP_THRESHOLD:
                anomalies.append({
                    'symbol': row['symbol'],
                    'change_percent': round(change_percent, 2),
                    'current_price': round(row['latest_close'], 2),
                    'previous_price': round(row['previous_close'], 2),
                    'latest_date': row['latest_date'],
                    'previous_date': row['previous_date']
                })
    
    return anomalies


def save_alert(symbol: str, alert_type: str, message: str, change_percent: float):
    """Alerti veritabanına kaydeder."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO alerts (symbol, alert_type, alert_message, price_change_percent, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (symbol, alert_type, message, change_percent, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()


def send_alert_email(anomalies: list) -> bool:
    """
    Anormal düşüşler için email gönderir.
    
    Args:
        anomalies: List of anomaly dictionaries
    
    Returns:
        True if email sent successfully
    """
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT]):
        logger.warning("Email ayarları eksik, email gönderilmeyecek.")
        return False
    
    if not anomalies:
        return False
    
    # Email içeriği oluştur
    subject = f"🚨 NASDAQ Alert: {len(anomalies)} hissede anormal düşüş!"
    
    html_content = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #4CAF50; color: white; }
            .negative { color: red; font-weight: bold; }
            h2 { color: #333; }
        </style>
    </head>
    <body>
        <h2>🚨 NASDAQ Anormal Düşüş Uyarısı</h2>
        <p>Aşağıdaki hisselerde %{threshold} veya daha fazla düşüş tespit edildi:</p>
        <table>
            <tr>
                <th>Sembol</th>
                <th>Değişim (%)</th>
                <th>Güncel Fiyat</th>
                <th>Önceki Fiyat</th>
                <th>Tarih</th>
            </tr>
    """.format(threshold=DROP_THRESHOLD)
    
    for anomaly in anomalies:
        html_content += f"""
            <tr>
                <td><strong>{anomaly['symbol']}</strong></td>
                <td class="negative">{anomaly['change_percent']}%</td>
                <td>${anomaly['current_price']}</td>
                <td>${anomaly['previous_price']}</td>
                <td>{anomaly['latest_date']}</td>
            </tr>
        """
        
        # Alert'i veritabanına kaydet
        save_alert(
            anomaly['symbol'],
            'SIGNIFICANT_DROP',
            f"{anomaly['change_percent']}% düşüş",
            anomaly['change_percent']
        )
    
    html_content += """
        </table>
        <p style="margin-top: 20px; color: #666;">
            Bu otomatik bir bildirimdir. NASDAQ Tracker tarafından gönderilmiştir.
        </p>
    </body>
    </html>
    """
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECIPIENT
        
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        
        logger.info(f"Alert emaili başarıyla gönderildi: {len(anomalies)} anomali")
        return True
        
    except Exception as e:
        logger.error(f"Email gönderme hatası: {e}")
        return False


def log_fetch_operation(symbols_count: int, records_added: int, records_updated: int, 
                        errors: str, duration: float):
    """Fetch işlemini logla."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO fetch_logs 
        (fetch_timestamp, symbols_fetched, records_added, records_updated, errors, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), symbols_count, records_added, records_updated, errors, duration))
    
    conn.commit()
    conn.close()


def main():
    """Ana fonksiyon."""
    start_time = datetime.now()
    logger.info("=" * 50)
    logger.info(f"NASDAQ Tracker başlatılıyor - {start_time.isoformat()}")
    logger.info("=" * 50)
    
    errors = []
    
    try:
        # 1. Veritabanını hazırla
        init_database()
        
        # 2. Verileri çek
        data = fetch_stock_data(NASDAQ_100_SYMBOLS, period="5d")
        
        if data.empty:
            errors.append("Veri çekilemedi")
            logger.error("Veri çekilemedi!")
            return
        
        # 3. Veritabanına kaydet
        records_added, records_updated = save_to_database(data, NASDAQ_100_SYMBOLS)
        
        # 4. Anormal düşüşleri kontrol et
        anomalies = check_for_anomalies()
        
        if anomalies:
            logger.warning(f"{len(anomalies)} hissede anormal düşüş tespit edildi!")
            for a in anomalies:
                logger.warning(f"  {a['symbol']}: {a['change_percent']}% düşüş")
            
            # Email gönder
            send_alert_email(anomalies)
        else:
            logger.info("Anormal düşüş tespit edilmedi.")
        
        # 5. İşlemi logla
        duration = (datetime.now() - start_time).total_seconds()
        log_fetch_operation(
            len(NASDAQ_100_SYMBOLS),
            records_added,
            records_updated,
            "; ".join(errors) if errors else None,
            duration
        )
        
        logger.info(f"İşlem tamamlandı. Süre: {duration:.2f} saniye")
        
    except Exception as e:
        logger.error(f"Kritik hata: {e}")
        errors.append(str(e))
        raise


if __name__ == "__main__":
    main()
