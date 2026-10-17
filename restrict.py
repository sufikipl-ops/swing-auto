# Trading restrictions check: ASM / GSM list, circuit (price band), NSE series (BE/trade-for-trade).
# Candidates: docs/screen_latest.csv + docs/dip_latest.csv + locked (pinned) stocks.
# Writes docs/restrict.json. Never crashes the workflow: har source ka status json me rehta hai
# (ok / fail), taaki app "check nahi hua" dikha sake (chupchap pass nahi).
import os, sys, csv, json, re, time, datetime
import urllib.request, urllib.error, http.cookiejar

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36')
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
LOG = []


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


def candidates():
    out = []
    for p in ('docs/screen_latest.csv', 'docs/dip_latest.csv', 'out/screen_latest.csv', 'out/dip_latest.csv'):
        if os.path.exists(p):
            try:
                with open(p, newline='', encoding='utf-8') as h:
                    out += [r['SYMBOL'].strip().upper() for r in csv.DictReader(h) if r.get('SYMBOL')]
            except Exception as e:
                log('read %s fail: %s' % (p, e))
    try:
        import news_events
        out += news_events.pin_symbols()
    except Exception as e:
        log('pins fail: %s' % str(e)[:80])
    seen, res = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s); res.append(s)
    return res


def pick_col(hdr, *names):
    for i, h in enumerate(hdr):
        hh = re.sub(r'[^a-z]', '', h.lower())
        for n in names:
            if n in hh:
                return i
    return None


def parse_list_csv(txt):
    """ASM/GSM csv: symbol column + stage column (flexible)."""
    rows = list(csv.reader(txt.splitlines()))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return {}
    hi = 0
    for i, r in enumerate(rows[:6]):
        if pick_col(r, 'symbol') is not None:
            hi = i; break
    hdr = rows[hi]
    si = pick_col(hdr, 'symbol')
    gi = pick_col(hdr, 'stage', 'ltstage', 'gsm', 'asm', 'framework')
    if si is None:
        return {}
    out = {}
    for r in rows[hi + 1:]:
        if len(r) > si and r[si].strip():
            out[r[si].strip().upper()] = (r[gi].strip() if gi is not None and len(r) > gi else '')
    return out


def parse_json_list(txt):
    d = json.loads(txt)
    items = []

    def walk(x, sec=''):
        if isinstance(x, dict):
            if any(str(k).lower() in ('symbol', 'scripcode') for k in x):
                items.append((x, sec))
            for k, v in x.items():
                kl = str(k).lower()      # NSE reportASM: 'longterm' / 'shortterm' section -> LT / ST
                walk(v, 'LT' if 'long' in kl else 'ST' if 'short' in kl else sec)
        elif isinstance(x, list):
            for v in x:
                walk(v, sec)
    walk(d)
    out = {}
    for it, sec in items:
        sym = None
        for k, v in it.items():
            if str(k).lower() == 'symbol' and v:
                sym = str(v).strip().upper()
        if not sym:
            continue
        st = ''
        for k, v in it.items():
            if 'stage' in str(k).lower() or 'asmsurvind' in str(k).lower() or 'gsm' in str(k).lower():
                st = str(v); break
        out[sym] = ('%s %s' % (sec, st)).strip() if sec and not st.startswith(sec) else st
    return out


def fetch_list(name, csv_urls, api_urls):
    """ASM/GSM list laane ki koshish: pehle api, phir csv. Return (dict, status)."""
    for u in api_urls:
        try:
            d = parse_json_list(get(u))
            if d:
                return d, 'ok'
        except Exception as e:
            log('%s api %s fail: %s' % (name, u.split('/')[-1][:30], str(e)[:70]))
    for u in csv_urls:
        try:
            d = parse_list_csv(get(u, 'text/csv,*/*'))
            if d:
                return d, 'ok'
        except Exception as e:
            log('%s csv %s fail: %s' % (name, u.split('/')[-1][:30], str(e)[:70]))
    return {}, 'fail'


def quote_info(sym):
    """Ek stock ka price band + series + surveillance (NSE quote-equity)."""
    d = json.loads(get('https://www.nseindia.com/api/quote-equity?symbol=%s' % urllib.request.quote(sym)))
    pi = d.get('priceInfo') or {}
    si = d.get('securityInfo') or {}
    inf = d.get('info') or {}
    meta = d.get('metadata') or {}
    band = str(pi.get('pPriceBand') or '').strip()
    surv = si.get('surveillance') or {}
    surv_s = ''
    if isinstance(surv, dict):
        surv_s = ' '.join(str(surv.get(k) or '') for k in ('surv', 'desc')).strip()
    return dict(band=band, series=str(meta.get('series') or '').strip(), surv=surv_s,
                tft=str(si.get('tradingStatus') or '').strip(), suspended=bool(inf.get('isSuspended')),
                delisted=bool(inf.get('isDelisted')))


def main():
    cands = candidates()
    log('candidates: %d' % len(cands))
    try:
        get('https://www.nseindia.com/', 'text/html,*/*', tries=1)      # cookie warm-up
    except Exception as e:
        log('warmup fail: %s' % str(e)[:80])
    today = datetime.date.today()
    ds = today.strftime('%d%m%Y')
    asm, asm_st = fetch_list('ASM', [
        'https://nsearchives.nseindia.com/content/equities/ASM_list.csv',
        'https://nsearchives.nseindia.com/content/equities/asm_list.csv'],
        ['https://www.nseindia.com/api/reportASM'])
    gsm, gsm_st = fetch_list('GSM', [
        'https://nsearchives.nseindia.com/content/equities/GSM_list.csv',
        'https://nsearchives.nseindia.com/content/equities/gsm_list.csv'],
        ['https://www.nseindia.com/api/reportGSM'])
    log('ASM: %s (%d), GSM: %s (%d)' % (asm_st, len(asm), gsm_st, len(gsm)))
    # price band: NSE ki daily list (sec_list). Pehle aaj, phir pichle din.
    bandmap, band_st = {}, 'fail'
    for back in range(0, 6):
        d = today - datetime.timedelta(days=back)
        if d.weekday() >= 5:
            continue
        for u in ('https://nsearchives.nseindia.com/content/equities/sec_list_%s.csv' % d.strftime('%d%m%Y'),
                  'https://archives.nseindia.com/content/equities/sec_list_%s.csv' % d.strftime('%d%m%Y')):
            try:
                rows = list(csv.reader(get(u, 'text/csv,*/*', tries=1).splitlines()))
                rows = [r for r in rows if any(c.strip() for c in r)]
                hi = next((i for i, r in enumerate(rows[:8]) if pick_col(r, 'symbol') is not None and pick_col(r, 'band') is not None), None)
                if hi is None:
                    log('sec_list %s: band column nahi mila, header=%s' % (d, rows[0][:8] if rows else '-'))
                    continue
                si, bi = pick_col(rows[hi], 'symbol'), pick_col(rows[hi], 'band')
                se = pick_col(rows[hi], 'series')
                for r in rows[hi + 1:]:
                    if len(r) > max(si, bi) and r[si].strip() and (se is None or len(r) <= se or r[se].strip() in ('EQ', 'BE', 'BZ', 'SM', 'ST', '')):
                        bandmap[r[si].strip().upper()] = r[bi].strip()
                if bandmap:
                    band_st = 'ok'; log('sec_list %s ok (%d)' % (d, len(bandmap))); break
            except Exception as e:
                log('sec_list %s fail: %s' % (d, str(e)[:60]))
        if band_st == 'ok':
            break
    ok_q = bad_q = 0
    stocks = {}
    items = {}
    for s in cands:
        q = stocks.get(s, {})
        it = {}
        if s in asm:
            it['asm'] = asm[s] or 'ASM'
        if s in gsm:
            it['gsm'] = gsm[s] or 'GSM'
        if q.get('surv') and re.search(r'asm|gsm', q['surv'], re.I):
            it['surv'] = q['surv']
        if bandmap.get(s):
            it['band'] = bandmap[s]
        if q.get('series') and q['series'] not in ('EQ',):
            it['series'] = q['series']
        if q.get('suspended'):
            it['suspended'] = True
        if q.get('err'):
            it['err'] = 1
        if it:
            items[s] = it
    # ASM/GSM me jo bhi symbols mile (candidates ke bahar) unki list bhi rakho (search ke liye)
    out = dict(updated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
               status=dict(asm=asm_st, gsm=gsm_st, band=band_st),
               checked=cands, items=items, asm_all=sorted(asm)[:600], gsm_all=sorted(gsm)[:600], log=LOG[-12:])
    os.makedirs('docs', exist_ok=True)
    with open('docs/restrict.json', 'w', encoding='utf-8') as h:
        json.dump(out, h, ensure_ascii=False)
    log('docs/restrict.json written')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('restrict.py error:', e)
        os.makedirs('docs', exist_ok=True)
        with open('docs/restrict.json', 'w', encoding='utf-8') as h:
            json.dump(dict(updated=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
                           status=dict(asm='fail', gsm='fail', band='fail'), checked=[], items={}, log=[str(e)[:200]]), h)
