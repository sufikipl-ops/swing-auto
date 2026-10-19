# SAARE listed stocks ki khabar (sirf picks nahi): badi sites ki saari market khabar + Google News ki aam market searches
# + NSE ki saari companies ki announcements laao, har headline me company ka naam dhoondh ke stock se jodo.
# Har stock ke liye alag search (2600+) har 20 min me mumkin nahi (Google rok deta), isliye ye ulta tareeka.
# Pichhle 3 din ka itihas out/news_all_hist.json me; result docs/stock_news.json me (news_events.py ki stock-wise khabar ke saath).
# usage: python news_all.py   (news.yml me news_events.py ke baad)
import os, re, json, time, datetime, html, urllib.parse
import news_more

DAYS = 3
PER_SYM = 5
HIST = 'out/news_all_hist.json'
FEEDS = [('ET Markets', 'https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms'),
         ('ET Markets', 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms'),
         ('ET Results', 'https://economictimes.indiatimes.com/markets/stocks/earnings/rssfeeds/80262224.cms'),
         ('Business Standard', 'https://www.business-standard.com/rss/markets-106.rss'),
         ('Business Standard', 'https://www.business-standard.com/rss/companies-101.rss'),
         ('Moneycontrol', 'https://www.moneycontrol.com/rss/buzzingstocks.xml'),
         ('Moneycontrol', 'https://www.moneycontrol.com/rss/marketreports.xml'),
         ('Moneycontrol', 'https://www.moneycontrol.com/rss/results.xml'),
         ('Moneycontrol', 'https://www.moneycontrol.com/rss/latestnews.xml'),
         ('Mint', 'https://www.livemint.com/rss/markets'),
         ('Mint', 'https://www.livemint.com/rss/companies'),
         ('CNBC-TV18', 'https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml'),
         ('Financial Express', 'https://www.financialexpress.com/market/feed/'),
         ('BusinessLine', 'https://www.thehindubusinessline.com/markets/stock-markets/feeder/default.rss'),
         ('BusinessLine', 'https://www.thehindubusinessline.com/companies/feeder/default.rss')]
GQUERIES = ['shares surge', 'shares jump', 'shares rally', 'shares fall', 'shares slump', 'shares tumble', 'stock hits upper circuit',
            'stock lower circuit', 'Q2 results net profit', 'quarterly results shares', 'bags order shares', 'order win stock',
            'block deal shares', 'stocks to watch', 'stocks to buy target price', 'brokerage rating upgrade shares',
            'stake acquisition shares', 'dividend record date', 'bonus issue record date', 'stock split record date',
            'SME stock', 'smallcap stock news', 'midcap stock news', 'PSU stock news', 'NSE listed company',
            'board meeting fund raise shares', 'promoter stake sale', 'multibagger stock', 'share price today']
# aam English/finance shabd jo kisi stock ka symbol bhi hain: inhe sirf poore company naam se pakdo
STOP = set(('THE AND FOR NSE BSE FII DII IPO EPS PAT QOQ YOY GDP RBI SEBI ROE CMP SL BUY SELL NEW ALL NIFTY SENSEX FY PE PB '
            'EBITDA USD INR AUM NII NIM CAGR YTD EV PLI EPC SME MOU CEO CFO MD PSU OFS QIP NCD AGM CR BN RS ORDER WIN Q1 Q2 Q3 Q4 '
            'H1 H2 US UK UAE IT AI ACCURACY ADVANCE AFFORDABLE ALKALI ALPHA BETA CHEMICAL CLEAN CONS CONSUMER CREATIVE CREST '
            'CROWN DEEP DEFENCE DIVIDEND DOLLAR ELEVATE EMPOWER ENDURANCE ENERGY ETERNAL EXCEL FACT FOCUS FUSION GATEWAY GERMAN '
            'GLOBAL GLOBE GRAPHITE HEALTHCARE HEALTHY HEXAGON IDEA INCREDIBLE INFRA INTERNET LIQUID MAGNUM MARINE METAL MOMENTUM '
            'MONARCH NUCLEUS OIL OMNI PANORAMA PAR PREMIER PRESTIGE PRIORITY PRUDENT PYRAMID RACE RAIN RAINBOW RELIABLE RETAIL '
            'ROUTE SIGNATURE SILVER SPECTRUM STAR SUNSHINE SUPREME TAKE TECH TOTAL VALUE VITAL WEALTH WHEELS WORTH LANDMARK '
            'CAMPUS MARATHON CELEBRITY ZODIAC MEP ACE AVG IRIS INA DEN UFO CORONA SAFARI GOLD BANK POWER STEEL').split())
GENERIC1 = news_more.GENERIC | {'engineers', 'engineering', 'development', 'developers', 'logistics', 'technologies', 'technology',
                                'solutions', 'services', 'holdings', 'projects', 'motors', 'foods', 'hotels', 'healthcare',
                                'insurance', 'housing', 'realty', 'securities', 'ventures', 'cables', 'polymers', 'paper', 'sugar',
                                'cement', 'metals', 'minerals', 'investments', 'infrastructure', 'construction', 'petroleum',
                                'railways', 'electronics', 'software', 'media', 'airlines', 'shipping', 'fertilizers', 'gold',
                                'silver', 'auto', 'value', 'focus', 'total', 'star', 'prime', 'super', 'royal', 'modern', 'standard'}


SUFFIX = {'india', 'industries', 'corporation', 'company', 'enterprises', 'international', 'corp', 'co', 'and', 'of',
          'solutions', 'technologies', 'services', 'holdings', 'products', 'systems', 'global', 'group', 'ventures'}
JUNK = re.compile(r'price today & chart|live chart|stock price live|stock details|price movement today|share price live updates', re.I)


def norm(x):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', str(x or '').lower().replace('&', ' and '))).strip()


SHORT = {'sun pharma': 'SUNPHARMA', 'l and t': 'LT', 'larsen': 'LT', 'sbi': 'SBIN', 'sbi card': 'SBICARD', 'sbi cards': 'SBICARD', 'sbi life': 'SBILIFE', 'hdfc life': 'HDFCLIFE', 'state bank of india': 'SBIN', 'hul': 'HINDUNILVR',
         'ril': 'RELIANCE', 'm and m': 'M&M', 'mahindra and mahindra': 'M&M', 'bob': 'BANKBARODA', 'bank of baroda': 'BANKBARODA',
         'boi': 'BANKINDIA', 'pnb': 'PNB', 'bel': 'BEL', 'bharat electronics': 'BEL', 'hal': 'HAL', 'hindustan aeronautics': 'HAL',
         'infosys': 'INFY', 'tcs': 'TCS', 'hcl tech': 'HCLTECH', 'tech mahindra': 'TECHM', 'kotak bank': 'KOTAKBANK',
         'kotak mahindra bank': 'KOTAKBANK', 'bajaj finance': 'BAJFINANCE', 'bajaj finserv': 'BAJAJFINSV', 'maruti': 'MARUTI',
         'dr reddy s': 'DRREDDY', 'dr reddys': 'DRREDDY', 'ihcl': 'INDHOTEL', 'irctc': 'IRCTC', 'ongc': 'ONGC', 'ntpc': 'NTPC',
         'coal india': 'COALINDIA', 'itc': 'ITC', 'nalco': 'NATIONALUM', 'sail': 'SAIL', 'bhel': 'BHEL', 'ioc': 'IOC',
         'bpcl': 'BPCL', 'hpcl': 'HINDPETRO', 'tata steel': 'TATASTEEL', 'jsw steel': 'JSWSTEEL', 'adani ports': 'ADANIPORTS',
         'ultratech': 'ULTRACEMCO', 'asian paints': 'ASIANPAINT', 'eternal': 'ETERNAL', 'zomato': 'ETERNAL', 'paytm': 'PAYTM',
         'nykaa': 'NYKAA', 'policybazaar': 'POLICYBZR', 'ixigo': 'IXIGO', 'hdfc amc': 'HDFCAMC', 'icici pru amc': 'ICICIAMC'}


def aliases(names):
    """[(' naam ', SYM)]: poora naam (Ltd ke bina), pehle do shabd, aur ek-shabd naam agar khaas ho."""
    out = [(' %s ' % a, sy) for a, sy in SHORT.items() if sy in names]
    for sym, nm in names.items():
        full = re.sub(r'\b(limited|ltd|pvt|private|the|india limited)\b', ' ', norm(nm)); full = re.sub(r'\s+', ' ', full).strip()
        if not full:
            continue
        cand = {full}
        w = full.split()
        # pehle do shabd tabhi jab baaki naam sirf aam suffix ho (Sun Pharma Advanced Research != Sun Pharma)
        if len(w) >= 3 and len(' '.join(w[:2])) >= 7 and w[1] not in ('and', 'of') and (len(w) == 3 or all(x in SUFFIX for x in w[2:])):
            cand.add(' '.join(w[:2]))
        cut = re.sub(r'\s+(india|industries|corporation|company|enterprises|international|corp)$', '', full).strip()
        if cut:
            cand.add(cut)
        for a in cand:
            ws = a.split()
            if len(ws) == 1 and (len(a) < 5 or a in GENERIC1 or a.upper() in STOP):
                continue
            if len(ws) >= 2 and len(a) < 7:
                continue
            out.append((' %s ' % a, sym))
    return out


def match(title, al, syms):
    """Headline -> stocks. Lamba naam jeete (South Indian Bank me Indian Bank nahi); CAPITAL symbol bhi (aam shabd nahi)."""
    tx = ' %s ' % norm(title); hits = []
    for a, s in al:
        i = tx.find(a)
        if i >= 0:
            hits.append((i, i + len(a), s))
    hits.sort(key=lambda h: -(h[1] - h[0])); taken = []
    for h in hits:
        if not any(h[0] < t[1] - 1 and h[1] > t[0] + 1 for t in taken):
            taken.append(h)
    out = []
    for h in sorted(taken):
        if h[2] not in out:
            out.append(h[2])
    for m in re.finditer(r'\b[A-Z][A-Z0-9&\-]{2,19}\b', title):
        w = m.group(0)
        if re.match(r'\s+[A-Z][a-z]', title[m.end():]):      # 'DCM Shriram ...' = doosri company ka naam
            continue
        if w in syms and w not in STOP and w not in out:
            out.append(w)
    return out[:3]


def main():
    ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    names = news_more.load_names()
    try:
        syms = set(json.load(open('docs/stocks.json')).get('stocks', {})) | set(names)
    except Exception:
        syms = set(names)
    al = aliases({s: n for s, n in names.items() if s in syms})
    try:
        hist = json.load(open(HIST, encoding='utf-8'))
    except Exception:
        hist = {}
    items, ok, fail = [], 0, []
    for src, url in FEEDS:
        try:
            for it in news_more.rss_items(url, 100):
                items.append(dict(it, src=it.get('src') or src)); ok += 1
        except Exception as e:
            fail.append('%s %s' % (src, str(e)[:40]))
        time.sleep(0.3)
    for q in GQUERIES:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
            {'q': q + ' when:1d', 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'})
        try:
            for it in news_more.rss_items(url, 100):
                t = it['t']
                if it['src'] and t.endswith(' - ' + it['src']):
                    t = t[:-len(it['src']) - 3]
                items.append(dict(it, t=t)); ok += 1
        except Exception as e:
            fail.append('google %s %s' % (q, str(e)[:40]))
        time.sleep(0.6)
    cutoff = (ist - datetime.timedelta(days=DAYS)).strftime('%Y-%m-%d %H:%M')
    added = 0
    for it in items:
        w = news_more._when(it.get('date', ''))
        d = w.strftime('%Y-%m-%d %H:%M') if w else ist.strftime('%Y-%m-%d %H:%M')
        if d < cutoff:
            continue
        t = html.unescape(it['t']).strip()[:200]
        if JUNK.search(t):
            continue
        for s in match(t, al, syms):
            L = hist.setdefault(s, [])
            if any(norm(x['t']) == norm(t) for x in L):
                continue
            L.append(dict(t=t, src=(it.get('src') or '')[:40], date=d, link=it.get('link', '')[:400])); added += 1
    for s in list(hist):
        hist[s] = sorted([x for x in hist[s] if x['date'] >= cutoff], key=lambda x: x['date'], reverse=True)[:PER_SYM]
        if not hist[s]:
            del hist[s]
    os.makedirs('out', exist_ok=True)
    json.dump(hist, open(HIST, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    # stock-wise (news_events) + sabki khabar ek file me
    try:
        sn = json.load(open('docs/stock_news.json', encoding='utf-8'))
    except Exception:
        sn = {'items': {}}
    own = sn.get('items') or {}
    merged = {}
    for s in set(own) | set(hist):
        L = list(own.get(s) or [])
        for x in hist.get(s, []):
            if not any(norm(y['t']) == norm(x['t']) for y in L):
                L.append(x)
        merged[s] = sorted(L, key=lambda x: x.get('date') or '', reverse=True)[:PER_SYM]
    json.dump({'updated': ist.strftime('%Y-%m-%dT%H:%M:%S'), 'items': merged, 'all': len(hist)},
              open('docs/stock_news.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('news_all: %d headlines (%d sources fail: %s), %d naye jode, %d stocks ki khabar (kul file %d stocks, %d bytes)' % (
        ok, len(fail), '; '.join(fail[:6]), added, len(hist), len(merged), os.path.getsize('docs/stock_news.json')))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('news_all error:', str(e)[:200])
