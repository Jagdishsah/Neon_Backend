import requests
from bs4 import BeautifulSoup

def fetch_live_single_merolagani(symbol):
    """Refined scraping method for Merolagani."""
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    
    # Crucial: Mimic a real browser so they don't block you
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    data = {'price': 0.0, 'change': 0.0, 'high': 0.0, 'low': 0.0}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Error: Could not access {symbol} page (Status {response.status_code})")
            return data

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. GET PRICE (LTP)
        # Try the ID first, then fall back to searching the table
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag:
            data['price'] = float(price_tag.text.strip().replace(",", ""))
        else:
            # Fallback: Find the table cell containing "Market Price"
            price_row = soup.find('th', string=lambda t: t and "Market Price" in t)
            if price_row:
                data['price'] = float(price_row.find_next_sibling('td').text.strip().replace(",", ""))

        # 2. GET CHANGE & 52-WEEK RANGE
        rows = soup.find_all('tr')
        for row in rows:
            text = row.get_text()
            
            # Extract Change
            if "% Change" in text:
                cols = row.find_all('td')
                if cols:
                    try:
                        # Extract only the numeric part before the %
                        change_text = cols[0].text.strip().split('(')[0].replace(",", "")
                        data['change'] = float(change_text)
                    except: pass
            
            # Extract 52 Week High/Low
            if "52 Weeks High - Low" in text:
                tds = row.find_all('td')
                if tds:
                    range_text = tds[-1].text.strip().replace(",", "")
                    if "-" in range_text:
                        parts = range_text.split("-")
                        data['high'] = float(parts[0].strip())
                        data['low'] = float(parts[1].strip())
        
        return data
    except Exception as e:
        print(f"Scraping Error for {symbol}: {e}")
        return data

def get_market_data(symbols):
    """Main function to loop through your symbols."""
    results = {}
    for sym in symbols:
        print(f"Fetching {sym}...")
        results[sym] = fetch_live_single_merolagani(sym)
    return results

# --- TEST IT ---
if __name__ == "__main__":
    # Add your stock symbols here
    my_stocks = ["NABIL", "UPPER", "HRL"]
    
    stock_info = get_market_data(my_stocks)
    
    print("\n--- Final Data ---")
    for sym, info in stock_info.items():
        print(f"{sym}: Price={info['price']}, Change={info['change']}, 52W High={info['high']}")
