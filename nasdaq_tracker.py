"""
NASDAQ-100 Stock Tracker v2 - Real-time Price Tracking
=======================================================
Yahoo Finance API ile NASDAQ-100 hisselerinin ANLIK fiyatlarını çekip SQLite'a kaydeder.
Saatlik bazda anormal düşüşlerde email bildirimi gönderir.
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

# Saatlik düşüş eşiği (daha hassas)
HOURLY_DROP_THRESHOLD = float(os.environ.get('HOURLY_DROP_THRESHOLD', '3.0'))


def init_database():
    """Veritabanı tablolarını oluşturur."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Anlık fiyat tablosu (her saat kaydedilecek)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS realtime_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            previous_close REAL,
            day_high REAL,
            day_low REAL,
            volume INTEGER,
            market_cap REAL,
            fetch_timestamp DATETIME NOT NULL
        )
    ''')
    
    # Günlük kapanış verileri (historical data için)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_prices (
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
            fetch_type TEXT NOT NULL,
            symbols_fetched INTEGER,
            records_added INTEGER,
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
            current_price REAL,
            previous_price REAL,
            created_at DATETIME NOT NULL,
            email_sent BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # İndeksler
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_symbol ON realtime_prices(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_timestamp ON realtime_prices(fetch_timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_symbol ON daily_prices(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_prices(date)')
    
    conn.commit()
    conn.close()
    logger.info("Veritabanı başarıyla hazırlandı.")


def fetch_realtime_prices(symbols: list) -> list:
    """
    Yahoo Finance'den ANLIK fiyatları çeker.
    
    Args:
        symbols: Hisse sembolleri listesi
    
    Returns:
        List of dictionaries with realtime data
    """
    logger.info(f"{len(symbols)} hisse için anlık fiyatlar çekiliyor...")
    
    results = []
    fetch_timestamp = datetime.now().isoformat()
    
    # Batch halinde çek (daha verimli)
    tickers = yf.Tickers(' '.join(symbols))
    
    for symbol in symbols:
        try:
            ticker = tickers.tickers.get(symbol)
            if ticker is None:
                continue
                
            info = ticker.info
            
            # Anlık fiyat bilgilerini al
            current_price = info.get('regularMarketPrice') or info.get('currentPrice')
            
            if current_price is None:
                # Fast info dene
                fast_info = ticker.fast_info
                current_price = getattr(fast_info, 'last_price', None)
            
            if current_price is None:
                logger.warning(f"{symbol}: Fiyat bilgisi alınamadı")
                continue
            
            results.append({
                'symbol': symbol,
                'price': current_price,
                'previous_close': info.get('previousClose') or info.get('regularMarketPreviousClose'),
                'day_high': info.get('dayHigh') or info.get('regularMarketDayHigh'),
                'day_low': info.get('dayLow') or info.get('regularMarketDayLow'),
                'volume': info.get('volume') or info.get('regularMarketVolume'),
                'market_cap': info.get('marketCap'),
                'fetch_timestamp': fetch_timestamp
            })
            
        except Exception as e:
            logger.error(f"{symbol} için hata: {e}")
            continue
    
    logger.info(f"{len(results)} hisse için anlık fiyat alındı.")
    return results


def save_realtime_prices(prices: list) -> int:
    """
    Anlık fiyatları veritabanına kaydeder.
    
    Returns:
        Number of records added
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    records_added = 0
    
    for price_data in prices:
        try:
            cursor.execute('''
                INSERT INTO realtime_prices 
                (symbol, price, previous_close, day_high, day_low, volume, market_cap, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                price_data['symbol'],
                price_data['price'],
                price_data['previous_close'],
                price_data['day_high'],
                price_data['day_low'],
                price_data['volume'],
                price_data['market_cap'],
                price_data['fetch_timestamp']
            ))
            records_added += 1
        except Exception as e:
            logger.error(f"Kayıt hatası {price_data['symbol']}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"{records_added} anlık fiyat kaydedildi.")
    return records_added


def check_for_anomalies(current_prices: list) -> list:
    """
    Anlık fiyatlarda anormal düşüş olup olmadığını kontrol eder.
    
    1. Günlük düşüş: previous_close'a göre
    2. Saatlik düşüş: Son 1 saatteki kayda göre
    
    Returns:
        List of anomaly dictionaries
    """
    conn = sqlite3.connect(DB_PATH)
    anomalies = []
    
    for price_data in current_prices:
        symbol = price_data['symbol']
        current_price = price_data['price']
        previous_close = price_data['previous_close']
        
        # 1. Günlük düşüş kontrolü (previous close'a göre)
        if previous_close and previous_close > 0:
            daily_change = ((current_price - previous_close) / previous_close) * 100
            
            if daily_change <= -DROP_THRESHOLD:
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'DAILY_DROP',
                    'change_percent': round(daily_change, 2),
                    'current_price': round(current_price, 2),
                    'previous_price': round(previous_close, 2),
                    'timeframe': 'Günlük (önceki kapanışa göre)'
                })
        
        # 2. Saatlik düşüş kontrolü (son 1 saatteki kayda göre)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT price, fetch_timestamp 
            FROM realtime_prices 
            WHERE symbol = ? 
              AND fetch_timestamp < ?
              AND fetch_timestamp > datetime(?, '-2 hours')
            ORDER BY fetch_timestamp DESC 
            LIMIT 1
        ''', (symbol, price_data['fetch_timestamp'], price_data['fetch_timestamp']))
        
        row = cursor.fetchone()
        if row:
            last_hour_price = row[0]
            last_timestamp = row[1]
            
            if last_hour_price and last_hour_price > 0:
                hourly_change = ((current_price - last_hour_price) / last_hour_price) * 100
                
                if hourly_change <= -HOURLY_DROP_THRESHOLD:
                    anomalies.append({
                        'symbol': symbol,
                        'alert_type': 'HOURLY_DROP',
                        'change_percent': round(hourly_change, 2),
                        'current_price': round(current_price, 2),
                        'previous_price': round(last_hour_price, 2),
                        'timeframe': f'Saatlik ({last_timestamp} den beri)'
                    })
    
    conn.close()
    return anomalies


def save_alert(anomaly: dict):
    """Alerti veritabanına kaydeder."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO alerts (symbol, alert_type, alert_message, price_change_percent, 
                           current_price, previous_price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        anomaly['symbol'],
        anomaly['alert_type'],
        f"{anomaly['timeframe']}: {anomaly['change_percent']}% düşüş",
        anomaly['change_percent'],
        anomaly['current_price'],
        anomaly['previous_price'],
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()


def send_alert_email(anomalies: list) -> bool:
    """
    Anormal düşüşler için email gönderir.
    """
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT]):
        logger.warning("Email ayarları eksik, email gönderilmeyecek.")
        return False
    
    if not anomalies:
        return False
    
    # Duplicate alert kontrolü - aynı hisse için son 1 saat içinde alert gönderilmiş mi?
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    new_anomalies = []
    for anomaly in anomalies:
        cursor.execute('''
            SELECT COUNT(*) FROM alerts 
            WHERE symbol = ? 
              AND alert_type = ?
              AND created_at > datetime('now', '-1 hour')
              AND email_sent = TRUE
        ''', (anomaly['symbol'], anomaly['alert_type']))
        
        if cursor.fetchone()[0] == 0:
            new_anomalies.append(anomaly)
    
    conn.close()
    
    if not new_anomalies:
        logger.info("Tüm alertler zaten gönderilmiş, yeni email gönderilmeyecek.")
        return False
    
    # Email içeriği oluştur
    subject = f"🚨 NASDAQ Alert: {len(new_anomalies)} hissede anormal düşüş!"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #d32f2f; color: white; }}
            .negative {{ color: red; font-weight: bold; }}
            .daily {{ background-color: #ffebee; }}
            .hourly {{ background-color: #fff3e0; }}
            h2 {{ color: #333; }}
        </style>
    </head>
    <body>
        <h2>🚨 NASDAQ Anormal Düşüş Uyarısı</h2>
        <p><strong>Zaman:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        <p>Aşağıdaki hisselerde önemli düşüş tespit edildi:</p>
        <table>
            <tr>
                <th>Sembol</th>
                <th>Alert Tipi</th>
                <th>Değişim (%)</th>
                <th>Güncel Fiyat</th>
                <th>Önceki Fiyat</th>
                <th>Zaman Dilimi</th>
            </tr>
    """
    
    for anomaly in new_anomalies:
        row_class = 'daily' if anomaly['alert_type'] == 'DAILY_DROP' else 'hourly'
        alert_type_text = 'Günlük Düşüş' if anomaly['alert_type'] == 'DAILY_DROP' else 'Saatlik Düşüş'
        
        html_content += f"""
            <tr class="{row_class}">
                <td><strong>{anomaly['symbol']}</strong></td>
                <td>{alert_type_text}</td>
                <td class="negative">{anomaly['change_percent']}%</td>
                <td>${anomaly['current_price']}</td>
                <td>${anomaly['previous_price']}</td>
                <td>{anomaly['timeframe']}</td>
            </tr>
        """
        
        # Alert'i veritabanına kaydet
        save_alert(anomaly)
    
    html_content += """
        </table>
        <p style="margin-top: 20px; color: #666;">
            <strong>Eşik Değerleri:</strong><br>
            - Günlük düşüş eşiği: %{daily_threshold}<br>
            - Saatlik düşüş eşiği: %{hourly_threshold}
        </p>
        <p style="color: #999;">
            Bu otomatik bir bildirimdir. NASDAQ Tracker tarafından gönderilmiştir.
        </p>
    </body>
    </html>
    """.format(daily_threshold=DROP_THRESHOLD, hourly_threshold=HOURLY_DROP_THRESHOLD)
    
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
        
        # Email gönderildi olarak işaretle
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE alerts SET email_sent = TRUE 
            WHERE created_at > datetime('now', '-1 minute')
        ''')
        conn.commit()
        conn.close()
        
        logger.info(f"Alert emaili başarıyla gönderildi: {len(new_anomalies)} anomali")
        return True
        
    except Exception as e:
        logger.error(f"Email gönderme hatası: {e}")
        return False


def log_fetch_operation(fetch_type: str, symbols_count: int, records_added: int, 
                        errors: str, duration: float):
    """Fetch işlemini logla."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO fetch_logs 
        (fetch_timestamp, fetch_type, symbols_fetched, records_added, errors, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), fetch_type, symbols_count, records_added, errors, duration))
    
    conn.commit()
    conn.close()


def get_market_status() -> dict:
    """
    Piyasa durumunu kontrol eder.
    NYSE/NASDAQ: Pazartesi-Cuma, 09:30-16:00 EST
    """
    from datetime import timezone
    import pytz
    
    try:
        est = pytz.timezone('US/Eastern')
        now_est = datetime.now(est)
        
        # Hafta sonu kontrolü (0=Pazartesi, 6=Pazar)
        is_weekday = now_est.weekday() < 5
        
        # Saat kontrolü
        market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
        is_market_hours = market_open <= now_est <= market_close
        
        return {
            'is_open': is_weekday and is_market_hours,
            'is_weekday': is_weekday,
            'is_market_hours': is_market_hours,
            'current_time_est': now_est.strftime('%Y-%m-%d %H:%M:%S EST')
        }
    except:
        # pytz yoksa basit kontrol
        return {'is_open': True, 'note': 'Could not determine market status'}


def main():
    """Ana fonksiyon."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"NASDAQ Tracker v2 başlatılıyor - {start_time.isoformat()}")
    logger.info("=" * 60)
    
    errors = []
    
    try:
        # Piyasa durumunu kontrol et
        market_status = get_market_status()
        logger.info(f"Piyasa durumu: {market_status}")
        
        # 1. Veritabanını hazırla
        init_database()
        
        # 2. Anlık fiyatları çek
        realtime_prices = fetch_realtime_prices(NASDAQ_100_SYMBOLS)
        
        if not realtime_prices:
            errors.append("Anlık fiyat çekilemedi")
            logger.error("Anlık fiyat çekilemedi!")
            return
        
        # 3. Veritabanına kaydet
        records_added = save_realtime_prices(realtime_prices)
        
        # 4. Anormal düşüşleri kontrol et
        anomalies = check_for_anomalies(realtime_prices)
        
        if anomalies:
            logger.warning(f"{len(anomalies)} anormal düşüş tespit edildi!")
            for a in anomalies:
                logger.warning(f"  {a['symbol']}: {a['change_percent']}% ({a['alert_type']})")
            
            # Email gönder
            send_alert_email(anomalies)
        else:
            logger.info("Anormal düşüş tespit edilmedi.")
        
        # 5. İşlemi logla
        duration = (datetime.now() - start_time).total_seconds()
        log_fetch_operation(
            'REALTIME',
            len(NASDAQ_100_SYMBOLS),
            records_added,
            "; ".join(errors) if errors else None,
            duration
        )
        
        # 6. Özet bilgi
        logger.info("=" * 60)
        logger.info(f"ÖZET:")
        logger.info(f"  - Çekilen hisse: {len(realtime_prices)}")
        logger.info(f"  - Kaydedilen: {records_added}")
        logger.info(f"  - Tespit edilen anomali: {len(anomalies)}")
        logger.info(f"  - Süre: {duration:.2f} saniye")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Kritik hata: {e}")
        errors.append(str(e))
        raise


if __name__ == "__main__":
    main()
