"""
NASDAQ-100 Stock Tracker v3 - Smart Real-time Price Tracking
=============================================================
Yahoo Finance API ile NASDAQ-100 hisselerinin ANLIK fiyatlarini cekip SQLite'a kaydeder.
Sadece piyasa acikken ve fiyat degistiginde kayit yapar.
Anormal dususlerde email bildirimi gonderir.
"""

import yfinance as yf
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone, time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Logging ayarlari
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# NASDAQ-100 sembolleri
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

# Veritabani yolu
DB_PATH = os.environ.get('DB_PATH', 'nasdaq_data.db')

# Email ayarlari
EMAIL_SENDER = os.environ.get('EMAIL_SENDER', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_RECIPIENT = os.environ.get('EMAIL_RECIPIENT', '')
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))

# Dusus esikleri
DROP_THRESHOLD = float(os.environ.get('DROP_THRESHOLD', '5.0'))
HOURLY_DROP_THRESHOLD = float(os.environ.get('HOURLY_DROP_THRESHOLD', '3.0'))


def get_market_status() -> dict:
    """
    NYSE/NASDAQ piyasa durumunu kontrol eder.
    Piyasa saatleri: Pazartesi-Cuma, 09:30-16:00 EST
    Pre-market: 04:00-09:30 EST
    After-hours: 16:00-20:00 EST
    """
    try:
        est = ZoneInfo('America/New_York')
        now_est = datetime.now(est)
        
        # Hafta sonu kontrolu (0=Pazartesi, 6=Pazar)
        weekday = now_est.weekday()
        is_weekday = weekday < 5
        
        # Saat kontrolu
        current_time = now_est.time()
        
        market_open = time(9, 30)
        market_close = time(16, 0)
        pre_market_open = time(4, 0)
        after_hours_close = time(20, 0)
        
        is_regular_hours = market_open <= current_time <= market_close
        is_extended_hours = (pre_market_open <= current_time < market_open) or \
                           (market_close < current_time <= after_hours_close)
        
        # Piyasa acik mi?
        is_open = is_weekday and (is_regular_hours or is_extended_hours)
        
        return {
            'is_open': is_open,
            'is_regular_hours': is_weekday and is_regular_hours,
            'is_extended_hours': is_weekday and is_extended_hours,
            'is_weekday': is_weekday,
            'current_time_est': now_est.strftime('%Y-%m-%d %H:%M:%S EST'),
            'weekday': weekday
        }
    except Exception as e:
        logger.warning(f"Piyasa durumu kontrol edilemedi: {e}")
        return {
            'is_open': True,
            'is_regular_hours': True,
            'is_extended_hours': False,
            'is_weekday': True,
            'current_time_est': 'Unknown',
            'error': str(e)
        }


def init_database():
    """Veritabani tablolarini olusturur."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Anlik fiyat tablosu
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
            market_state TEXT,
            fetch_timestamp DATETIME NOT NULL
        )
    ''')
    
    # Fetch log tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_timestamp DATETIME NOT NULL,
            fetch_type TEXT,
            market_state TEXT,
            symbols_fetched INTEGER,
            records_added INTEGER,
            records_skipped INTEGER,
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
    
    # Indeksler
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_symbol ON realtime_prices(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_timestamp ON realtime_prices(fetch_timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_symbol_timestamp ON realtime_prices(symbol, fetch_timestamp)')
    
    conn.commit()
    conn.close()
    logger.info("Veritabani hazir.")


def get_last_prices() -> dict:
    """Her sembol icin son kaydedilen fiyati getirir."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT symbol, price, fetch_timestamp
        FROM realtime_prices
        WHERE id IN (
            SELECT MAX(id) FROM realtime_prices GROUP BY symbol
        )
    ''')
    
    last_prices = {}
    for row in cursor.fetchall():
        last_prices[row[0]] = {'price': row[1], 'timestamp': row[2]}
    
    conn.close()
    return last_prices


def fetch_realtime_prices(symbols: list) -> list:
    """
    Yahoo Finance'den ANLIK fiyatlari ceker.
    All timestamps are in EST (America/New_York) for consistency with NASDAQ trading hours.
    """
    logger.info(f"{len(symbols)} hisse icin anlik fiyatlar cekiliyor...")
    
    results = []
    # Use EST timezone for all timestamps (NASDAQ timezone)
    est = ZoneInfo('America/New_York')
    fetch_timestamp = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    # Batch halinde cek
    tickers = yf.Tickers(' '.join(symbols))
    
    for symbol in symbols:
        try:
            ticker = tickers.tickers.get(symbol)
            if ticker is None:
                continue
            
            info = ticker.info
            
            # Piyasa durumu
            market_state = info.get('marketState', 'UNKNOWN')
            
            # Anlik fiyat - piyasa durumuna gore
            if market_state == 'REGULAR':
                current_price = info.get('regularMarketPrice')
            elif market_state in ['PRE', 'PREPRE']:
                current_price = info.get('preMarketPrice') or info.get('regularMarketPrice')
            elif market_state in ['POST', 'POSTPOST']:
                current_price = info.get('postMarketPrice') or info.get('regularMarketPrice')
            else:
                current_price = info.get('regularMarketPrice') or info.get('currentPrice')
            
            if current_price is None:
                try:
                    fast_info = ticker.fast_info
                    current_price = getattr(fast_info, 'last_price', None)
                except:
                    pass
            
            if current_price is None:
                logger.warning(f"{symbol}: Fiyat bilgisi alinamadi")
                continue
            
            results.append({
                'symbol': symbol,
                'price': float(current_price),
                'previous_close': info.get('previousClose') or info.get('regularMarketPreviousClose'),
                'day_high': info.get('dayHigh') or info.get('regularMarketDayHigh'),
                'day_low': info.get('dayLow') or info.get('regularMarketDayLow'),
                'volume': info.get('volume') or info.get('regularMarketVolume'),
                'market_cap': info.get('marketCap'),
                'market_state': market_state,
                'fetch_timestamp': fetch_timestamp
            })
            
        except Exception as e:
            logger.error(f"{symbol} icin hata: {e}")
            continue
    
    logger.info(f"{len(results)} hisse icin fiyat alindi.")
    return results


def save_realtime_prices(prices: list, last_prices: dict) -> tuple:
    """
    Anlik fiyatlari veritabanina kaydeder.
    Sadece fiyat degismisse kayit yapar.
    
    Returns:
        (records_added, records_skipped)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    records_added = 0
    records_skipped = 0
    
    for price_data in prices:
        symbol = price_data['symbol']
        current_price = price_data['price']
        
        # Son fiyatla karsilastir
        last = last_prices.get(symbol)
        
        if last:
            last_price = last['price']
            # Fiyat degismemisse kaydetme (kucuk tolerans ile)
            if abs(current_price - last_price) < 0.001:
                records_skipped += 1
                continue
        
        try:
            cursor.execute('''
                INSERT INTO realtime_prices 
                (symbol, price, previous_close, day_high, day_low, volume, market_cap, market_state, fetch_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol,
                current_price,
                price_data['previous_close'],
                price_data['day_high'],
                price_data['day_low'],
                price_data['volume'],
                price_data['market_cap'],
                price_data['market_state'],
                price_data['fetch_timestamp']
            ))
            records_added += 1
        except Exception as e:
            logger.error(f"Kayit hatasi {symbol}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Kaydedilen: {records_added}, Atlanan (ayni fiyat): {records_skipped}")
    return records_added, records_skipped


def check_for_anomalies(current_prices: list, last_prices: dict) -> list:
    """
    Anlik fiyatlarda anormal dusus olup olmadigini kontrol eder.
    """
    anomalies = []
    
    for price_data in current_prices:
        symbol = price_data['symbol']
        current_price = price_data['price']
        previous_close = price_data['previous_close']
        
        # 1. Gunluk dusus kontrolu (previous close'a gore)
        if previous_close and previous_close > 0:
            daily_change = ((current_price - previous_close) / previous_close) * 100
            
            if daily_change <= -DROP_THRESHOLD:
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'DAILY_DROP',
                    'change_percent': round(daily_change, 2),
                    'current_price': round(current_price, 2),
                    'previous_price': round(previous_close, 2),
                    'timeframe': 'Daily (vs previous close)'
                })
        
        # 2. Saatlik dusus kontrolu (son kaydedilen fiyata gore)
        last = last_prices.get(symbol)
        if last and last['price'] > 0:
            last_price = last['price']
            hourly_change = ((current_price - last_price) / last_price) * 100
            
            if hourly_change <= -HOURLY_DROP_THRESHOLD:
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'HOURLY_DROP',
                    'change_percent': round(hourly_change, 2),
                    'current_price': round(current_price, 2),
                    'previous_price': round(last_price, 2),
                    'timeframe': f'Hourly (since {last["timestamp"]})'
                })
    
    return anomalies


def save_alert(anomaly: dict):
    """Alerti veritabanina kaydeder. All timestamps in EST."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    est = ZoneInfo('America/New_York')
    timestamp_est = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    cursor.execute('''
        INSERT INTO alerts (symbol, alert_type, alert_message, price_change_percent, 
                           current_price, previous_price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        anomaly['symbol'],
        anomaly['alert_type'],
        f"{anomaly['timeframe']}: {anomaly['change_percent']}% drop",
        anomaly['change_percent'],
        anomaly['current_price'],
        anomaly['previous_price'],
        timestamp_est
    ))
    
    conn.commit()
    conn.close()


def send_alert_email(anomalies: list) -> bool:
    """Anormal dususler icin email gonderir."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT]):
        logger.warning("Email ayarlari eksik.")
        return False
    
    if not anomalies:
        return False
    
    # Son 1 saat icinde ayni alert gonderilmis mi?
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
        logger.info("Tum alertler zaten gonderilmis.")
        return False
    
    subject = f"NASDAQ Alert: {len(new_anomalies)} stock(s) with significant drop"
    
    est = ZoneInfo('America/New_York')
    current_time_est = datetime.now(est).strftime('%Y-%m-%d %H:%M:%S EST')
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #d32f2f; color: white; }}
            .negative {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>NASDAQ Price Drop Alert</h2>
        <p><strong>Time:</strong> {current_time_est}</p>
        <table>
            <tr>
                <th>Symbol</th>
                <th>Alert Type</th>
                <th>Change</th>
                <th>Current Price</th>
                <th>Previous Price</th>
            </tr>
    """
    
    for anomaly in new_anomalies:
        alert_type_text = 'Daily Drop' if anomaly['alert_type'] == 'DAILY_DROP' else 'Hourly Drop'
        html_content += f"""
            <tr>
                <td><strong>{anomaly['symbol']}</strong></td>
                <td>{alert_type_text}</td>
                <td class="negative">{anomaly['change_percent']}%</td>
                <td>${anomaly['current_price']}</td>
                <td>${anomaly['previous_price']}</td>
            </tr>
        """
        save_alert(anomaly)
    
    html_content += """
        </table>
        <p style="margin-top: 20px; color: #666;">
            Thresholds: Daily {daily}%, Hourly {hourly}%
        </p>
    </body>
    </html>
    """.format(daily=DROP_THRESHOLD, hourly=HOURLY_DROP_THRESHOLD)
    
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
        
        # Email gonderildi olarak isaretle
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE alerts SET email_sent = TRUE 
            WHERE created_at > datetime('now', '-1 minute')
        ''')
        conn.commit()
        conn.close()
        
        logger.info(f"Alert emaili gonderildi: {len(new_anomalies)} anomali")
        return True
        
    except Exception as e:
        logger.error(f"Email hatasi: {e}")
        return False


def log_fetch_operation(fetch_type: str, market_state: str, symbols_count: int, 
                        records_added: int, records_skipped: int, errors: str, duration: float):
    """Fetch islemini logla. All timestamps in EST."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    est = ZoneInfo('America/New_York')
    timestamp_est = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    cursor.execute('''
        INSERT INTO fetch_logs 
        (fetch_timestamp, fetch_type, market_state, symbols_fetched, records_added, records_skipped, errors, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp_est, fetch_type, market_state, symbols_count, records_added, records_skipped, errors, duration))
    
    conn.commit()
    conn.close()


def main():
    """Ana fonksiyon."""
    est = ZoneInfo('America/New_York')
    start_time = datetime.now(est)
    logger.info("=" * 60)
    logger.info(f"NASDAQ Tracker v3 - {start_time.strftime('%Y-%m-%d %H:%M:%S EST')}")
    logger.info("=" * 60)
    
    errors = []
    records_added = 0
    records_skipped = 0
    
    try:
        # 1. Piyasa durumunu kontrol et
        market_status = get_market_status()
        logger.info(f"Market status: {market_status}")
        
        # Piyasa kapali ve haftasonuysa calisma
        if not market_status['is_open']:
            if not market_status['is_weekday']:
                logger.info("Weekend - skipping data fetch.")
                log_fetch_operation('SKIPPED', 'WEEKEND', 0, 0, 0, None, 0)
                return
            else:
                logger.info("Market closed - skipping data fetch.")
                log_fetch_operation('SKIPPED', 'CLOSED', 0, 0, 0, None, 0)
                return
        
        # 2. Veritabanini hazirla
        init_database()
        
        # 3. Son fiyatlari al (karsilastirma icin)
        last_prices = get_last_prices()
        logger.info(f"Onceki kayit sayisi: {len(last_prices)} sembol")
        
        # 4. Anlik fiyatlari cek
        realtime_prices = fetch_realtime_prices(NASDAQ_100_SYMBOLS)
        
        if not realtime_prices:
            errors.append("No price data fetched")
            logger.error("Fiyat verisi alinamadi!")
            return
        
        # 5. Veritabanina kaydet (sadece degisenleri)
        records_added, records_skipped = save_realtime_prices(realtime_prices, last_prices)
        
        # 6. Anormal dususleri kontrol et
        anomalies = check_for_anomalies(realtime_prices, last_prices)
        
        if anomalies:
            logger.warning(f"{len(anomalies)} anomali tespit edildi!")
            for a in anomalies:
                logger.warning(f"  {a['symbol']}: {a['change_percent']}% ({a['alert_type']})")
            send_alert_email(anomalies)
        else:
            logger.info("Anormal dusus yok.")
        
        # 7. Islem logu
        duration = (datetime.now(est) - start_time).total_seconds()
        market_state = realtime_prices[0].get('market_state', 'UNKNOWN') if realtime_prices else 'UNKNOWN'
        log_fetch_operation(
            'REALTIME',
            market_state,
            len(NASDAQ_100_SYMBOLS),
            records_added,
            records_skipped,
            "; ".join(errors) if errors else None,
            duration
        )
        
        # 8. Ozet
        logger.info("=" * 60)
        logger.info(f"SUMMARY:")
        logger.info(f"  - Fetched: {len(realtime_prices)} symbols")
        logger.info(f"  - Saved: {records_added} (new/changed prices)")
        logger.info(f"  - Skipped: {records_skipped} (unchanged prices)")
        logger.info(f"  - Anomalies: {len(anomalies)}")
        logger.info(f"  - Duration: {duration:.2f}s")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        traceback.print_exc()
        errors.append(str(e))
        raise


if __name__ == "__main__":
    main()
