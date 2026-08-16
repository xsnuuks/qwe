import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Prices
PRICE_NORMAL = 15
PRICE_DISCOUNT = 10

# Referral requirement
REFERRALS_NEEDED = 2
