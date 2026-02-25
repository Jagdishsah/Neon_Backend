import requests

def fetch_live_data_api(symbol):
    # Mimicking a browser request to avoid being blocked/zeroed
    url = "https://navyaadvisors.com/api_endpoint/stocks/list/detail"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://navyaadvisors.com/",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        # --- DIAGNOSTIC: Uncomment the line below if you still get 0 ---
        # print(f"DEBUG: First item in response: {data[0] if isinstance(data, list) else 'Not a list'}")

        # Handle different response structures (Dict vs List)
        stocks_list = data if isinstance(data, list) else data.get('data', [])
        
        for stock in stocks_list:
            if str(stock.get('symbol')).upper() == symbol.upper():
                # Check for multiple possible LTP keys
                ltp = stock.get('ltp') or stock.get('last_price') or stock.get('lastTradedPrice') or 0
                return float(ltp)
                
        return 0
    except Exception as e:
        print(f"Error fetching data: {e}")
        return 0

# Test
symbol = "NABIL"
price = fetch_live_data_api(symbol)
print(f"Current Price of {symbol}: {price}")
