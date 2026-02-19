import requests
from bs4 import BeautifulSoup

# --- 1. NEW FAST API FETCH (NAVYA ADVISORS) ---
def fetch_live_data_api():
    """Fetches ALL live stock data at once using the Navya API."""
    url = "https://navyaadvisors.com/api_endpoint/stocks/list/detail"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Extract the list from JSON structure
            if isinstance(data, dict):
                for key in data.keys():
                    if isinstance(data[key], list):
                        data = data[key]
                        break
            
            if not isinstance(data, list):
                return None
            
            # Build a fast dictionary for all stocks
            result = {}
            for item in data:
                # Make keys lowercase to avoid case-sensitivity issues
                item_lower = {str(k).lower(): v for k, v in item.items()}
                sym = item_lower.get('symbol', '')
                
                if sym:
                    result[sym.upper()] = {
                        "price": float(item_lower.get('ltp', item_lower.get('lasttradedprice', 0)) or 0),
                        "change": float(item_lower.get('change', item_lower.get('schange', 0)) or 0),
                        "high": float(item_lower.get('high', item_lower.get('highprice', 0)) or 0),
                        "low": float(item_lower.get('low', item_lower.get('lowprice', 0)) or 0)
                    }
            return result
    except Exception as e:
        print(f"API Fetch Error: {e}")
    return None

# --- 2. OLD SCRAPING METHOD (BACKUP) ---
def fetch_live_single_backup(symbol):
    """Original BeautifulSoup scraping method from Merolagani (Fallback)."""
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # LTP
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag: data['price'] = float(price_tag.text.strip().replace(",", ""))
        
        # Change & 52W
        for row in soup.find_all('tr'):
            text = row.text.strip()
            if "52 Weeks High - Low" in text:
                tds = row.find_all('td')
                if tds:
                    nums = tds[-1].text.split("-")
                    if len(nums) == 2:
                        data['high'] = float(nums[0].strip().replace(",", ""))
                        data['low'] = float(nums[1].strip().replace(",", ""))
            if "Change" in text and "%" not in text: 
                tds = row.find_all('td')
                if tds:
                    try: data['change'] = float(tds[-1].text.strip().replace(",", ""))
                    except: pass
    except: pass
    return data

# --- 3. MAIN FETCH CONTROLLER ---
def get_market_data(symbols):
    """Tries API first. If it fails, falls back to the old scraper."""
    api_data = fetch_live_data_api()
    
    results = {}
    for sym in symbols:
        # 1. Try API (Lightning Fast)
        if api_data and sym in api_data:
            results[sym] = api_data[sym]
        # 2. Backup Scraper (Slow but reliable fail-safe)
        else:
            results[sym] = fetch_live_single_backup(sym)
            
    return results
