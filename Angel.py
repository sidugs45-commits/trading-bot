import json, time, datetime, pyotp
import pandas as pd
from SmartApi import SmartConnect

# ========= SETTINGS =========
API_KEY = "kmzJOfrd"
CLIENT_ID = "S690048"
PIN = "5296"
TOTP_SECRET = "NIMHMCCLDM3R3B5X2MDVZJOVQQ"

QTY = 65

# ========= LOGIN =========
obj = SmartConnect(api_key=API_KEY)
totp = pyotp.TOTP(TOTP_SECRET).now()
obj.generateSession(CLIENT_ID, PIN, totp)

print("Login Successful ✅")

# ========= LOAD INSTRUMENT =========
with open("/storage/emulated/0/Download/OpenAPIScripMaster.json") as f:
    instrument_list = json.load(f)

# ========= FIND OPTION =========
def find_option(strike, option_type):
    filtered = []
    for item in instrument_list:
        symbol = item['symbol']
        if ("NIFTY" in symbol and
            "BANKNIFTY" not in symbol and
            "FINNIFTY" not in symbol and
            str(strike) in symbol and
            option_type in symbol):
            try:
                expiry = datetime.datetime.strptime(item['expiry'], "%d%b%Y")
                filtered.append((expiry, item))
            except:
                pass

    if not filtered:
        return None, None

    filtered.sort(key=lambda x: x[0])
    best = filtered[0][1]
    return best['symbol'], best['token']

# ========= VARIABLES =========
prices = []
in_trade = False
entry_price = 0
sl = 0
target = 0
symbol = None
token = None
last_trade_time = 0
cooldown = 300

# ========= LOOP =========
while True:
    try:
        now = datetime.datetime.now().time()

        if not (datetime.time(9,20) <= now <= datetime.time(15,15)):
            print("Market closed")
            time.sleep(30)
            continue

        print("\n🔄 Loop running...")

        # ===== PRICE =====
        ltp = obj.ltpData("NSE", "NIFTY", "26000")
        price = ltp['data']['ltp']
        prices.append(price)

        if len(prices) < 40:
            print("Waiting data...")
            time.sleep(2)
            continue

        df = pd.DataFrame(prices, columns=['price'])

        # ===== EMA =====
        ema9 = df['price'].ewm(span=9).mean().iloc[-1]
        ema22 = df['price'].ewm(span=22).mean().iloc[-1]
        ema33 = df['price'].ewm(span=33).mean().iloc[-1]

        # ===== RSI =====
        delta = df['price'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.iloc[-1]

        # ===== VWAP =====
        df['vol'] = 1
        vwap = (df['price'] * df['vol']).cumsum() / df['vol'].cumsum()
        vwap = vwap.iloc[-1]

        prev_price = df['price'].iloc[-2]

        print(f"Price:{price} RSI:{rsi:.2f}")

        signal = None

        # ===== SNIPER FILTER =====
        ema_gap = abs(ema9 - ema22)

        if 45 < rsi < 55 or ema_gap < 2:
            print("❌ Sideways / Weak")
            continue

        # ===== CE ENTRY =====
        if (ema9 > ema22 > ema33 and
            price > vwap and
            rsi > 60 and
            price > prev_price):

            signal = "CE"

        # ===== PE ENTRY =====
        elif (ema9 < ema22 < ema33 and
              price < vwap and
              rsi < 40 and
              price < prev_price):

            signal = "PE"

        # ===== ENTRY =====
        if signal and not in_trade and time.time() - last_trade_time > cooldown:

            strike = round(price / 50) * 50
            symbol, token = find_option(strike, signal)

            if token is None:
                continue

            premium = obj.ltpData("NFO", symbol, token)['data']['ltp']

            entry_price = premium
            sl = premium * 0.95
            target = premium * 1.08

            obj.placeOrder({
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": "BUY",
                "exchange": "NFO",
                "ordertype": "MARKET",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "quantity": QTY
            })

            print("\n🚀 SNIPER ENTRY:", symbol, premium)

            in_trade = True
            last_trade_time = time.time()

        # ===== EXIT =====
        if in_trade:

            premium = obj.ltpData("NFO", symbol, token)['data']['ltp']
            print("Live:", premium)

            # TRAILING SL
            if premium > entry_price * 1.04:
                sl = entry_price

            if premium <= sl or premium >= target:

                obj.placeOrder({
                    "variety": "NORMAL",
                    "tradingsymbol": symbol,
                    "symboltoken": token,
                    "transactiontype": "SELL",
                    "exchange": "NFO",
                    "ordertype": "MARKET",
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "quantity": QTY
                })

                print("🔚 EXIT")

                in_trade = False

        time.sleep(2)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(2)