# Fundamentals (safety) check for screen + dip + locked stocks: promoter pledge, promoter holding trend, Debt/Equity.
# Sources: NSE public API (pledge + shareholding pattern), Yahoo Finance (debt/equity). Writes docs/funda.json.
# Read-only, no secrets. Har stock 7 din tak cache rehta hai (fundamentals roz nahi badalte), naye stock hi fetch hote hain.
# Never crashes: har source ka status json me rehta hai, taaki app "data nahi mila" dikha sake (chupchaap pass nahi).
import os, sys, json, re, time, datetime
import urllib.request, urllib.parse, http.cookiejar

from restrict import candidates   # screen + dip + locked list (same as restrict.py)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36')
OUT = 'docs/funda.json'
MAX_AGE = int(os.environ.get('FUNDA_MAX_AGE', '7'))     # din
LOG = []
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def log(s):
    print(s); LOG.append(s)


def get(url, accept='application/json, text/plain, */*', ref='https://www.nseindia.com/', tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Referer': ref,
                                                       'Accept-Language': 'en-US,en;q=0.9'})
            with op.open(req, timeout=30) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            last = e; time.sleep(2 + 2 * i)
    raise last


def num(x):
    try:
        return float(str(x).replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return None


def pdate(x):
    x = str(x or '').strip()
    for f in ('%d-%b-%Y', '%d-%B-%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y %H:%M:%S', '%d-%b-%Y %H:%M'):
        try:
            return datetime.datetime.strptime(x.title() if 'b' in f.lower() else x, f).date()
        except ValueError:
            pass
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', x)
    if m:
        try:
            return datetime.datetime.strptime('%s-%s-%s' % (m.group(1), m.group(2).title(), m.group(3)), '%d-%b-%Y').date()
        except ValueError:
            pass
    return None


def rows_of(d):
    """NSE kabhi list deta hai, kabhi {'data': [...]}."""
    if isinstance(d, list):
        return [r for r in d if isinstance(r, dict)]
    if isinstance(d, dict):
        for k in ('data', 'Data', 'rows'):
            if isinstance(d.get(k), list):
                return [r for r in d[k] if isinstance(r, dict)]
    return []


def key_like(rec, *pats):
    for p in pats:
        for k in rec:
            if re.search(p, str(k), re.I):
                return k
    return None


# ---------------- NSE: shareholding pattern (promoter %) ----------------
def shareholding(sym, dbg):
    d = json.loads(get('https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=%s'
                       % urllib.parse.quote(sym)))
    rows = rows_of(d)
    if not rows:
        return None
    if 'shp_keys' not in dbg:
        dbg['shp_keys'] = sorted(rows[0].keys())
    pk = key_like(rows[0], r'^pr_and_prgrp$', r'promoter', r'pr_and')
    dk = key_like(rows[0], r'^date$', r'asondate', r'quarter', r'date')
    if not pk or not dk:
        return None
    byq = {}
    for r in rows:
        dt, v = pdate(r.get(dk)), num(r.get(pk))
        if dt and v is not None and dt not in byq:     # pehla record = latest filing (revision ho to bhi)
            byq[dt] = v
    qs = sorted(byq, reverse=True)
    if not qs:
        return None
    out = {'prom': round(byq[qs[0]], 2), 'prom_date': qs[0].isoformat()}
    if len(qs) > 1:
        out['prom_prev'] = round(byq[qs[1]], 2)
    if len(qs) > 4:
        out['prom_yr'] = round(byq[qs[4]], 2)      # ~1 saal pehle
    return out


# ---------------- NSE: promoter pledge ----------------
def pledge(sym, dbg):
    d = json.loads(get('https://www.nseindia.com/api/corporate-pledgedata?index=equities&symbol=%s'
                       % urllib.parse.quote(sym)))
    rows = rows_of(d)
    if not rows:
        return {'pledge': None, 'pledge_note': 'NSE par pledge record nahi'}
    if 'pledge_keys' not in dbg:
        dbg['pledge_keys'] = sorted(rows[0].keys())
    dk = key_like(rows[0], r'^shp$', r'asondate', r'shpdate', r'disclosuredate', r'date')
    rows.sort(key=lambda r: pdate(r.get(dk)) or datetime.date(1900, 1, 1), reverse=True)
    r = rows[0]
    pk = key_like(r, r'^percPromoterShares$', r'perc.*promoter.*share', r'pledge.*promoter')
    v = num(r.get(pk)) if pk else None
    if v is None:          # khud hisaab: pledged / promoter holding
        a = num(r.get(key_like(r, r'^totPromoterShares$') or ''))
        b = num(r.get(key_like(r, r'^totPromoterHolding$') or ''))
        v = (a / b * 100) if a is not None and b else None
    dt = pdate(r.get(dk))
    return {'pledge': None if v is None else round(v, 2), 'pledge_date': dt.isoformat() if dt else ''}


# ---------------- Yahoo: debt / equity ----------------
YC = {'crumb': None, 'tried': False}


def yahoo_crumb(dbg):
    if YC['tried']:
        return YC['crumb']
    YC['tried'] = True
    for u in ('https://fc.yahoo.com', 'https://finance.yahoo.com/'):
        try:
            get(u, 'text/html,*/*', ref='https://finance.yahoo.com/', tries=1)
        except Exception:
            pass        # fc.yahoo.com 404 deta hai par cookie set ho jaati hai
    for u in ('https://query2.finance.yahoo.com/v1/test/getcrumb', 'https://query1.finance.yahoo.com/v1/test/getcrumb'):
        try:
            c = get(u, '*/*', ref='https://finance.yahoo.com/', tries=2).strip()
            if c and len(c) < 40 and '<' not in c:
                YC['crumb'] = c; dbg['yahoo_crumb'] = 'ok'; return c
        except Exception as e:
            dbg['yahoo_crumb'] = 'fail: %s' % str(e)[:80]
    return None


def debt_equity(sym, dbg):
    y = sym + '.NS'
    c = yahoo_crumb(dbg)
    if c:
        try:
            u = ('https://query2.finance.yahoo.com/v10/finance/quoteSummary/%s?modules=financialData,assetProfile,defaultKeyStatistics,summaryDetail&crumb=%s'
                 % (urllib.parse.quote(y), urllib.parse.quote(c)))
            res = json.loads(get(u, ref='https://finance.yahoo.com/', tries=2))['quoteSummary']['result'][0]
            fd, ap = res.get('financialData') or {}, res.get('assetProfile') or {}
            de = (fd.get('debtToEquity') or {}).get('raw')
            out = {'sector': ap.get('sector') or '', 'industry': ap.get('industry') or ''}
            # reel quality screen: PE, ROE, EPS, profit/sales growth (Yahoo: latest quarter YoY)
            ks, sd = res.get('defaultKeyStatistics') or {}, res.get('summaryDetail') or {}
            def rw(d, k, mul=1.0):
                v = (d.get(k) or {}).get('raw') if isinstance(d.get(k), dict) else None
                return round(v * mul, 2) if isinstance(v, (int, float)) else None
            for k, v in (('pe', rw(sd, 'trailingPE')), ('roe', rw(fd, 'returnOnEquity', 100)), ('eps', rw(ks, 'trailingEps')),
                         ('eg', rw(fd, 'earningsGrowth', 100)), ('rg', rw(fd, 'revenueGrowth', 100))):
                if v is not None:
                    out[k] = v
            if de is not None:
                out.update(de=round(de / 100.0, 2), de_src='yahoo')      # Yahoo % me deta hai (45 = 0.45)
                return out
        except Exception as e:
            dbg['yahoo_qs_err'] = str(e)[:100]
    # fallback: annual balance sheet timeseries (crumb nahi chahiye)
    now = int(time.time())
    u = ('https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/%s?type=annualTotalDebt,'
         'annualStockholdersEquity&period1=%d&period2=%d' % (urllib.parse.quote(y), now - 4 * 365 * 86400, now))
    res = json.loads(get(u, ref='https://finance.yahoo.com/', tries=2))['timeseries']['result']
    val = {}
    for r in res:
        t = (r.get('meta') or {}).get('type', [''])[0]
        pts = [p for p in (r.get(t) or []) if p and (p.get('reportedValue') or {}).get('raw') is not None]
        if pts:
            pts.sort(key=lambda p: p.get('asOfDate', ''))
            val[t] = (pts[-1]['reportedValue']['raw'], pts[-1].get('asOfDate', ''))
    if 'annualTotalDebt' in val and 'annualStockholdersEquity' in val and val['annualStockholdersEquity'][0] > 0:
        return {'de': round(val['annualTotalDebt'][0] / val['annualStockholdersEquity'][0], 2), 'de_src': 'yahoo-annual',
                'de_date': val['annualStockholdersEquity'][1]}
    return {}


def main():
    today = datetime.date.today()
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8')).get('items', {})
        except Exception as e:
            log('old funda.json read fail: %s' % e)
    cands = candidates()
    log('candidates: %d' % len(cands))
    try:
        get('https://www.nseindia.com/', 'text/html,*/*', tries=1)      # cookie warm-up
    except Exception as e:
        log('warmup fail: %s' % str(e)[:80])
    dbg, items, cnt = {}, {}, {'shp': [0, 0], 'pledge': [0, 0], 'de': [0, 0], 'cached': 0}
    for sym in cands:
        o = old.get(sym)
        try:
            age = (today - datetime.date.fromisoformat(o['at'])).days if o else 99
        except Exception:
            age = 99
        if o and age < MAX_AGE and not o.get('err') and o.get('qv') == 2:     # qv=2: reel quality fields bhi aa chuke hain
            items[sym] = o; cnt['cached'] += 1
            continue
        it, err = {'at': today.isoformat(), 'qv': 2}, []
        for name, fn in (('shp', shareholding), ('pledge', pledge), ('de', debt_equity)):
            cnt[name][1] += 1
            try:
                r = fn(sym, dbg)
                if r:
                    it.update(r)
                ok = {'shp': 'prom', 'pledge': 'pledge', 'de': 'de'}[name]
                if it.get(ok) is not None or (name == 'pledge' and r and r.get('pledge_note')):
                    cnt[name][0] += 1
                else:
                    err.append(name)
            except Exception as e:
                err.append(name)
                if name + '_err' not in dbg:
                    dbg[name + '_err'] = '%s: %s' % (sym, str(e)[:120])
            time.sleep(0.6)
        if err:
            it['err'] = err
        items[sym] = it
    # purane (candidate list se bahar) stock 30 din tak rakho, taaki Search me bhi dikhe
    for sym, o in old.items():
        if sym not in items:
            try:
                if (today - datetime.date.fromisoformat(o.get('at', '1900-01-01'))).days <= 30:
                    items[sym] = o
            except Exception:
                pass
    status = {k: ('%d/%d' % tuple(v)) for k, v in cnt.items() if k != 'cached'}
    status['cached'] = cnt['cached']
    log('status: %s' % json.dumps(status))
    os.makedirs('docs', exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as h:
        json.dump({'updated': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'), 'status': status,
                   'items': items, 'debug': dbg, 'log': LOG[-20:]}, h, indent=1, sort_keys=True)
    print('wrote %s (%d stocks)' % (OUT, len(items)))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('FATAL: %s' % e)
        sys.exit(1)
