# 🤖 Polymarket AI Trading Bot V2

**Claude AI ile %8+ mispricing tespiti yapan, Kelly Criterion ile pozisyon alan otonom trading bot.**

50$ → Hayatta kal ya da öl.

## Nasıl Çalışır?

Her **10 dakikada** bir:

1. 📡 **500-1000 market** taranır (Gamma API)
2. 🧠 **Claude AI** ile her market için **fair value** hesaplanır
3. 🎯 **>%8 mispricing** tespit edilir
4. 📊 **Kelly Criterion** ile pozisyon büyüklüğü hesaplanır (max %6 sermaye)
5. 🛡️ Risk kontrolünden geçirilir
6. ⚡ **Limit emir** gönderilir
7. 🔍 Pozisyonlar izlenir (Stop-Loss / Take-Profit)
8. 💰 **Ekonomi raporu** güncellenir (API maliyeti vs gelir)

## Özellikler

| Özellik | Açıklama |
|---------|----------|
| 🧠 AI Brain | Claude Haiku ile fair value hesaplama |
| 📊 Kelly Criterion | Matematiksel pozisyon boyutlandırma |
| 🎯 Mispricing | >%8 fiyatlama hatası tespiti |
| 🔄 Arbitraj | YES + NO < 0.98 risksiz fırsat |
| 🛡️ Risk Yönetimi | SL/TP, günlük limit, hayatta kalma modu |
| 💀 Hayatta Kalma | Bakiye < $5 → tüm işlemler durur |
| 💰 Ekonomi Takibi | API maliyeti vs trading geliri |
| 📱 Telegram | Anlık trade + rapor bildirimleri |
| 🔵 DRY RUN | Gerçek para olmadan test |

## Hızlı Kurulum

```bash
# 1. Kopyala
git clone https://github.com/dem2203/polymarket-bot.git
cd polymarket-bot

# 2. Bağımlılıklar
pip install -r requirements.txt

# 3. .env ayarla
cp .env.example .env
# .env dosyasını düzenle: API key'lerini gir

# 4. Test et (DRY RUN)
python main.py
```

## .env Ayarları

```env
# Zorunlu
ANTHROPIC_API_KEY=sk-ant-...     # Claude API key
POLYMARKET_PRIVATE_KEY=0x...     # Polymarket private key
TELEGRAM_BOT_TOKEN=123:ABC       # Telegram bot token
TELEGRAM_CHAT_ID=123456          # Telegram chat ID

# Trading
DRY_RUN=true                     # İlk test için true!
STARTING_BALANCE=50              # Başlangıç bakiyesi
MAX_KELLY_FRACTION=0.06          # Max %6 sermaye/trade
MISPRICING_THRESHOLD=0.08        # >%8 mispricing
STOP_LOSS_PCT=0.20               # %20 kayıp = çık
TAKE_PROFIT_PCT=0.25             # %25 kâr = sat
SURVIVAL_BALANCE=5.0             # $5 altında dur
```

## Railway Deploy

1. GitHub'a push et
2. [Railway](https://railway.app) → New Project → Deploy from GitHub
3. `dem2203/polymarket-bot` seç
4. Variables'a .env değerlerini ekle
5. Deploy otomatik başlar

## Mimari

```
src/
├── ai/            # Claude AI Brain (fair value)
├── scanner/       # 500-1000 market tarayıcı
├── strategy/      # Kelly + Mispricing + Arbitraj
├── trading/       # Executor + Positions + Risk
├── economics/     # API cost vs revenue tracker
└── notifications/ # Telegram bildirimleri
```

## ⚠️ Risk Uyarısı

Bu bot gerçek para ile işlem yapar. **DRY_RUN=true** ile başlayıp test edin.
Kâr garantisi yoktur. Kaybedebilirsiniz.
