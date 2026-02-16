import shutil
import requests
from bs4 import BeautifulSoup
import json
import os
import csv
from datetime import datetime
from tabulate import tabulate
from colorama import Fore, Style, init
import urllib3

# --- CONNECTION SETTINGS ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
init(autoreset=True)

# --- FILES ---
PORTFOLIO_FILE = "portfolio.json"
HISTORY_FILE = "sales_history.json"
WATCHLIST_FILE = "watchlist.json"
DIARY_FILE = "trading_diary.txt"

# --- NEPAL GOVT FEES (TIERED 2024/25) ---
SEBON_FEE = 0.015 / 100
DP_CHARGE = 25
CGT_SHORT = 7.5 / 100
CGT_LONG = 5.0 / 100

def get_broker_commission(amount):
    """Tiered Broker Commission Structure"""
    if amount <= 50000: rate = 0.36 / 100
    elif amount <= 500000: rate = 0.33 / 100
    elif amount <= 2000000: rate = 0.31 / 100
    elif amount <= 10000000: rate = 0.27 / 100
    else: rate = 0.24 / 100
    return max(10, amount * rate)

# --- HELPER FUNCTIONS ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_valid_input(prompt, type_cast=str):
    while True:
        try:
            val = input(prompt).strip()
            if type_cast == str: return val
            if val == "": return 0
            return type_cast(val)
        except ValueError:
            print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")

def print_banner():
    print(f"""{Fore.CYAN}
╔═══════════════════════════════════════════════════════════════╗
║   {Fore.YELLOW}█▀▀█ █▀▀ █▀▀█ █▀▀ █▀▀█ █▀▀▄ █▀▀█ █   {Fore.CYAN}                  ║
║   {Fore.YELLOW}█  █ █▀▀ █▄▄▀ ▀▀█ █  █ █  █ █▄▄█ █   {Fore.CYAN}                  ║
║   {Fore.YELLOW}█▀▀▀ ▀▀▀ ▀ ▀▀ ▀▀▀ ▀▀▀▀ ▀  ▀ ▀  ▀ ▀▀▀ {Fore.CYAN}                  ║
║   {Fore.GREEN}NEPSE TERMINAL v13.0 (Bulletproof)   {Fore.CYAN}                  ║
╚═══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}""")

# --- DATA MANAGER (SAFE SAVE) ---
def load_data(filename, default=None):
    if not os.path.exists(filename):
        if default is not None:
            save_data(filename, default)
            return default
        return {} if filename == WATCHLIST_FILE else []
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            if filename == WATCHLIST_FILE and data and isinstance(list(data.values())[0], (int, float)):
                return {k: {'target': v, 'remark': '-'} for k, v in data.items()}
            return data
    except:
        return default if default else ({} if filename == WATCHLIST_FILE else [])

def save_data(filename, data):
    """Atomic Save: Writes to temp file first to prevent corruption."""
    temp_file = filename + ".tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=4)
        if os.path.exists(filename):
            os.remove(filename)
        os.rename(temp_file, filename)
    except Exception as e:
        print(f"{Fore.RED}Error Saving Data: {e}{Style.RESET_ALL}")

def backup_data():
    if not os.path.exists("backups"): os.makedirs("backups")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if os.path.exists(PORTFOLIO_FILE): shutil.copy(PORTFOLIO_FILE, f"backups/port_{timestamp}.json")

# --- SCRAPING ENGINE (ROBUST) ---
def fetch_live_data(symbol):
    """Scrapes data with Error Handling"""
    url = f"https://merolagani.com/CompanyDetail.aspx?symbol={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://merolagani.com/'
    }
    
    result = {'price': 0, 'high52': 0, 'low52': 0, 'change': 0, 'status': 'Error'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        if response.status_code != 200: return result
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        price_tag = soup.select_one("#ctl00_ContentPlaceHolder1_CompanyDetail1_lblMarketPrice")
        if not price_tag:
             label = soup.find('th', string=lambda t: t and "Market Price" in t)
             if label: price_tag = label.find_next('td')

        if price_tag:
            result['price'] = float(price_tag.text.strip().replace(",", ""))
            result['status'] = 'Ok'

        tables = soup.find_all('table')
        for table in tables:
            for row in table.find_all('tr'):
                text = row.text.strip()
                if "52 Weeks High - Low" in text:
                    tds = row.find_all('td')
                    if tds:
                        parts = tds[-1].text.strip().split('-')
                        if len(parts) >= 2:
                            result['high52'] = float(parts[0].replace(',', ''))
                            result['low52'] = float(parts[1].replace(',', ''))
                
                if "Previous Closing" in text and result['price']:
                    tds = row.find_all('td')
                    if tds:
                        prev = float(tds[-1].text.strip().replace(',', ''))
                        result['change'] = result['price'] - prev
    except: pass
    return result

def update_portfolio_prices(portfolio):
    print(f"\n{Fore.CYAN}>>> UPDATING PRICES...{Style.RESET_ALL}")
    count = 0
    total = len(portfolio)
    for symbol in portfolio:
        count += 1
        print(f"[{count}/{total}] Fetching {symbol}...", end="\r")
        live_data = fetch_live_data(symbol)
        if live_data['status'] == 'Ok':
            portfolio[symbol]['cached_ltp'] = live_data['price']
            portfolio[symbol]['cached_high52'] = live_data['high52']
            portfolio[symbol]['cached_low52'] = live_data['low52']
            portfolio[symbol]['cached_change'] = live_data['change']
            portfolio[symbol]['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_data(PORTFOLIO_FILE, portfolio)
    print(f"\n{Fore.GREEN}✔ Prices Updated!{Style.RESET_ALL}")

# --- MATH CORE (ACCURATE TAX) ---
def calculate_metrics(units, total_buy_cost, current_price, is_long_term=False):
    sell_amount = units * current_price
    commission = get_broker_commission(sell_amount)
    deductions = commission + (sell_amount * SEBON_FEE) + DP_CHARGE
    net_receivable = sell_amount - deductions
    
    gross_pl = net_receivable - total_buy_cost
    
    # Tax Logic: Tax ONLY on Profit
    tax_rate = CGT_LONG if is_long_term else CGT_SHORT
    
    if gross_pl > 0:
        tax_amount = gross_pl * tax_rate
        net_pl = gross_pl - tax_amount
    else:
        tax_amount = 0
        net_pl = gross_pl # No tax on loss

    pl_percent = (net_pl / total_buy_cost) * 100 if total_buy_cost > 0 else 0
    
    # Approx Break Even
    est_rate = 0.0036 + SEBON_FEE
    be_price = (total_buy_cost + DP_CHARGE) / (units * (1 - est_rate)) if units else 0
    
    return [net_receivable, net_pl, pl_percent, be_price, tax_amount]

# --- FEATURES ---

def daily_diary():
    while True:
        clear_screen()
        print(f"{Fore.BLUE}--- TRADING DIARY (Internal) ---{Style.RESET_ALL}")
        
        if os.path.exists(DIARY_FILE):
            print(f"{Fore.YELLOW}Recent Entries:{Style.RESET_ALL}")
            with open(DIARY_FILE, 'r') as f:
                lines = f.readlines()
                for line in lines[-15:]:
                    print(f"  {line.strip()}")
        else:
            print("No entries yet.")
            
        print("-" * 50)
        print("[A]dd Note | [C]lear All | [B]ack")
        choice = input(">> ").lower()
        
        if choice == 'a':
            note = input(f"{Fore.GREEN}Write Note: {Style.RESET_ALL}")
            if note:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                with open(DIARY_FILE, "a") as f:
                    f.write(f"[{timestamp}] {note}\n")
                print("Saved.")
        elif choice == 'c':
            if input("Confirm Clear All? (y/n): ") == 'y':
                open(DIARY_FILE, 'w').close()
                print("Cleared.")
        elif choice == 'b': break

def view_portfolio(portfolio):
    if not portfolio: print("Empty Portfolio."); return
    sort_mode = '0' # Default Date
    
    while True:
        clear_screen()
        print_banner()
        
        table_data = []
        alerts = []
        total_inv = 0; total_val = 0; total_pl = 0; day_change = 0
        last_update_time = "Never"
        processed = []
        
        # 1. Process Data
        for sym, data in portfolio.items():
            ltp = data.get('cached_ltp', 0)
            change = data.get('cached_change', 0)
            ts = data.get('last_updated', '-')
            if ts != '-': last_update_time = ts
            
            units = data['units']
            cost = data['total_cost']
            wacc = cost / units if units else 0
            
            # Use Short Term tax for conservative view
            metrics = calculate_metrics(units, cost, ltp, is_long_term=False)
            curr_val = units * ltp
            net_pl = metrics[1]
            pl_perc = metrics[2]
            be = metrics[3]
            
            day_change += (change * units)
            total_inv += cost
            total_val += curr_val
            total_pl += net_pl
            
            processed.append({
                'sym': sym, 'sec': data.get('sector', '-'), 'units': units, 
                'wacc': wacc, 'ltp': ltp, 'val': curr_val, 'be': be,
                'sl': data.get('stop_loss', 0), 'pl': net_pl, 'pl_p': pl_perc,
                'note': data.get('note', '')
            })

        # 2. Sorting
        if sort_mode == '1': processed.sort(key=lambda x: x['val'], reverse=True)
        elif sort_mode == '2': processed.sort(key=lambda x: x['pl'], reverse=True)
        elif sort_mode == '3': processed.sort(key=lambda x: x['pl'])
        elif sort_mode == '4': processed.sort(key=lambda x: x['pl_p'], reverse=True)

        # 3. Build Table
        for p in processed:
            # Panic Alert
            if p['sl'] > 0 and p['ltp'] < p['sl'] and p['ltp'] > 0:
                alerts.append(f"⚠️ PANIC: {p['sym']} @ {p['ltp']} (SL: {p['sl']})")
                sym_disp = f"{Fore.RED}{p['sym']} (!){Style.RESET_ALL}"
            else: sym_disp = p['sym']
            
            if p['note']: sym_disp += f" {Fore.BLUE}[N]{Style.RESET_ALL}"
            pl_col = Fore.GREEN if p['pl'] > 0 else Fore.RED
            
            table_data.append([
                sym_disp, p['sec'], p['units'], f"{p['wacc']:.1f}",
                f"{p['ltp']}", f"{p['val']:,.0f}", 
                f"{p['be']:.1f}", f"{p['sl']}", 
                f"{pl_col}{p['pl']:,.0f}{Style.RESET_ALL}",
                f"{pl_col}{p['pl_p']:.1f}%{Style.RESET_ALL}"
            ])

        print(f"{Fore.YELLOW}Data Cached: {last_update_time}{Style.RESET_ALL}")
        if alerts:
            for a in alerts: print(f"{Fore.RED}{a}{Style.RESET_ALL}")
            
        headers = ["Stock", "Sector", "Qty", "WACC", "LTP", "Value", "BE", "SL", "P/L", "%"]
        print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))
        
        # 4. Summary Table
        tot_perc = (total_pl / total_inv * 100) if total_inv > 0 else 0
        m_col = Fore.GREEN if total_pl > 0 else Fore.RED
        d_col = Fore.GREEN if day_change > 0 else Fore.RED
        
        summary_table = [[
            f"Rs. {total_inv:,.0f}",
            f"Rs. {total_val:,.0f}",
            f"{d_col}Rs. {day_change:,.0f}{Style.RESET_ALL}",
            f"{m_col}Rs. {total_pl:,.0f}{Style.RESET_ALL}",
            f"{m_col}{tot_perc:.2f}%{Style.RESET_ALL}"
        ]]
        
        print(f"\n{Fore.WHITE}=== PORTFOLIO SUMMARY ==={Style.RESET_ALL}")
        sum_headers = ["Total Investment", "Current Value", "Day Change", "Total P/L", "Return %"]
        print(tabulate(summary_table, headers=sum_headers, tablefmt="heavy_grid"))
        
        # 5. Show Notes
        notes_found = [p for p in processed if p['note']]
        if notes_found:
            print(f"\n{Fore.BLUE}--- 📝 STOCK NOTES ---{Style.RESET_ALL}")
            for p in notes_found:
                print(f"{Fore.YELLOW}{p['sym']}:{Style.RESET_ALL} {p['note']}")

        # Menu
        print(f"\n{Fore.CYAN}COMMANDS:{Style.RESET_ALL} [U]pdate Data | [S]ort List | [B]ack to Menu")
        cmd = input(">> ").lower()
        
        if cmd == 'u': update_portfolio_prices(portfolio)
        elif cmd == 's':
            print("Sort by: [1]Value  [2]Profit  [3]Loss  [4]% Return  [0]Date Added")
            sort_mode = input("Select Mode: ")
        elif cmd == 'b': break

def manage_watchlist(watchlist):
    while True:
        clear_screen()
        print(f"{Fore.BLUE}--- WATCHLIST (Live Check) ---{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Fetching live data...{Style.RESET_ALL}")
        table = []
        
        for s, d in watchlist.items():
            tgt = d.get('target', 0)
            rem = d.get('remark', '-')
            
            data = fetch_live_data(s)
            ltp = data['price']
            high = data['high52']
            low = data['low52']
            
            if ltp > 0:
                if tgt > 0 and ltp <= tgt: signal = f"{Fore.GREEN}BUY NOW{Style.RESET_ALL}"
                else: signal = "WAIT"
                
                if high > low:
                    pos = ((ltp - low) / (high - low)) * 100
                    pos_str = f"{pos:.0f}%"
                else: pos_str = "-"
                ltp_str = f"{ltp}"
            else:
                ltp_str = "Error"; signal = "-"; pos_str = "-"; high = "-"; low = "-"
            
            table.append([s, tgt, ltp_str, high, low, pos_str, signal, rem])
            
        print(tabulate(table, headers=["Stock", "Target", "LTP", "52W High", "52W Low", "Pos %", "Signal", "Remark"], tablefmt="fancy_grid"))
        
        print("\n[A]dd | [E]dit | [R]emove | [B]ack")
        c = input(">> ").lower()
        
        if c == 'a':
            s = input("Symbol: ").upper()
            t = get_valid_input("Target: ", float)
            r = input("Remark: ")
            watchlist[s] = {'target': t, 'remark': r}
            save_data(WATCHLIST_FILE, watchlist)
        elif c == 'e':
            s = input("Symbol to Edit: ").upper()
            if s in watchlist:
                old_t = watchlist[s].get('target', 0)
                old_r = watchlist[s].get('remark', '')
                print(f"Current Target: {old_t} | Remark: {old_r}")
                new_t_str = input(f"New Target (Enter to keep {old_t}): ")
                new_r = input(f"New Remark (Enter to keep '{old_r}'): ")
                
                final_t = float(new_t_str) if new_t_str.strip() else old_t
                final_r = new_r if new_r.strip() else old_r
                
                watchlist[s] = {'target': final_t, 'remark': final_r}
                save_data(WATCHLIST_FILE, watchlist)
                print("Updated.")
            else: print("Stock not in watchlist.")
        elif c == 'r':
            s = input("Symbol: ").upper()
            if s in watchlist: del watchlist[s]; save_data(WATCHLIST_FILE, watchlist)
        elif c == 'b': break

def project_wacc(portfolio):
    print(f"\n{Fore.YELLOW}=== PROJECT WACC ==={Style.RESET_ALL}")
    sym = input("Symbol: ").upper()
    if sym not in portfolio: print("Stock not found."); return

    curr = portfolio[sym]
    u_old = curr['units']
    cost_old = curr['total_cost']
    wacc_old = cost_old / u_old if u_old else 0

    print(f"Current: {u_old} units @ Rs. {wacc_old:.2f}")
    
    try:
        u_new = get_valid_input("Units to Buy: ", int)
        p_new = get_valid_input("Price per Unit: ", float)
        
        amt_new = u_new * p_new
        comm = get_broker_commission(amt_new)
        fees = comm + (amt_new * SEBON_FEE) + DP_CHARGE
        cost_new = amt_new + fees
        
        u_total = u_old + u_new
        cost_total = cost_old + cost_new
        wacc_new = cost_total / u_total
        
        # New Break Even
        est_rate = 0.0036 + SEBON_FEE
        be_new = (cost_total + DP_CHARGE) / (u_total * (1 - est_rate))

        print(f"\n{Fore.CYAN}>>> RESULT:{Style.RESET_ALL}")
        print(f"New Cost:    Rs. {cost_total:,.2f}")
        print(f"OLD WACC:    {Fore.RED}{wacc_old:.2f}{Style.RESET_ALL}")
        print(f"NEW WACC:    {Fore.GREEN}{wacc_new:.2f}{Style.RESET_ALL}")
        print(f"IMPROVED:    {Fore.GREEN}Rs. {wacc_old - wacc_new:.2f}{Style.RESET_ALL}")
        print(f"NEW BE:      Rs. {be_new:.2f}")
        input("\nPress Enter...")
    except: pass

def add_stock(portfolio):
    print(f"\n{Fore.YELLOW}--- ADD STOCK ---{Style.RESET_ALL}")
    sym = input("Symbol: ").upper().strip()
    if not sym: return
    units = get_valid_input("Units: ", int)
    price = get_valid_input("Price: ", float)
    
    is_exist = sym in portfolio
    sec = input(f"Sector ({portfolio[sym]['sector'] if is_exist else 'Hydro'}): ").capitalize()
    if is_exist and not sec: sec = portfolio[sym]['sector']
    sl = get_valid_input(f"Stop Loss ({portfolio[sym]['stop_loss'] if is_exist else 0}): ", float)
    note = input("Note: ")
    if is_exist and not note: note = portfolio[sym].get('note', '')

    cost = units * price
    comm = get_broker_commission(cost)
    fees = comm + (cost * SEBON_FEE) + DP_CHARGE
    total = cost + fees
    
    if is_exist:
        portfolio[sym]['units'] += units
        portfolio[sym]['total_cost'] += total
        portfolio[sym]['sector'] = sec
        portfolio[sym]['stop_loss'] = sl
        portfolio[sym]['note'] = note
        print("Averaged successfully.")
    else:
        portfolio[sym] = {
            'units': units, 'total_cost': total, 'sector': sec, 
            'stop_loss': sl, 'note': note,
            'cached_ltp': 0, 'cached_change': 0, 'last_updated': 'New'
        }
        print("Added successfully.")
    save_data(PORTFOLIO_FILE, portfolio)

def manage_portfolio(portfolio):
    print(f"\n{Fore.CYAN}--- MANAGE STOCK ---{Style.RESET_ALL}")
    sym = input("Symbol: ").upper()
    if sym not in portfolio: print("Not found"); return
    
    curr = portfolio[sym]
    print(f"1. Units: {curr['units']} | 2. Cost: {curr['total_cost']} | 3. Note: {curr.get('note')}")
    print("[1] Edit Note | [2] Fix Data | [3] Delete | [4] Cancel")
    opt = input(">> ")
    
    if opt == '1':
        portfolio[sym]['note'] = input("New Note: ")
        save_data(PORTFOLIO_FILE, portfolio)
    elif opt == '2':
        u = get_valid_input("Correct Units: ", int)
        w = get_valid_input("Correct WACC: ", float)
        portfolio[sym]['units'] = u
        portfolio[sym]['total_cost'] = u * w
        save_data(PORTFOLIO_FILE, portfolio)
    elif opt == '3':
        if input("Confirm Delete? (y/n): ") == 'y': 
            del portfolio[sym]; save_data(PORTFOLIO_FILE, portfolio)

def sell_stock(portfolio, history):
    print(f"\n{Fore.MAGENTA}--- SELL STOCK ---{Style.RESET_ALL}")
    sym = input("Symbol: ").upper()
    if sym not in portfolio: print("Not found"); return
    
    curr = portfolio[sym]
    u_avail = curr['units']
    print(f"Available: {u_avail}")
    u_sell = get_valid_input("Units to sell: ", int)
    if u_sell > u_avail: print("Not enough."); return
    
    price = get_valid_input("Sell Price: ", float)
    
    print("Holding Period: [1] Short Term (<1 yr)  [2] Long Term (>1 yr)")
    hp = input(">> ")
    is_long = True if hp == '2' else False
    tax_desc = "5%" if is_long else "7.5%"
    
    remark = input("Reason: ")
    
    cost_share = curr['total_cost'] / u_avail
    cost_sold = cost_share * u_sell
    metrics = calculate_metrics(u_sell, cost_sold, price, is_long_term=is_long)
    # Returns: [receivable, net_pl, pl_%, be, tax_amt]
    
    print("-" * 30)
    print(f"Gross Profit:  {metrics[0] - cost_sold:,.2f}")
    print(f"CGT Tax ({tax_desc}): {metrics[4]:,.2f}")
    print(f"Net Realized:  {Fore.GREEN if metrics[1]>0 else Fore.RED}{metrics[1]:,.2f}{Style.RESET_ALL}")
    print("-" * 30)
    
    if input("Confirm Sell? (y/n): ") == 'y':
        rec = {
            'date': datetime.now().strftime("%Y-%m-%d"),
            'symbol': sym, 'units': u_sell, 'sell_price': price,
            'invested': cost_sold, 'sold_val': metrics[0], 'net_pl': metrics[1],
            'tax_paid': metrics[4],
            'reason': remark
        }
        history.append(rec)
        save_data(HISTORY_FILE, history)
        
        rem = u_avail - u_sell
        if rem == 0: del portfolio[sym]
        else:
            portfolio[sym]['units'] = rem
            portfolio[sym]['total_cost'] -= cost_sold
        save_data(PORTFOLIO_FILE, portfolio)
        print("Sold.")

def view_history(history):
    clear_screen()
    table = []
    t_pl = 0
    t_tax = 0
    for h in history:
        pl = h.get('net_pl', 0)
        t_pl += pl
        t_tax += h.get('tax_paid', 0)
        c = Fore.GREEN if pl > 0 else Fore.RED
        table.append([h['date'], h['symbol'], h['units'], f"{c}{pl:,.0f}{Style.RESET_ALL}", h.get('reason','-')])
    print(tabulate(table, headers=["Date", "Sym", "Qty", "Net P/L", "Reason"], tablefmt="simple"))
    print(f"Total Net Profit: {t_pl:,.2f}")
    print(f"Total Tax Paid:   {t_tax:,.2f}")
    input("Enter...")

def view_allocation(portfolio):
    print(f"\n{Fore.MAGENTA}=== SECTOR ALLOCATION ==={Style.RESET_ALL}")
    if not portfolio: print("Empty."); return
    sectors = {}
    total = 0
    for s, d in portfolio.items():
        sec = d.get('sector', 'Other')
        val = d['total_cost']
        sectors[sec] = sectors.get(sec, 0) + val
        total += val
    
    table = []
    for sec, val in sectors.items():
        perc = (val / total * 100) if total > 0 else 0
        bar = '█' * int(perc/5)
        table.append([sec, f"{val:,.0f}", f"{perc:.1f}%", f"{Fore.CYAN}{bar}{Style.RESET_ALL}"])
    print(tabulate(table, headers=["Sector", "Invested", "%", "Visual"], tablefmt="fancy_grid"))
    input("Enter...")

def export_data(portfolio, history):
    try:
        fname = f"export_{datetime.now().strftime('%Y%m%d')}.csv"
        with open(fname, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Type", "Symbol", "Units", "Cost", "Note"])
            for s, d in portfolio.items():
                writer.writerow(["HOLDING", s, d['units'], d['total_cost'], d.get('note')])
            for h in history:
                writer.writerow(["SOLD", h['symbol'], h['units'], h['invested'], h.get('reason')])
        print(f"{Fore.GREEN}Exported to {fname}{Style.RESET_ALL}")
        input("Enter...")
    except: pass

# --- MAIN ---
def main():
    backup_data()
    port = load_data(PORTFOLIO_FILE, {})
    hist = load_data(HISTORY_FILE)
    watch = load_data(WATCHLIST_FILE, {})
    
    while True:
        clear_screen()
        print_banner()
        print(f"\n{Fore.WHITE}MENU:{Style.RESET_ALL}")
        print("[V]iew Portfolio  [P]roject WACC  [M]anage   [Se]ll")
        print("[W]atchlist       [H]istory       [S]ector   [A]dd")
        print("[D]iary           [E]xport        [C]lear    [Q]uit")
        
        c = input(">> ").lower().strip()
        
        if c == 'v': view_portfolio(port)
        elif c == 'p': project_wacc(port)
        elif c == 'm': manage_portfolio(port)
        elif c == 'se': sell_stock(port, hist)
        elif c == 'w': manage_watchlist(watch)
        elif c == 'h': view_history(hist)
        elif c == 's': view_allocation(port)
        elif c == 'a': add_stock(port)
        elif c == 'e': export_data(port, hist)
        elif c == 'c': clear_screen(); print_banner()
        elif c == 'd': daily_diary()
        elif c == 'q': break

if __name__ == "__main__":
    main()