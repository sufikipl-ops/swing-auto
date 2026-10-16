# Company name list (SYMBOL -> Company name) for Swing Desk search + Telegram matching.
# Source: NSE public EQUITY_L.csv. Writes docs/names.json. Run via Actions > names > Run workflow (monthly auto).
import csv, io, json, os, sys, urllib.request, http.cookiejar, time
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
URLS = ['https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv',
        'https://archives.nseindia.com/content/equities/EQUITY_L.csv']
raw = None
for u in URLS:
    for attempt in range(3):
        try:
            req = urllib.request.Request(u, headers={'User-Agent': UA, 'Referer': 'https://www.nseindia.com/', 'Accept': 'text/csv,*/*'})
            raw = op.open(req, timeout=40).read().decode('utf-8', errors='ignore')
            if 'SYMBOL' in raw[:300].upper():
                break
            raw = None
        except Exception as ex:
            print('try', u, attempt, ex)
            time.sleep(2)
    if raw:
        break
if not raw:
    print('EQUITY_L.csv nahi mila'); sys.exit(1)
out = {}
for r in csv.DictReader(io.StringIO(raw)):
    r = {(k or '').strip().upper(): (v or '').strip() for k, v in r.items()}
    sym, name = r.get('SYMBOL'), r.get('NAME OF COMPANY')
    if sym and name and r.get('SERIES', 'EQ') in ('EQ', 'BE', 'BZ', 'SM', 'ST'):
        out[sym] = name
if len(out) < 500:
    print('bahut kam rows:', len(out)); sys.exit(1)
os.makedirs('docs', exist_ok=True)
json.dump(out, open('docs/names.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
print('names:', len(out))
