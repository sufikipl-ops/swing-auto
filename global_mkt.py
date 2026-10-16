# Global market snapshot for Swing Desk: indices, commodities, FX, bond yield, main global players,
# headlines + rule-based "reason" + earnings (results) tags, and a simple global mood.
# Source: Yahoo Finance public chart endpoint + Yahoo Finance RSS headlines. Writes docs/global.json.
# Never crashes: har symbol ka fail alag record hota hai.
import os, sys, json, re, time, datetime
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
GROUPS = [
    ('US', [('^GSPC', 'S&P 500'), ('^IXIC', 'Nasdaq'), ('^DJI', 'Dow Jones'), ('^VIX', 'US VIX (dar ka meter)')]),
    ('Asia', [('^N225', 'Nikkei (Japan)'), ('^HSI', 'Hang Seng (HK)'), ('000001.SS', 'Shanghai (China)'), ('^KS11', 'Kospi (Korea)')]),
    ('Europe', [('^FTSE', 'FTSE (UK)'), ('^GDAXI', 'DAX (Germany)'), ('^FCHI', 'CAC (France)')]),
    ('India', [('^NSEI', 'Nifty 50'), ('^NSEBANK', 'Bank Nifty'), ('^BSESN', 'Sensex'), ('^INDIAVIX', 'India VIX')]),
    ('Commodity / FX / Bond', [('BZ=F', 'Brent crude'), ('CL=F', 'WTI crude'), ('GC=F', 'Gold'), ('INR=X', 'USD/INR'),
                               ('DX-Y.NYB', 'Dollar index'), ('^TNX', 'US 10Y yield')]),
]
PLAYERS = [('NVDA', 'Nvidia', 'AI/chips'), ('MSFT', 'Microsoft', 'Tech'), ('AAPL', 'Apple', 'Tech'), ('AMZN', 'Amazon', 'Tech/Retail'),
           ('GOOGL', 'Alphabet (Google)', 'Tech'), ('META', 'Meta', 'Tech'), ('TSLA', 'Tesla', 'Auto/EV'), ('TSM', 'TSMC', 'Chips'),
           ('JPM', 'JPMorgan', 'Banks'), ('XOM', 'Exxon', 'Oil'), ('INFY', 'Infosys ADR', 'India IT'), ('HDB', 'HDFC Bank ADR', 'India Bank'),
           ('IBN', 'ICICI Bank ADR', 'India Bank'), ('WIT', 'Wipro ADR', 'India IT')]
MARKET_FEEDS = ['^GSPC', '^IXIC', 'CL=F', '^TNX', 'GC=F']

DRIVERS = [
    (r'\bfed\b|powell|rate cut|rate hike|interest rate|fomc', 'Fed / interest rate ki baat'),
    (r'inflation|\bcpi\b|\bppi\b', 'Mehngai (inflation) data'),
    (r'jobs|payroll|unemployment|jobless', 'Jobs data'),
    (r'tariff|trade war|sanction|export ban|trade deal', 'Tariff / trade tension'),
    (r'\boil\b|crude|opec|brent', 'Crude oil'),
    (r'earnings|profit|revenue|guidance|quarter|results', 'Company results (earnings)'),
    (r'war|missile|iran|russia|ukraine|israel|gaza|geopolit|attack', 'Geopolitical tension'),
    (r'china|stimulus|beijing', 'China ki khabar'),
    (r'yield|treasury|bond', 'Bond yield'),
    (r'\bai\b|chip|nvidia|semiconductor', 'AI / chip stocks'),
    (r'bank|lender|credit', 'Banking / credit'),
    (r'recession|slowdown|gdp', 'Growth / recession dar'),
]
EARN = re.compile(r'earnings|quarter|q[1-4]\b|revenue|profit|guidance|beats|misses|results|eps\b|outlook|forecast', re.I)
BAD = re.compile(r'fraud|probe|investigat|lawsuit|sec charges|recall|downgrade|plunge|slump|miss|cuts? (forecast|outlook|guidance)|layoff|ban\b', re.I)
GOOD = re.compile(r'beat|record|surge|soar|jump|upgrade|raises? (forecast|outlook|guidance)|rally|approval|wins?\b|deal', re.I)
ERR = []


def http(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            last = e; time.sleep(1.5 + i)
    raise last


def quote(sym):
    u = 'https://query1.finance.yahoo.com/v8/finance/chart/%s?range=15d&interval=1d' % urllib.parse.quote(sym)
    try:
        d = json.loads(http(u))
    except Exception:
        d = json.loads(http(u.replace('query1', 'query2')))
    r = d['chart']['result'][0]
    m = r.get('meta') or {}
    ts = r.get('timestamp') or []
    cl = (r.get('indicators') or {}).get('quote', [{}])[0].get('close') or []
    pts = [(t, c) for t, c in zip(ts, cl) if c is not None]
    if len(pts) < 2:
        raise ValueError('data kam')
    off = m.get('gmtoffset') or 0
    mt = m.get('regularMarketTime') or pts[-1][0]
    day = lambda t: datetime.datetime.utcfromtimestamp(t + off).date()
    price = m.get('regularMarketPrice') or pts[-1][1]
    if day(pts[-1][0]) == day(mt) or True:
        prev = pts[-2][1]
    chg = (price / prev - 1) * 100 if prev else 0
    c5 = (price / pts[-6][1] - 1) * 100 if len(pts) >= 6 else None
    # bar series ka last date, taaki pata chale data kitna taza hai
    return dict(price=round(price, 4), prev=round(prev, 4), chg=round(chg, 2), chg5=None if c5 is None else round(c5, 2),
                asof=datetime.datetime.utcfromtimestamp(mt).strftime('%Y-%m-%d %H:%M UTC'), state=m.get('marketState', ''))


def feed(sym, limit=6):
    u = 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=US&lang=en-US' % urllib.parse.quote(sym)
    root = ET.fromstring(http(u, 2))
    out = []
    for it in root.iter('item'):
        t = (it.findtext('title') or '').strip()
        if t:
            out.append(dict(t=t[:200], l=(it.findtext('link') or '').strip(), d=(it.findtext('pubDate') or '')[:25]))
        if len(out) >= limit:
            break
    return out


def drivers_from(heads):
    sc = {}
    for h in heads:
        for pat, name in DRIVERS:
            if re.search(pat, h['t'], re.I):
                sc[name] = sc.get(name, 0) + 1
    return [k for k, v in sorted(sc.items(), key=lambda x: -x[1])][:3]


def reason_for(chg, heads):
    """Rule-based: sabse relevant headline + tag. AI nahi, andaza hai."""
    if not heads:
        return '', 'Koi taza headline nahi mili.', ''
    big = abs(chg) >= 2
    best = None
    for h in heads:
        sc = 0
        if EARN.search(h['t']):
            sc += 2
        if (chg < 0 and BAD.search(h['t'])) or (chg > 0 and GOOD.search(h['t'])):
            sc += 2
        if best is None or sc > best[0]:
            best = (sc, h)
    h = best[1]
    tag = 'RESULT' if EARN.search(h['t']) else ''
    why = ('Badi move ' if big else 'Move ') + ('ki sambhavit wajah (headline): ' if best[0] >= 2 else 'par taza headline (wajah pakki nahi): ')
    return tag, why + h['t'], h['l']


def mood(g):
    """Simple global mood. Backtest nahi hua, sirf savdhani ka alert."""
    q = {}
    for grp in g['groups']:
        for it in grp['items']:
            if 'chg' in it:
                q[it['sym']] = it
    ch = lambda s: q[s]['chg'] if s in q else None
    why, lvl = [], 0
    sp, nq, usv, inv, br = ch('^GSPC'), ch('^IXIC'), q.get('^VIX', {}).get('price'), q.get('^INDIAVIX', {}).get('price'), ch('BZ=F')
    asia = [ch(s) for s in ('^N225', '^HSI', '^KS11') if ch(s) is not None]
    am = sum(asia) / len(asia) if asia else None
    if sp is not None and sp <= -1.5 or nq is not None and nq <= -2 or (usv or 0) >= 30 or (inv or 0) >= 22:
        lvl = 2
    elif (sp is not None and sp <= -0.8) or (nq is not None and nq <= -1.2) or (usv or 0) >= 22 or (inv or 0) >= 18 or \
            (br is not None and br >= 3) or (am is not None and am <= -1.2):
        lvl = 1
    if sp is not None and sp <= -0.8: why.append('US (S&P 500) %.1f%% gira' % sp)
    if nq is not None and nq <= -1.2: why.append('Nasdaq %.1f%% gira' % nq)
    if (usv or 0) >= 22: why.append('US VIX %.0f (dar zyada)' % usv)
    if (inv or 0) >= 18: why.append('India VIX %.1f (uncertainty zyada)' % inv)
    if br is not None and br >= 3: why.append('Brent crude %.1f%% upar (India ke liye negative)' % br)
    if am is not None and am <= -1.2: why.append('Asia average %.1f%% neeche' % am)
    up = sp is not None and nq is not None and sp >= 0.5 and nq >= 0.5 and (usv or 0) < 20 and lvl == 0
    name = ['NORMAL', 'CAUTION', 'RISK_OFF'][lvl]
    if up:
        name = 'RISK_ON'; why.append('US market majboot (S&P %.1f%%, Nasdaq %.1f%%)' % (sp, nq))
    if not why:
        why.append('Koi bada global dar ka sanket nahi')
    return dict(level=name, why=why)


def main():
    g = dict(updated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'), groups=[], players=[], market_heads=[], drivers=[],
             status='ok', errors=[])
    nok = 0
    for gname, items in GROUPS:
        arr = []
        for sym, nm in items:
            it = dict(sym=sym, name=nm)
            try:
                it.update(quote(sym)); nok += 1
            except Exception as e:
                it['err'] = str(e)[:60]; ERR.append('%s: %s' % (sym, str(e)[:50]))
            arr.append(it); time.sleep(0.25)
        g['groups'].append(dict(name=gname, items=arr))
    for sym, nm, sec in PLAYERS:
        it = dict(sym=sym, name=nm, sector=sec)
        try:
            it.update(quote(sym)); nok += 1
        except Exception as e:
            it['err'] = str(e)[:60]; ERR.append('%s: %s' % (sym, str(e)[:50]))
        try:
            hd = feed(sym, 6)
            tag, why, link = reason_for(it.get('chg', 0), hd)
            it.update(tag=tag, why=why, link=link, heads=hd[:3])
        except Exception as e:
            it['why'] = 'Headline nahi mili.'; ERR.append('rss %s: %s' % (sym, str(e)[:40]))
        g['players'].append(it); time.sleep(0.25)
    allh = []
    for s in MARKET_FEEDS:
        try:
            allh += feed(s, 5)
        except Exception as e:
            ERR.append('rss %s: %s' % (s, str(e)[:40]))
    seen, uniq = set(), []
    for h in allh:
        if h['t'] not in seen:
            seen.add(h['t']); uniq.append(h)
    g['market_heads'] = uniq[:12]
    g['drivers'] = drivers_from(uniq)
    g['mood'] = mood(g)
    g['errors'] = ERR[:15]
    if nok == 0:
        g['status'] = 'fail'
    elif ERR:
        g['status'] = 'part'
    os.makedirs('docs', exist_ok=True)
    old = None
    if g['status'] == 'fail' and os.path.exists('docs/global.json'):
        print('sab fail: purani global.json rakhi'); return
    with open('docs/global.json', 'w', encoding='utf-8') as h:
        json.dump(g, h, ensure_ascii=False)
    print('global.json: status %s, ok %d, errors %d' % (g['status'], nok, len(ERR)))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('global_mkt error:', e)
