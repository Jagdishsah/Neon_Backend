import requests
import json

class NepseDataPro:
    def __init__(self, fsk="1771326338011"):
        self.fsk = fsk
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://nepsealpha.com/"
        }
        self.success_log = []

    def _log(self, name, status, msg=""):
        status_icon = "✅" if status else "❌"
        self.success_log.append(f"{status_icon} {name}: {msg}")

    # --- CATEGORY 1: NAVYA ADVISORS (Live & Macro) ---
    def get_navya_stock_details(self):
        url = "https://navyaadvisors.com/api_endpoint/stocks/list/detail"
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                self._log("Navya Stock Details", True, "Data Found")
                return res.json()
            self._log("Navya Stock Details", False, f"Status {res.status_code}")
        except: self._log("Navya Stock Details", False, "Connection Error")
        return None

    def get_navya_macro(self):
        url = "https://navyaadvisors.com/api_endpoint/market_cap_valuation/macro"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                self._log("Navya Macro Data", True, "Successfully Fetched")
                return res.json()
        except: pass
        self._log("Navya Macro Data", False, "Failed")
        return None

    # --- CATEGORY 2: NEPSE ALPHA (Trading & Depth) ---
    def get_alpha_trading_history(self, symbol="ULHC"):
        # TradingView style history
        url = f"https://www.nepsealpha.com/trading/1/history?fsk={self.fsk}&symbol={symbol}&resolution=1"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200 and "t" in res.text:
                self._log("Alpha History API", True, f"Loaded {symbol}")
                return res.json()
            self._log("Alpha History API", False, "Invalid FSK or Forbidden")
        except: self._log("Alpha History API", False, "Error")
        return None

    def get_alpha_floorsheet(self, symbol="NHPC"):
        url = f"https://nepsealpha.com/floorsheet-live-today/filter?fsk={self.fsk}&page=1&stockSymbol={symbol}&itemsPerPage=500"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                self._log("Alpha Floorsheet", True, f"Found trades for {symbol}")
                return res.json()
        except: pass
        self._log("Alpha Floorsheet", False, "Failed")
        return None

    # --- CATEGORY 3: BROKER ANALYTICS ---
    def get_broker_holding(self, symbol="AKJCL", range_type="Y"):
        # range_type: 'Y' for Year, 'W' for Week
        url = f"https://nepsealpha.com/broker-holding/filter?fsk={self.fsk}&symbol={symbol}&range={range_type}"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                self._log(f"Broker Holding ({range_type})", True, "Data OK")
                return res.json()
        except: pass
        self._log(f"Broker Holding ({range_type})", False, "Failed")
        return None

    def report(self):
        print("\n" + "="*40)
        print("📊 API SUCCESS NOTIFICATION REPORT")
        print("="*40)
        for line in self.success_log:
            print(line)
        print("="*40)

# --- RUN THE ANALYSIS ---
nepse = NepseDataPro(fsk="1771326338011")

# Fetching samples
details = nepse.get_navya_stock_details()
macro = nepse.get_navya_macro()
history = nepse.get_alpha_trading_history("ULHC")
floorsheet = nepse.get_alpha_floorsheet("NHPC")
holdings = nepse.get_broker_holding("AKJCL", "Y")

# Final Notification
nepse.report()
