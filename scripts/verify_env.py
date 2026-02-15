
import sys
import os
sys.path.append(os.getcwd())

from src.config import settings

print("="*40)
print("BOT CALISMA MODU KONTROLU")
print("="*40)

# 1. .env Dosyası Var mı?
env_exists = os.path.exists(".env")
print(f"Directory: {os.getcwd()}")
print(f".env Dosyasi: {'MEVCUT' if env_exists else 'YOK (Sadece varsayilan ayarlar)'}")

# 2. Dry Run Modu
print(f"Calisma Modu: {'DRY RUN (Sanal)' if settings.dry_run else 'LIVE (Gercek)'}")

# 3. Private Key Kontrolü
has_key = bool(settings.polymarket_private_key)
print(f"Private Key:  {'YUKLU' if has_key else 'YOK'}")

# 4. Positions.json Kontrolü
pos_file = "data/positions.json"
has_pos = os.path.exists(pos_file)
print(f"Hafiza Dosyasi: {'VAR' if has_pos else 'YOK (' + pos_file + ')'}")

print("="*40)
print("SONUC:")
if settings.dry_run:
    print("Bot su an SANAL modda calisiyor. Gercek islem YAPMAZ.")
else:
    print("Bot su an GERCEK modda calisiyor.")

if not has_pos:
    print("Gecmis pozisyon hafizasi YOK. Restart edilirse portfoyu unutur.")
