import requests
from bs4 import BeautifulSoup
import json

# Set a consistent header to look like a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Referer": "https://merolagani.com/"
}

def fetch_live_data_api():
    """Fetches live stock data with improved error reporting."""
    url = "https://navyaadvisors.com/api_endpoint/stocks/list/detail"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[!] Navya API Error: Status {response.status_code}")
            return None
        
        data = response.json()
        
        # Robustly find the list in the JSON response
        stock_list = []
        if isinstance(data, list):
            stock_list = data
        elif isinstance(data, dict):
            # Try to find any value that is a list (common for Navya's response)
            for val in data.values():
                if isinstance(val, list):
                    stock_list = val
                    break
        
        if not stock_list:
            print("[!] Navya API: Could not find stock list in JSON structure.")
            return None

        result = {}
        for item in stock_list:
            # Safe parsing with defaults
            sym = str(item.get('symbol', item.get('Symbol', ''))).upper()
            if sym:
                result[sym] = {
                    "price": float(item.get('ltp', item.get('lastTradedPrice', 0)) or 0),
                    "change": float(item.get('change', item.get('sChange', 0)) or 0),
                    "high": float(item.get('high', item.get('highPrice', 0)) or 0),
                    "low": float(item.get('low', item.get('lowPrice', 0)) or 0)
                }
        return result
    except Exception as e:
        print(f"[!] API Exception: {e}")
        return None

def fetch_live_single_backup(symbol):
    """Refactored scraper with flexible selection logic."""
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    data = {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0}
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Try specific ID first, then fall back to a search
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if not price_tag:
            # Fallback: Find the label "Market Price" and get the next sibling
            label = soup.find(text=lambda t: "Market Price" in t)
            if label:
                price_tag = label.find_next()

        if price_tag:
            data['price'] = float(price_tag.text.strip().replace(",", ""))
        
        # 2. Extract Table Data (More stable than IDs)
        rows = soup.find_all('tr')
        for row in rows:
            text = row.get_text(strip=True)
            cols = row.find_all('td')
            if len(cols) < 2: continue
            
            val = cols[-1].text.strip().replace(",", "")
            
            if "Change" in text and "%" not in text:
                try: data['change'] = float(val)
                except: pass
            elif "52 Weeks High - Low" in text:
                nums = val.split("-")
                if len(nums) == 2:
                    data['high'] = float(nums[0].strip())
                    data['low'] = float(nums[1].strip())
                    
        return data
    except Exception as e:
        print(f"[!] Scraper Error ({symbol}): {e}")
        return data

def get_market_data(symbols):
    """Orchestrator with logic to handle API failure."""
    print("--- Starting Market Data Fetch ---")
    api_results = fetch_live_data_api()
    
    final_results = {}
    for sym in symbols:
        sym_upper = sym.upper()
        if api_results and sym_upper in api_results:
            print(f"[✓] {sym_upper}: Data from API")
            final_results[sym_upper] = api_results[sym_upper]
        else:
            print(f"[!] {sym_upper}: API failed, trying Merolagani...")
            final_results[sym_upper] = fetch_live_single_backup(sym_upper)
            
    return final_results

# Example Usage
if __name__ == "__main__":
    my_stocks = ["NABIL", "UPPER", "HRL"]
    print(get_market_data(my_stocks))
