"""
NASDAQ-100 Stock Tracker v4 - Smart Real-time Price Tracking with Benchmark
============================================================================
Yahoo Finance API ile NASDAQ-100 hisselerinin ANLIK fiyatlarini cekip SQLite'a kaydeder.
Sadece piyasa acikken ve fiyat degistiginde kayit yapar.
QQQ benchmark karsilastirmasi ile gercek anomalileri tespit eder.
Anormal dususlerde email bildirimi gonderir.

Alert Filters:
- MIN_PRICE_FOR_ALERT: Ucuz hisseleri filtreler (varsayilan $5)
- MIN_ABS_MOVE_DOLLAR: Kucuk dolar hareketlerini filtreler (varsayilan $0.50)
- MIN_MINUTES_BETWEEN_SAME_ALERT: Ayni alert icin spam engeli (varsayilan 60 dk)
- QQQ Benchmark: Piyasa geneline gore goreceli dusus kontrolu
- Sadece regular market saatlerinde alert uretir (09:30-16:00 EST)
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

# NASDAQ-100 sembolleri + QQQ benchmark
NASDAQ_100_SYMBOLS = [
    "QQQ",  # Benchmark - NASDAQ-100 ETF (ilk sirada olmali)
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

BENCHMARK_SYMBOL = "QQQ"

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

# Benchmark goreceli dusus esigi
# Hisse, QQQ'dan bu kadar fazla dustuyse alert uret
RELATIVE_DROP_THRESHOLD = float(os.environ.get('RELATIVE_DROP_THRESHOLD', '3.0'))

# Ek filtreler
MIN_PRICE_FOR_ALERT = float(os.environ.get('MIN_PRICE_FOR_ALERT', '5.0'))
MIN_ABS_MOVE_DOLLAR = float(os.environ.get('MIN_ABS_MOVE_DOLLAR', '0.50'))
MIN_MINUTES_BETWEEN_SAME_ALERT = int(os.environ.get('MIN_MINUTES_BETWEEN_SAME_ALERT', '60'))


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
        
        weekday = now_est.weekday()
        is_weekday = weekday < 5
        
        current_time = now_est.time()
        
        market_open = time(9, 30)
        market_close = time(16, 0)
        pre_market_open = time(4, 0)
        after_hours_close = time(20, 0)
        
        is_regular_hours = market_open <= current_time <= market_close
        is_extended_hours = (pre_market_open <= current_time < market_open) or \
                           (market_close < current_time <= after_hours_close)
        
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_timestamp DATETIME NOT NULL,
            fetch_type TEXT,
            market_state TEXT,
            symbols_fetched INTEGER,
            records_added INTEGER,
            records_skipped INTEGER,
            benchmark_change REAL,
            errors TEXT,
            duration_seconds REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            alert_message TEXT,
            price_change_percent REAL,
            benchmark_change_percent REAL,
            relative_change_percent REAL,
            current_price REAL,
            previous_price REAL,
            created_at DATETIME NOT NULL,
            email_sent BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_symbol ON realtime_prices(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_timestamp ON realtime_prices(fetch_timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rt_symbol_timestamp ON realtime_prices(symbol, fetch_timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_symbol_type ON alerts(symbol, alert_type)')
    
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
    Tum timestamp'ler NASDAQ saat dilimi (EST) ile kaydedilir.
    """
    logger.info(f"{len(symbols)} hisse icin anlik fiyatlar cekiliyor...")
    
    results = []
    est = ZoneInfo('America/New_York')
    fetch_timestamp = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    tickers = yf.Tickers(' '.join(symbols))
    
    for symbol in symbols:
        try:
            ticker = tickers.tickers.get(symbol)
            if ticker is None:
                continue
            
            info = ticker.info
            market_state = info.get('marketState', 'UNKNOWN')
            
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
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    records_added = 0
    records_skipped = 0
    
    for price_data in prices:
        symbol = price_data['symbol']
        current_price = price_data['price']
        
        last = last_prices.get(symbol)
        
        if last:
            last_price = last['price']
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


def get_benchmark_change(prices: list) -> float:
    """QQQ benchmark degisim yuzdesini hesaplar."""
    for price_data in prices:
        if price_data['symbol'] == BENCHMARK_SYMBOL:
            current = price_data['price']
            prev_close = price_data['previous_close']
            if prev_close and prev_close > 0:
                change = ((current - prev_close) / prev_close) * 100
                logger.info(f"Benchmark ({BENCHMARK_SYMBOL}): {change:.2f}% (${prev_close:.2f} -> ${current:.2f})")
                return change
    logger.warning(f"Benchmark ({BENCHMARK_SYMBOL}) bulunamadi!")
    return 0.0


def should_suppress_alert(symbol: str, alert_type: str) -> bool:
    """
    Ayni sembol + ayni alert tipi icin spam kontrolu.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT COUNT(*) FROM alerts 
            WHERE symbol = ? 
              AND alert_type = ?
              AND created_at > datetime('now', '-{MIN_MINUTES_BETWEEN_SAME_ALERT} minutes')
        ''', (symbol, alert_type))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.warning(f"Alert bastirma kontrolu yapilamadi ({symbol} - {alert_type}): {e}")
        return False


def check_for_anomalies(current_prices: list, last_prices: dict, benchmark_change: float) -> list:
    """
    Anlik fiyatlarda anormal dusus olup olmadigini kontrol eder.
    
    Alert Turleri:
    1. RELATIVE_DROP: Hisse QQQ'dan RELATIVE_DROP_THRESHOLD kadar fazla dustuyse
    2. ABSOLUTE_DROP: Hisse mutlak olarak DROP_THRESHOLD'dan fazla dustuyse VE QQQ neredeyse duzse
    3. HOURLY_DROP: Son kayda gore HOURLY_DROP_THRESHOLD'dan fazla dustuyse
    
    Filtreler:
    - Ucuz hisseler (< MIN_PRICE_FOR_ALERT)
    - Kucuk dolar hareketleri (< MIN_ABS_MOVE_DOLLAR)
    - Spam engeli (should_suppress_alert)
    - QQQ kendisi icin alert uretme
    """
    anomalies = []
    
    for price_data in current_prices:
        symbol = price_data['symbol']
        current_price = price_data['price']
        previous_close = price_data['previous_close']
        
        # QQQ icin alert uretme (benchmark)
        if symbol == BENCHMARK_SYMBOL:
            continue
        
        # Ucuz hisseleri filtrele
        if current_price is None or current_price < MIN_PRICE_FOR_ALERT:
            continue
        
        # 1. Gunluk degisim hesapla
        if previous_close and previous_close > 0:
            daily_change = ((current_price - previous_close) / previous_close) * 100
            abs_move_daily = abs(current_price - previous_close)
            
            # Benchmark'a gore goreceli degisim
            relative_change = daily_change - benchmark_change
            
            # RELATIVE_DROP: QQQ'ya gore anormal dusus
            if (
                relative_change <= -RELATIVE_DROP_THRESHOLD and
                daily_change < 0 and  # Hisse gercekten dusuyor olmali
                abs_move_daily >= MIN_ABS_MOVE_DOLLAR and
                not should_suppress_alert(symbol, 'RELATIVE_DROP')
            ):
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'RELATIVE_DROP',
                    'change_percent': round(daily_change, 2),
                    'benchmark_change': round(benchmark_change, 2),
                    'relative_change': round(relative_change, 2),
                    'current_price': round(current_price, 2),
                    'previous_price': round(previous_close, 2),
                    'timeframe': f'vs {BENCHMARK_SYMBOL}'
                })
            
            # ABSOLUTE_DROP: Mutlak buyuk dusus (piyasa duzken)
            elif (
                daily_change <= -DROP_THRESHOLD and
                benchmark_change > -2.0 and  # QQQ neredeyse duz veya yukseliyorsa
                abs_move_daily >= MIN_ABS_MOVE_DOLLAR and
                not should_suppress_alert(symbol, 'ABSOLUTE_DROP')
            ):
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'ABSOLUTE_DROP',
                    'change_percent': round(daily_change, 2),
                    'benchmark_change': round(benchmark_change, 2),
                    'relative_change': round(relative_change, 2),
                    'current_price': round(current_price, 2),
                    'previous_price': round(previous_close, 2),
                    'timeframe': 'Daily (absolute)'
                })
        
        # 2. Saatlik dusus kontrolu (son kayda gore)
        last = last_prices.get(symbol)
        if last and last['price'] > 0:
            last_price = last['price']
            hourly_change = ((current_price - last_price) / last_price) * 100
            abs_move_hourly = abs(current_price - last_price)
            
            if (
                hourly_change <= -HOURLY_DROP_THRESHOLD and
                abs_move_hourly >= MIN_ABS_MOVE_DOLLAR and
                not should_suppress_alert(symbol, 'HOURLY_DROP')
            ):
                anomalies.append({
                    'symbol': symbol,
                    'alert_type': 'HOURLY_DROP',
                    'change_percent': round(hourly_change, 2),
                    'benchmark_change': round(benchmark_change, 2),
                    'relative_change': None,
                    'current_price': round(current_price, 2),
                    'previous_price': round(last_price, 2),
                    'timeframe': f'Since {last["timestamp"]}'
                })
    
    return anomalies


def save_alert(anomaly: dict):
    """Alerti veritabanina kaydeder."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    est = ZoneInfo('America/New_York')
    timestamp_est = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    cursor.execute('''
        INSERT INTO alerts (symbol, alert_type, alert_message, price_change_percent, 
                           benchmark_change_percent, relative_change_percent,
                           current_price, previous_price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        anomaly['symbol'],
        anomaly['alert_type'],
        f"{anomaly['timeframe']}: {anomaly['change_percent']}% drop",
        anomaly['change_percent'],
        anomaly.get('benchmark_change'),
        anomaly.get('relative_change'),
        anomaly['current_price'],
        anomaly['previous_price'],
        timestamp_est
    ))
    
    conn.commit()
    conn.close()


def send_alert_email(anomalies: list, benchmark_change: float) -> bool:
    """Anormal dususler icin email gonderir."""
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT]):
        logger.warning("Email ayarlari eksik.")
        return False
    
    if not anomalies:
        return False
    
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
    
    subject = f"NASDAQ Alert: {len(new_anomalies)} stock(s) with unusual drop"
    
    est = ZoneInfo('America/New_York')
    current_time_est = datetime.now(est).strftime('%Y-%m-%d %H:%M:%S EST')
    
    # Benchmark durumu
    if benchmark_change >= 0:
        benchmark_status = f"<span style='color: green;'>+{benchmark_change:.2f}%</span>"
    else:
        benchmark_status = f"<span style='color: red;'>{benchmark_change:.2f}%</span>"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #d32f2f; color: white; }}
            .negative {{ color: red; font-weight: bold; }}
            .positive {{ color: green; }}
            .benchmark-box {{ background-color: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <h2>NASDAQ Price Drop Alert</h2>
        <p><strong>Time:</strong> {current_time_est}</p>
        
        <div class="benchmark-box">
            <strong>Market Benchmark ({BENCHMARK_SYMBOL}):</strong> {benchmark_status}
        </div>
        
        <table>
            <tr>
                <th>Symbol</th>
                <th>Alert Type</th>
                <th>Change</th>
                <th>vs {BENCHMARK_SYMBOL}</th>
                <th>Current</th>
                <th>Previous</th>
            </tr>
    """
    
    alert_type_labels = {
        'RELATIVE_DROP': 'Relative Drop',
        'ABSOLUTE_DROP': 'Absolute Drop',
        'HOURLY_DROP': 'Hourly Drop'
    }
    
    for anomaly in new_anomalies:
        alert_type_text = alert_type_labels.get(anomaly['alert_type'], anomaly['alert_type'])
        relative_text = f"{anomaly['relative_change']}%" if anomaly.get('relative_change') is not None else "N/A"
        
        html_content += f"""
            <tr>
                <td><strong>{anomaly['symbol']}</strong></td>
                <td>{alert_type_text}</td>
                <td class="negative">{anomaly['change_percent']}%</td>
                <td class="negative">{relative_text}</td>
                <td>${anomaly['current_price']}</td>
                <td>${anomaly['previous_price']}</td>
            </tr>
        """
        save_alert(anomaly)
    
    html_content += f"""
        </table>
        <p style="margin-top: 20px; color: #666;">
            <strong>Alert Thresholds:</strong><br>
            - Relative Drop (vs {BENCHMARK_SYMBOL}): {RELATIVE_DROP_THRESHOLD}%<br>
            - Absolute Drop: {DROP_THRESHOLD}% (when {BENCHMARK_SYMBOL} is flat)<br>
            - Hourly Drop: {HOURLY_DROP_THRESHOLD}%<br>
            - Min Price: ${MIN_PRICE_FOR_ALERT}, Min Move: ${MIN_ABS_MOVE_DOLLAR}
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
                        records_added: int, records_skipped: int, benchmark_change: float,
                        errors: str, duration: float):
    """Fetch islemini logla."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    est = ZoneInfo('America/New_York')
    timestamp_est = datetime.now(est).strftime('%Y-%m-%dT%H:%M:%S EST')
    
    cursor.execute('''
        INSERT INTO fetch_logs 
        (fetch_timestamp, fetch_type, market_state, symbols_fetched, records_added, records_skipped, benchmark_change, errors, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp_est, fetch_type, market_state, symbols_count, records_added, records_skipped, benchmark_change, errors, duration))
    
    conn.commit()
    conn.close()


def main():
    """Ana fonksiyon."""
    est = ZoneInfo('America/New_York')
    start_time = datetime.now(est)
    logger.info("=" * 60)
    logger.info(f"NASDAQ Tracker v4 - {start_time.strftime('%Y-%m-%d %H:%M:%S EST')}")
    logger.info("=" * 60)
    
    errors = []
    records_added = 0
    records_skipped = 0
    benchmark_change = 0.0
    
    try:
        market_status = get_market_status()
        logger.info(f"Market status: {market_status}")
        
        if not market_status['is_open']:
            if not market_status['is_weekday']:
                logger.info("Weekend - skipping data fetch.")
                log_fetch_operation('SKIPPED', 'WEEKEND', 0, 0, 0, 0, None, 0)
                return
            else:
                logger.info("Market closed - skipping data fetch.")
                log_fetch_operation('SKIPPED', 'CLOSED', 0, 0, 0, 0, None, 0)
                return
        
        init_database()
        
        last_prices = get_last_prices()
        logger.info(f"Onceki kayit sayisi: {len(last_prices)} sembol")
        
        realtime_prices = fetch_realtime_prices(NASDAQ_100_SYMBOLS)
        
        if not realtime_prices:
            errors.append("No price data fetched")
            logger.error("Fiyat verisi alinamadi!")
            return
        
        # Benchmark degisimini hesapla
        benchmark_change = get_benchmark_change(realtime_prices)
        
        records_added, records_skipped = save_realtime_prices(realtime_prices, last_prices)
        
        # Sadece regular hours'da alert kontrolu
        anomalies = []
        if market_status['is_regular_hours']:
            anomalies = check_for_anomalies(realtime_prices, last_prices, benchmark_change)
        else:
            logger.info("Extended hours - anomali kontrolu yapilmadi.")
        
        if anomalies:
            logger.warning(f"{len(anomalies)} anomali tespit edildi!")
            for a in anomalies:
                rel = f", vs QQQ: {a.get('relative_change')}%" if a.get('relative_change') else ""
                logger.warning(f"  {a['symbol']}: {a['change_percent']}% ({a['alert_type']}{rel})")
            send_alert_email(anomalies, benchmark_change)
        else:
            logger.info("Anormal dusus yok.")
        
        duration = (datetime.now(est) - start_time).total_seconds()
        market_state = realtime_prices[0].get('market_state', 'UNKNOWN') if realtime_prices else 'UNKNOWN'
        log_fetch_operation(
            'REALTIME',
            market_state,
            len(NASDAQ_100_SYMBOLS),
            records_added,
            records_skipped,
            benchmark_change,
            "; ".join(errors) if errors else None,
            duration
        )
        
        logger.info("=" * 60)
        logger.info(f"SUMMARY:")
        logger.info(f"  - Benchmark ({BENCHMARK_SYMBOL}): {benchmark_change:.2f}%")
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
