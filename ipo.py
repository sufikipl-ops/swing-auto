# IPO tab ka data: open + aane wale IPO (mainboard + SME). Har IPO ka: price band, lot, dates, issue size, OFS/fresh,
# live subscription (QIB/NII/Retail, NSE), GMP (grey market, ANOFFICIAL, ipowatch), financials, KPI, peers, promoter
# holding, aur ek rule-based score (apply / soch ke / skip) jiske har point ka kaaran likha hota hai.
# Score abhi purane IPO par test nahi hua (subscription ka purana data seedha nahi milta): app me ye saaf likha hai.
# usage: python ipo.py  -> docs/ipo.json   (news.yml me har 20 min, market ke time)
import os, re, json, time, html, datetime, urllib.request, http.cookiejar

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
GMP_URL = 'https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/'
OUT = 'docs/ipo.json'
LOG = []


def log(s):
    print(s, flush=True); LOG.append(s)


def get(url, accept='text/html,application/xhtml+xml,*/*', referer=None):
    h = {'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.9'}
    if referer:
        h['Referer'] = referer
    with _op.open(urllib.request.Request(url, headers=h), timeout=30) as r:
        return r.read().decode('utf-8', errors='ignore')


def nse(path):
    return json.loads(get('https://www.nseindia.com/api/' + path, accept='application/json', referer='https://www.nseindia.com/market-data/all-upcoming-issues-ipo'))


def txt(c):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip()


def tables(s):
    out = []
    for t in re.findall(r'<table.*?</table>', s, re.S):
        rows = []
        for r in re.findall(r'<tr.*?</tr>', t, re.S):
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)
            rows.append([txt(c) for c in cells] + [re.findall(r'href="([^"]+)"', c) for c in cells[:1]])
        out.append(rows)
    return out


def num(x):
    """'₹(6.69)' -> -6.69 (bracket = minus), '₹1,234.5 Cr' -> 1234.5."""
    t = str(x or '').replace('₹', '')
    m = re.search(r'(\(?)\s*(-?[\d,]+(?:\.\d+)?)', t)
    if not m:
        return None
    try:
        v = float(m.group(2).replace(',', ''))
    except ValueError:
        return None
    return -abs(v) if m.group(1) else v


def nkey(name):
    n = re.sub(r'\b(limited|ltd|india|private|pvt|the|ipo|sme|open|closed|upcoming|allotted|listed)\b', ' ', name.lower())
    return re.sub(r'[^a-z0-9]+', ' ', n).split()


def gmp_rows():
    s = get(GMP_URL)
    out = []
    # IPO detail page ke link (menu me): https://ipowatch.in/<naam>-ipo/  -> naam ke shabd se milao
    det = sorted(set(re.findall(r'href="(https://ipowatch\.in/[a-z0-9\-]+-ipo/)"', s)))
    def find_det(name):
        w = set(nkey(name)); best, bs = None, 0
        for u in det:
            uw = set(u.rstrip('/').split('/')[-1].replace('-ipo', '').split('-')) - {'india', 'limited', 'ltd'}
            sc = len(w & uw)
            if sc > bs and sc >= min(2, len(w)):
                best, bs = u, sc
        return best
    for k, tb in enumerate(tables(s)[:2]):
        for r in tb[1:]:
            if len(r) < 7:
                continue
            name, gmp, trend, band, est, dates, links = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            st = 'OPEN' if re.search(r'\bopen\b', name, re.I) else 'UPCOMING' if re.search(r'upcoming', name, re.I) else 'CLOSED'
            clean = re.sub(r'\s*(open|closed|upcoming|allotted|listed)\s*$', '', name, flags=re.I).strip()
            pm = re.search(r'\(([-\d.]+)%\)', est)
            out.append(dict(name=clean, kind='SME' if k == 1 else 'MAIN', status=st, gmp=num(gmp), band=num(band),
                            gmp_pct=float(pm.group(1)) if pm else None, dates=dates, url=find_det(clean),
                            trend={'🟢': 'up', '🔴': 'down', '🟡': 'flat'}.get(trend.strip(), '')))
    return out


def detail_page(url):
    """ipowatch IPO page -> basic info, lot table, dates, promoter, financials, KPI, peers."""
    d = {}
    s = get(url)
    m = re.search(r'href="(https?://[^"]+\.pdf)"[^>]*>[^<]*(?:RHP|Red Herring)', s, re.I)
    if m:
        d['rhp'] = m.group(1)
    for tb in tables(s):
        if not tb:
            continue
        h = [c.lower() for c in tb[0][:-1]]
        rows = [r[:-1] for r in tb]
        if h and h[0].startswith('ipo open date') or any(r and r[0].lower().startswith('ipo price band') for r in rows):
            for r in rows:
                if len(r) >= 2:
                    d.setdefault('info', {})[r[0].rstrip(':')] = r[1]
        elif h[:2] == ['application', 'lot size']:
            d['lots'] = rows[1:]
        elif h and h[0].startswith('period ended'):
            d['fin_head'] = tb[0][:-1]; d['fin'] = rows[1:]
        elif h[:1] == ['kpi']:
            d['kpi'] = {r[0].rstrip(':'): r[1] for r in rows[1:] if len(r) >= 2}
        elif h and h[0] == 'company' and 'pe ratio' in ' '.join(h):
            d['peers'] = rows[1:]
        elif h and h[0] == 'particular' and any('post' in x for x in h):
            d['promoter'] = rows[1:]
        elif any(r and re.match(r'(basis of allotment|ipo listing date|refunds)', r[0], re.I) for r in rows):
            for r in rows:
                if len(r) >= 2:
                    d.setdefault('dates', {})[r[0].rstrip(':')] = r[1]
        elif h[:1] == ['investor category']:
            d['reserve'] = rows[1:]
    return d


def nse_sub(sym):
    """NSE live subscription: category -> times."""
    try:
        d = nse('ipo-active-category?symbol=%s' % sym)
        out = {}
        for r in d.get('dataList', [])[1:]:
            c, t = r.get('category', ''), r.get('noOfTotalMeant')
            if not t:
                continue
            k = 'QIB' if c.startswith('Qualified') else 'NII' if c == 'Non Institutional Investors' else 'RII' if c.startswith('Retail') \
                else 'EMP' if c.startswith('Employee') else 'TOTAL' if c.lower().startswith('total') else None
            if k:
                out[k] = round(float(t), 2)
        return out, d.get('updateTime', '')
    except Exception as e:
        return {}, 'err %s' % str(e)[:40]


def fin_summary(d):
    """Financial table se: aakhri 2 poore saal ka revenue/PAT growth."""
    f = d.get('fin') or []; hd = [x.lower() for x in d.get('fin_head', [])]
    if not f or not hd:
        return {}
    ci = {k: next((i for i, x in enumerate(hd) if x.startswith(k)), None) for k in ('revenue', 'pat', 'net worth', 'total borrowing', 'assets')}
    yrs = [r for r in f if re.fullmatch(r'(FY)?\s*\d{4}', r[0].strip(), re.I)]          # sirf poore saal (June/Sep wale chhote period nahi)
    if len(yrs) < 2 or ci['revenue'] is None or ci['pat'] is None:
        return {}
    a, b = yrs[-2], yrs[-1]
    ra, rb, pa, pb = num(a[ci['revenue']]), num(b[ci['revenue']]), num(a[ci['pat']]), num(b[ci['pat']])
    out = dict(year=b[0], rev=rb, pat=pb)
    if ra and rb is not None:
        out['rev_g'] = round((rb / ra - 1) * 100, 1)
    if pa and pb is not None and pa > 0:
        out['pat_g'] = round((pb / pa - 1) * 100, 1)
    if ci['total borrowing'] is not None and ci['net worth'] is not None:
        nw, bo = num(b[ci['net worth']]), num(b[ci['total borrowing']])
        if nw:
            out['de'] = round((bo or 0) / nw, 2)
    return out


def score(x, capital):
    """Do alag faisle. (1) LISTING: listing ke din fayda? (subscription + GMP). (2) LAMBA: company kaisi? (munafa, growth,
    ROE, valuation, OFS). Har point ka kaaran. Rule-based: purane IPO par abhi test nahi hua."""
    L, lw, F, fw = 0, [], 0, []
    sub = x.get('sub') or {}
    q, t = sub.get('QIB'), sub.get('TOTAL')
    if q is not None:
        if q >= 50: L += 2; lw.append('+ Bade institution (QIB) %sx bhar chuke: sabse mazboot sanket' % q)
        elif q >= 10: L += 1; lw.append('+ QIB %sx: achhi demand' % q)
        elif q < 1: L -= 1; lw.append('- QIB sirf %sx%s' % (q, ' (aakhri din aksar badhta hai, close tak dekho)' if x['status'] == 'OPEN' else ''))
        else: lw.append('= QIB %sx: theek-thaak' % q)
    if t is not None and t < 1 and x['status'] != 'UPCOMING':
        L -= 1; lw.append('- Poora issue bhi abhi %sx: demand kam' % t)
    g = x.get('gmp_pct')
    if g is not None:
        if g >= 25: L += 2; lw.append('+ GMP %+.0f%%: grey market bada listing gain dikha raha' % g)
        elif g >= 10: L += 1; lw.append('+ GMP %+.0f%%: thoda listing gain ka andaza' % g)
        elif g <= 3: L -= 2; lw.append('- GMP %+.0f%%: listing par fayda mushkil' % g)
        else: lw.append('= GMP %+.0f%%: kam' % g)
        if x.get('trend') == 'down': lw.append('= GMP gir raha hai')
    lv = 'APPLY' if L >= 3 else 'SOCH' if L >= 1 else 'SKIP'
    k = x.get('kpi') or {}; fs = x.get('fin') or {}
    eps = num(k.get('Earning Per Share (EPS)'))
    if (eps is not None and eps < 0) or (fs.get('pat') is not None and fs['pat'] < 0):
        F -= 2; fw.append('- Company ghate me hai (EPS/PAT minus)')
    else:
        if fs.get('pat_g') is not None:
            if fs['pat_g'] >= 20: F += 1; fw.append('+ Munafa %+.0f%% badha (%s)' % (fs['pat_g'], fs['year']))
            elif fs['pat_g'] < 0: F -= 1; fw.append('- Munafa %+.0f%% gira (%s)' % (fs['pat_g'], fs['year']))
        if fs.get('rev_g') is not None:
            if fs['rev_g'] >= 15: F += 1; fw.append('+ Bikri (revenue) %+.0f%% badhi' % fs['rev_g'])
            elif fs['rev_g'] < 0: F -= 1; fw.append('- Bikri %+.0f%% giri' % fs['rev_g'])
    roe = num(k.get('ROE')) if re.search(r'\d', str(k.get('ROE', ''))) else num(k.get('Return on Net Worth (RoNW)'))
    if roe is not None:
        if roe >= 15: F += 1; fw.append('+ ROE %.0f%%: paise par achha return' % roe)
        elif roe < 10: F -= 1; fw.append('- ROE %.0f%%: kamzor' % roe)
    pe, ppe = x.get('pe'), x.get('peer_pe')
    if pe and ppe:
        if pe > 1.3 * ppe: F -= 1; fw.append('- Mehenga: P/E %.0f vs milti-julti companies ~%.0f' % (pe, ppe))
        elif pe < 0.8 * ppe: F += 1; fw.append('+ Sasta: P/E %.0f vs milti-julti companies ~%.0f' % (pe, ppe))
        else: fw.append('= P/E %.0f, milti-julti companies ~%.0f ke aas-paas' % (pe, ppe))
    if x.get('ofs_only'): F -= 1; fw.append('- Poora OFS: company ko naya paisa nahi, purane maalik bech rahe')
    elif x.get('fresh'): fw.append('= Naya paisa (fresh issue): %s' % x['fresh'])
    fv = 'ACHHA' if F >= 3 else 'THEEK' if F >= 1 else 'KAMZOR'
    if x.get('min_amt') and x['min_amt'] > capital:
        lw.append('! Kam se kam ₹%s lagenge: aapke capital (₹%s) se zyada' % (format(int(x['min_amt']), ','), format(capital, ',')))
    return L, lv, lw, F, fv, fw


def main():
    ist = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)
    try:
        prev = json.load(open(OUT))
    except Exception:
        prev = {}
    try:
        rows = gmp_rows(); log('GMP rows %d' % len(rows))
    except Exception as e:
        log('GMP FAIL %s' % str(e)[:80]); rows = []
    nlist = []
    for path in ('ipo-current-issue', 'all-upcoming-issues?category=ipo'):
        try:
            for r in nse(path):
                if r.get('symbol') and r['symbol'] not in [x['symbol'] for x in nlist]:
                    nlist.append(r)
        except Exception as e:
            log('NSE %s FAIL %s' % (path, str(e)[:60]))
    log('NSE issues %d' % len(nlist))
    items, used = [], set()
    for g in rows:
        if g['status'] == 'CLOSED' and not g['url']:
            continue
        x = dict(g)
        gk = set(nkey(g['name']))
        for n in nlist:                                # NSE se jodo (naam ke shabd milao)
            nk = nkey(n.get('companyName', ''))
            if nk and gk and len(gk & set(nk)) >= min(2, len(gk), len(nk)) and n['symbol'] not in used:
                used.add(n['symbol']); x['symbol'] = n['symbol']; x['company'] = n.get('companyName')
                x['nse_status'] = n.get('status'); x['issue_dates'] = '%s - %s' % (n.get('issueStartDate', ''), n.get('issueEndDate', ''))
                break
        if x.get('url'):
            try:
                d = detail_page(x['url']); time.sleep(0.8)
                info = d.get('info', {})
                x['issue_size'] = info.get('Issue Size') or info.get('Total Issue Size')
                x['fresh'] = info.get('Fresh Issue') or info.get('Fresh Issue:')
                x['ofs'] = info.get('Offer for Sale') or info.get('Offer for Sale:')
                x['ofs_only'] = bool(x['ofs']) and not x['fresh']
                x['listing_at'] = info.get('IPO Listing')
                x['dates_all'] = d.get('dates', {})
                x['lots'] = d.get('lots')
                x['kpi'] = d.get('kpi')
                x['peers'] = d.get('peers')
                x['promoter'] = d.get('promoter')
                x['fin_table'] = [d.get('fin_head')] + (d.get('fin') or []) if d.get('fin') else None
                x['fin'] = fin_summary(d)
                x['rhp'] = d.get('rhp')
                if d.get('lots'):
                    for r in d['lots']:
                        if r and r[0].lower().startswith('retail minimum') and len(r) >= 4:
                            x['lot_shares'], x['min_amt'] = num(r[2]), num(r[3])
                        elif r and r[0].lower().startswith('minimum') and len(r) >= 4 and not x.get('min_amt'):
                            x['lot_shares'], x['min_amt'] = num(r[2]), num(r[3])
                eps = num((d.get('kpi') or {}).get('Earning Per Share (EPS)'))
                if eps and eps > 0 and x.get('band'):          # ghate wali company ka P/E nahi
                    x['pe'] = round(x['band'] / eps, 1)
                pes = sorted(v for v in (num(r[2]) for r in (d.get('peers') or []) if len(r) > 2) if v and 0 < v < 400)
                if pes:
                    x['peer_pe'] = pes[len(pes) // 2]
            except Exception as e:
                log('detail FAIL %s %s' % (x['name'], str(e)[:60]))
        if x.get('symbol') and x['status'] in ('OPEN', 'CLOSED'):
            x['sub'], x['sub_at'] = nse_sub(x['symbol']); time.sleep(0.6)
            if not x['sub']:                         # NSE ne na diya to pichhla rakho
                old = next((o for o in prev.get('items', []) if o.get('symbol') == x['symbol']), None)
                if old and old.get('sub'):
                    x['sub'], x['sub_at'] = old['sub'], old.get('sub_at', '') + ' (purana)'
        x['ls'], x['lv'], x['lw'], x['fs'], x['fv'], x['fw'] = score(x, 50000)
        items.append(x)
    order = {'OPEN': 0, 'UPCOMING': 1, 'CLOSED': 2}
    items.sort(key=lambda x: (order.get(x['status'], 3), x['kind'] != 'MAIN', -x['ls']))
    if not items and prev.get('items'):
        log('kuch nahi mila: pichhla data rakha'); return
    json.dump({'updated': ist.strftime('%Y-%m-%d %H:%M'), 'items': items, 'log': LOG[-10:]}, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    log('ipo.json: %d IPO (%d open)' % (len(items), sum(1 for x in items if x['status'] == 'OPEN')))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('ipo error:', str(e)[:200])
