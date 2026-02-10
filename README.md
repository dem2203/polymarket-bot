# 🤖 Polymarket Professional Trading Bot

Polymarket prediction market'i üzerinde **tam otonom** çalışan profesyonel trading bot.

## ✨ Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🔄 Otomatik Trading | Market tarama, strateji analizi, emir yürütme |
| 📊 3 Strateji | Momentum, Value, Arbitrage |
| 🛡 Risk Yönetimi | Stop-loss, take-profit, günlük limit, exposure kontrolü |
| 💰 Wallet Yönetimi | Otomatik bakiye/allowance kontrolü |
| 📱 Telegram Bildirimleri | Trade açılış/kapanış, PnL raporları, hata uyarıları |
| 🧪 Dry Run Modu | Gerçek para olmadan test |
| 🚀 Railway Deploy | Dockerfile + railway.toml hazır |

## 🏗 Mimari

```
Market Data (Gamma API) → Strateji Motoru → Risk Manager → Emir Yürütme → Pozisyon Takibi
     ↑                                                                              ↓
 WebSocket ←──────────────────── Monitoring Loop ─────────────────── Telegram Bildirim
```

## 🚀 Kurulum

### 1. Bağımlılıkları Yükle
```bash
pip install -r requirements.txt
```

### 2. Konfigürasyon
```bash
copy .env.example .env
```

`.env` dosyasını düzenleyin:
- `POLYMARKET_PRIVATE_KEY` → Polymarket hesabınızdan: Cash > ... > Export Private Key
- `TELEGRAM_BOT_TOKEN` → @BotFather'dan alın
- `TELEGRAM_CHAT_ID` → @userinfobot'a mesaj gönderin

### 3. Dry Run Test
```bash
set DRY_RUN=true
python main.py
```

### 4. Canlıya Geç
```bash
set DRY_RUN=false
python main.py
```

## ☁️ Railway Deployment

### 1. GitHub'a Push
```bash
git init
git add .
git commit -m "Polymarket Bot v1.0"
git remote add origin https://github.com/YOUR_USER/polymarket-bot.git
git push -u origin main
```

### 2. Railway'de
1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Repo'yu seçin
3. **Variables** sekmesinden `.env` değişkenlerini ekleyin:
   - `POLYMARKET_PRIVATE_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DRY_RUN=false` (canlı için)
   - Diğer parametreler...

## ⚙️ Trading Parametreleri

| Parametre | Varsayılan | Açıklama |
|-----------|------------|----------|
| `DRY_RUN` | `true` | Gerçek emir gönderilmez |
| `MAX_ORDER_SIZE` | `10` | Tek emir max (USDC) |
| `MAX_TOTAL_EXPOSURE` | `100` | Toplam max pozisyon (USDC) |
| `STOP_LOSS_PCT` | `0.15` | Stop-loss %15 |
| `TAKE_PROFIT_PCT` | `0.30` | Take-profit %30 |
| `DAILY_LOSS_LIMIT` | `50` | Günlük max kayıp (USDC) |
| `MIN_CONFIDENCE` | `0.65` | Minimum strateji güven skoru |
| `SCAN_INTERVAL` | `60` | Tarama aralığı (saniye) |

## ⚠️ Risk Uyarısı

Bu bot gerçek para ile işlem yapar. Lütfen:
1. İlk önce `DRY_RUN=true` ile test edin
2. Küçük miktarlarla başlayın
3. Risk parametrelerini kendinize göre ayarlayın
4. Bot'u düzenli izleyin

## 📜 Lisans

MIT
