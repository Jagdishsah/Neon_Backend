import requests

def analyze_and_fetch(symbol):
    symbol = symbol.upper()
    success_report = []
    final_data = None

    # --- API 1: Suraj Rimal (Unofficial REST) ---
    # This is the 'gold standard' for unofficial NEPSE development.
    url_suraj = f"https://nepseapi.surajrimal.dev/api/v1/stock/latest/{symbol}"
    try:
        res = requests.get(url_suraj, timeout=5)
        if res.status_code == 200:
            data = res.json()
            final_data = {"price": data.get('lastTradedPrice'), "source": "Suraj Rimal API"}
            success_report.append("✅ Suraj Rimal API: SUCCESS")
        else:
            success_report.append(f"❌ Suraj Rimal API: FAILED (Status {res.status_code})")
    except Exception as e:
        success_report.append(f"❌ Suraj Rimal API: ERROR ({str(e)})")

    # --- API 2: Official NEPSE (Direct Endpoint) ---
    # Requires specific headers to bypass bot detection.
    url_official = "https://nepalstock.com/api/nots/market-summary"
    headers = {"User-Agent": "Mozilla/5.0"} # Real implementation needs more headers
    try:
        if not final_data: # Only try if API 1 failed
            res = requests.get(url_official, headers=headers, timeout=5)
            if res.status_code == 200:
                success_report.append("✅ NEPSE Official: SUCCESS (Connection Established)")
                # Parsing official NEPSE requires complex mapping of IDs
            else:
                success_report.append("❌ NEPSE Official: FAILED (Blocked/Zeroed)")
    except:
        success_report.append("❌ NEPSE Official: CONNECTION ERROR")

    # --- API 3: ShareSansar (Fallback Scraper) ---
    if not final_data:
        # Implementing a quick check on the web response
        success_report.append("⚠️ Scraping: PENDING (Use as manual fallback)")

    return final_data, success_report

# Execute and Notify
symbol_to_check = "NABIL"
data, reports = analyze_and_fetch(symbol_to_check)

print(f"--- API SUCCESS NOTIFICATION FOR {symbol_to_check} ---")
for note in reports:
    print(note)

if data:
    print(f"\nFinal Result: {symbol_to_check} Price is {data['price']} (Source: {data['source']})")
else:
    print("\n[!] All APIs currently returning 0 or failing. This usually happens when the market is closed or APIs are under maintenance.")
