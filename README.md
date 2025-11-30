# NASDAQ-100 Stock Tracker 📈

Yahoo Finance API kullanarak NASDAQ-100 hisselerini takip eden ve anormal düşüşlerde email bildirimi gönderen otomatik sistem.

## Özellikler

- ✅ NASDAQ-100 hisselerini saatlik olarak takip
- ✅ SQLite veritabanında veri saklama
- ✅ Her fetch işleminde timestamp kaydı
- ✅ Anormal düşüş tespiti (varsayılan: %5)
- ✅ Email bildirimi
- ✅ GitHub Actions ile tam otomasyon

## Kurulum

### 1. Repository'yi Fork/Clone Et

```bash
git clone https://github.com/YOUR_USERNAME/nasdaq-tracker.git
cd nasdaq-tracker
```

### 2. GitHub Secrets Ayarla

Repository Settings > Secrets and variables > Actions > New repository secret:

| Secret Name | Açıklama |
|------------|----------|
| `EMAIL_SENDER` | Gönderen email adresi (Gmail önerilir) |
| `EMAIL_PASSWORD` | Gmail App Password (normal şifre değil!) |
| `EMAIL_RECIPIENT` | Bildirimlerin gönderileceği email |

### 3. Gmail App Password Oluşturma

1. Google Account > Security > 2-Step Verification'ı etkinleştir
2. Google Account > Security > App passwords
3. "Mail" ve "Other" seçip bir isim ver
4. Oluşturulan 16 haneli şifreyi `EMAIL_PASSWORD` olarak kullan

### 4. (Opsiyonel) Variables Ayarla

Repository Settings > Secrets and variables > Actions > Variables:

| Variable Name | Varsayılan | Açıklama |
|--------------|-----------|----------|
| `DROP_THRESHOLD` | `5.0` | Anormal düşüş eşiği (%) |

## Kullanım

### Otomatik Çalışma
GitHub Actions her saat başı otomatik çalışır.

### Manuel Çalıştırma
1. Actions sekmesine git
2. "NASDAQ Tracker" workflow'unu seç
3. "Run workflow" butonuna tıkla

### Lokal Test
```bash
pip install -r requirements.txt
python nasdaq_tracker.py
```

## Veritabanı Şeması

### stock_prices
```sql
- id: INTEGER PRIMARY KEY
- symbol: TEXT (hisse sembolü)
- date: DATE (tarih)
- open, high, low, close, adj_close: REAL (fiyatlar)
- volume: INTEGER (işlem hacmi)
- fetch_timestamp: DATETIME (çekilme zamanı)
```

### fetch_logs
```sql
- id: INTEGER PRIMARY KEY
- fetch_timestamp: DATETIME
- symbols_fetched: INTEGER
- records_added: INTEGER
- records_updated: INTEGER
- errors: TEXT
- duration_seconds: REAL
```

### alerts
```sql
- id: INTEGER PRIMARY KEY
- symbol: TEXT
- alert_type: TEXT
- alert_message: TEXT
- price_change_percent: REAL
- created_at: DATETIME
- email_sent: BOOLEAN
```

## ML Modeli için Veri Kullanımı

```python
import sqlite3
import pandas as pd

# Veritabanına bağlan
conn = sqlite3.connect('nasdaq_data.db')

# Tüm verileri çek
df = pd.read_sql_query('''
    SELECT symbol, date, open, high, low, close, volume, fetch_timestamp
    FROM stock_prices
    ORDER BY symbol, date
''', conn)

# Belirli bir hisse için
aapl = pd.read_sql_query('''
    SELECT * FROM stock_prices 
    WHERE symbol = 'AAPL' 
    ORDER BY date
''', conn)

conn.close()
```

## Takip Edilen NASDAQ-100 Hisseleri

AAPL, MSFT, AMZN, NVDA, META, GOOGL, GOOG, TSLA, AVGO, COST, NFLX, AMD, PEP, ADBE, CSCO, TMUS, INTC, CMCSA, TXN, QCOM, INTU, AMGN, HON, AMAT, ISRG, BKNG, SBUX, VRTX, MDLZ, GILD, ADP, REGN, ADI, LRCX, PANW, KLAC, SNPS, MELI, CDNS, ASML, MAR, ABNB, PYPL, CRWD, ORLY, CTAS, MNST, NXPI, CSX, MRVL, PCAR, WDAY, CEG, ROP, ADSK, CPRT, DXCM, FTNT, CHTR, AEP, PAYX, ODFL, MCHP, KDP, KHC, FAST, ROST, AZN, EXC, EA, VRSK, CTSH, LULU, GEHC, IDXX, XEL, CCEP, DDOG, CSGP, BKR, TTWO, ANSS, ON, ZS, GFS, FANG, CDW, BIIB, ILMN, WBD, MDB, TEAM, MRNA, DLTR, SIRI, LCID, RIVN, ARM, SMCI, COIN

## Notlar

- GitHub Actions ücretsiz kullanımı ayda 2000 dakika ile sınırlı
- Her çalışma yaklaşık 1-2 dakika sürer
- Saatlik çalışma ile ayda ~720 dakika kullanılır
- NYSE kapalıyken (hafta sonları, tatiller) veri değişmez ama sistem yine de çalışır

## Lisans

MIT
