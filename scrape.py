import requests
from bs4 import BeautifulSoup

def fetch_live_single_merolagani(symbol):
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    data = {'price': 0.0, 'change': 0.0}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get Price
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if price_tag:
            data['price'] = float(price_tag.text.strip().replace(",", ""))
            
        # Get Change
        change_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPriceChange")
        if change_tag:
            data['change'] = float(change_tag.text.strip().replace(",", ""))
            
        return data
    except Exception as e:
        return data

def get_market_data(symbols):
    """This is the function your app.py is looking for!"""
    results = {}
    for sym in symbols:
        results[sym] = fetch_live_single_merolagani(sym)
    return results
