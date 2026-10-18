# Live prices feed (read-only). GitHub Actions me chalta hai, har ~25 second me Angel One se
# aaj ke picks + locked stocks ka LTP/open/high/low/prev-close leke Google Sheet (Apps Script) me bhejta hai.
# Page (docs/index.html) wahin se padhta hai. Is script me koi password nahi; Angel secrets sirf GitHub Secrets me.
import os, sys, re, csv, json, time, hmac, base64, struct, hashlib, datetime, traceback
import urllib.request, urllib.error, urllib.parse

import live_scan

try:
    sys.stdout.reconfigure(line_buffering=True)   # GitHub log me lines turant dikhein
except Exception:
    pass

BASE = os.environ.get('ANGEL_BASE', 'https://apiconnect.angelone.in')
MASTER = os.environ.get('ANGEL_MASTER', 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json')
POLL = float(os.environ.get('LIVE_POLL', '25'))
MAX_RUN_MIN = float(os.environ.get('LIVE_MAX_MIN', '345'))   # GitHub job limit 6h se pehle band
END_IST = os.environ.get('LIVE_END_IST', '15:32')            # market band hone ke baad ruk jao
MAX_SYMS = 100
PAGES_BASE = os.environ.get('PAGES_BASE', '')
if not PAGES_BASE and os.environ.get('GITHUB_REPOSITORY'):
    _o, _r = os.environ['GITHUB_REPOSITORY'].split('/', 1)
    PAGES_BASE = 'https://%s.github.io/%s/' % (_o.lower(), _r)
ALERTS_ON = os.environ.get('WATCH_ALERTS', '1') != '0'
BREADTH_SEC = float(os.environ.get('LIVE_BREADTH_SEC', '300'))   # live market breadth har 5 min (~1100 stock, ~25 sec lagte hain)
PREP_FROM, PREP_SEND = '14:30', '15:12'                          # 3:15 taiyari list: app me 2:30 se, Telegram 3:12 ke baad ek baar
LIVE_MAX_CHARS = 44000                                           # Apps Script 'Live' cell 45000 se bada nahi leta


def ist_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=5, minutes=30)


def totp(secret):
    s = secret.replace(' ', '').upper()
    s += '=' * (-len(s) % 8)
    k = base64.b32decode(s)
    c = struct.pack('>Q', int(time.time() // 30))
    h = hmac.new(k, c, hashlib.sha1).digest()
    o = h[-1] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)


def http_json(url, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'status': False, 'message': 'HTTP %s %s' % (e.code, e.read().decode()[:200])}
    except Exception as e:
        return {'status': False, 'message': 'ERR %s' % e}


def angel(key, path, body, jwt=None):
    hd = {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-UserType': 'USER',
          'X-SourceID': 'WEB', 'X-ClientLocalIP': '127.0.0.1', 'X-ClientPublicIP': '127.0.0.1',
          'X-MACAddress': '00:00:00:00:00:00', 'X-PrivateKey': key}
    if jwt:
        hd['Authorization'] = 'Bearer ' + jwt
    return http_json(BASE + path, body, hd)


def login(key, cid, pin, tsec):
    res = angel(key, '/rest/auth/angelbroking/user/v1/loginByPassword',
                {'clientcode': cid, 'password': pin, 'totp': totp(tsec)})
    if not res.get('status') or not res.get('data'):
        raise RuntimeError('LOGIN FAIL: %s' % res.get('message'))
    return res['data']['jwtToken']


def page_config():
    """docs/index.html se API ka URL aur key padho (ek hi jagah badalna padta hai)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, 'docs', 'index.html'), os.path.join('docs', 'index.html')):
        if os.path.exists(p):
            t = open(p, encoding='utf-8').read()
            m = re.search(r"var PIN_URL='([^']*)',PIN_KEY='([^']*)'", t)
            if m:
                return m.group(1), m.group(2)
    return '', ''


def page_var(name):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, 'docs', 'index.html'), os.path.join('docs', 'index.html')):
        if os.path.exists(p):
            m = re.search(r"var %s='([^']*)'" % name, open(p, encoding='utf-8').read())
            if m:
                return m.group(1)
    return ''


def sheet_trade_symbols(gviz):
    """Picks sheet (Trades tab ke naye trade) ke pichhle 30 din ke symbols, taaki unka live P&L dikhe."""
    if not gviz:
        return []
    try:
        with urllib.request.urlopen(gviz + '&t=%d' % int(time.time()), timeout=30) as r:
            rows = list(csv.reader(r.read().decode('utf-8', 'ignore').splitlines()))
    except Exception:
        return []
    out = []
    for r in rows[1:][-40:]:
        if len(r) > 1:
            s_ = r[1].strip().upper()
            if re.match(r'^[A-Z0-9&\-]{2,20}$', s_) and s_ not in out:
                out.append(s_)
    return out


def load_base():
    """docs/live_base.json (dip_scan.py): Pages se taaza, warna repo ki copy."""
    d = http_json(PAGES_BASE + 'live_base.json?t=%d' % int(time.time())) if PAGES_BASE else {}
    if not isinstance(d, dict) or not d.get('syms'):
        try:
            d = json.load(open(os.path.join('docs', 'live_base.json')))
        except Exception:
            d = {}
    return d if d.get('syms') else {}


def hm(now):
    return now.strftime('%H:%M')


def prep_text(pr, bh, base_reg, now):
    reg = (bh or {}).get('regime') or base_reg or '?'
    L = ['3:15 TAIYARI (%s) - kal ke liye dhyan do' % hm(now),
         'Market abhi: %s%% stock EMA50 ke upar -> %s' % ((bh or {}).get('pct', '?'), reg)]
    if pr['dip']:
        L.append('Dip A banne wale (din yahin band hua to): ' + ', '.join('%s %+.1f%% (3 din)' % (r['s'], r['r3']) for r in pr['dip'][:8]))
    else:
        L.append('Dip A: abhi koi nahi')
    if pr['bounce']:
        L.append('Oversold bounce: ' + ', '.join('%s RSI %d' % (r['s'], r['rsi']) for r in pr['bounce'][:8]) +
                 ('' if reg == 'VWEAK' else ' (sirf BAHUT kamzor market me trade; abhi nahi)'))
    L.append('Pakka signal shaam ~6:20 ki scan se. Entry kal 9:20 par, gap rule ke saath.')
    return '\n'.join(L)


def screen_symbols():
    out = []
    for fn in ('screen_latest.csv', 'dip_latest.csv', 'picks_review.csv'):
        for d in ('out', 'docs'):
            p = os.path.join(d, fn)
            if os.path.exists(p):
                with open(p, newline='', encoding='utf-8') as h:
                    for r in csv.DictReader(h):
                        sy = (r.get('SYMBOL') or r.get('symbol') or '').strip().upper()
                        if not sy:
                            continue
                        if fn == 'picks_review.csv' and (r.get('status') or '').strip() not in ('OPEN', 'PENDING_TRIGGER'):
                            continue          # sirf khule/pending trades (SL/target live dekhne ke liye)
                        out.append(sy)
                break
    return out


def server_state(url, key):
    q = url + ('&' if '?' in url else '?') + urllib.parse.urlencode({'key': key, 'action': 'get', 't': int(time.time())})
    d = http_json(q)
    return d if d.get('ok') else None


def push_live(url, key, live):
    body = {'key': key, 'action': 'putlive', 'live': live}
    r = http_json(url, body, {'Content-Type': 'text/plain;charset=utf-8'})
    return bool(r.get('ok'))


def notify(url, key, text):
    r = http_json(url, {'key': key, 'action': 'notify', 'text': text[:3500]}, {'Content-Type': 'text/plain;charset=utf-8'})
    return bool(r.get('ok')), (r.get('error') or r.get('message') or '')


def parse_quotes(resp):
    """Angel quote response -> {SYMBOL: item}. Missing fields ko None rakhta hai."""
    out = {}
    fetched = ((resp or {}).get('data') or {}).get('fetched') or []
    for q in fetched:
        sym = str(q.get('tradingSymbol', '')).replace('-EQ', '').upper()
        if not sym:
            continue

        def num(k):
            try:
                v = q.get(k)
                return None if v in (None, '') else round(float(v), 2)
            except Exception:
                return None
        out[sym] = {'ltp': num('ltp'), 'o': num('open'), 'h': num('high'), 'l': num('low'), 'pc': num('close'),
                    'vwap': num('avgPrice'), 'vol': num('tradeVolume'), 't': str(q.get('exchTradeTime') or q.get('exchFeedTime') or '')}
    return out


def fetch_quotes(key, jwt, tokens):
    """tokens: {SYMBOL: token}. 50-50 ke batch me. Rate limit ke liye beech me thoda ruk ke."""
    items, err = {}, ''
    syms = list(tokens)
    for i in range(0, len(syms), 50):
        chunk = syms[i:i + 50]
        body = {'mode': 'FULL', 'exchangeTokens': {'NSE': [tokens[s] for s in chunk]}}
        r = angel(key, '/rest/secure/angelbroking/market/v1/quote/', body, jwt)
        got = parse_quotes(r) if r.get('status') else {}
        if not got:
            r2 = angel(key, '/rest/secure/angelbroking/market/v1/quote/', dict(body, mode='OHLC'), jwt)
            got = parse_quotes(r2) if r2.get('status') else {}
            if not got:
                err = (r.get('message') or r2.get('message') or 'quote empty')[:120]
        items.update(got)
        if i + 50 < len(syms):
            time.sleep(1.2)
    return items, err


def traded_today(item, today_ist):
    """Quote ka trade time aaj (IST) ka hai ya nahi. Format 'dd-Mon-YYYY HH:MM:SS' ya 'YYYY-MM-DD ...'."""
    t = str(item.get('t', ''))
    m = re.search(r'(\d{2}-[A-Za-z]{3}-\d{4})', t)
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), '%d-%b-%Y').date() == today_ist
        except Exception:
            return False
    m = re.search(r'(\d{4}-\d{2}-\d{2})', t)
    if m:
        return m.group(1) == today_ist.strftime('%Y-%m-%d')
    return False


def end_reached(now_ist):
    h, m = END_IST.split(':')
    return now_ist.hour * 60 + now_ist.minute >= int(h) * 60 + int(m)


def test_alert(url, pkey):
    """Market band ho tab bhi Telegram check: kal ke close pe 'flat open' maan ke asli rules chalao, ek TEST message bhejo."""
    import watch_alerts
    ctx = watch_alerts.load_ctx(PAGES_BASE)
    items = {}
    for r in ctx.get('screen_latest.csv', []) + ctx.get('dip_latest.csv', []):
        c = watch_alerts.num(r.get('CLOSE'))
        if r.get('SYMBOL') and c:
            items[r['SYMBOL'].upper()] = {'ltp': c, 'o': c, 'h': c, 'l': c, 'pc': c}
    alerts = watch_alerts.evaluate(items, ctx, ist_now().strftime('%Y-%m-%d'))
    lines = ['%s: %s' % (a[1], a[2]) for a in alerts[:12]] or ['(abhi koi IGNORE condition nahi mili)']
    text = 'TEST (market band, kal ke close pe) - IGNORE / DHYAN\n' + '\n'.join(lines)
    print(text)
    ok, why = notify(url, pkey, text)
    print('notify %s %s (%d alerts, %d stocks checked)' % ('ok' if ok else 'FAIL', why, len(alerts), len(items)))
    sys.exit(0 if ok else 1)


def main():
    key = os.environ.get('ANGEL_API_KEY', '').strip()
    cid = os.environ.get('ANGEL_CLIENT_ID', '').strip()
    pin = os.environ.get('ANGEL_PIN', '').strip()
    tsec = os.environ.get('ANGEL_TOTP_SECRET', '').strip()
    url, pkey = page_config()
    url = os.environ.get('PIN_URL', url)
    pkey = os.environ.get('PIN_KEY', pkey)
    if os.environ.get('TEST_ALERT') == '1':
        if not url.startswith(('https://', 'http://127.0.0.1')):
            print('FAIL: docs/index.html me PIN_URL set nahi hai'); sys.exit(1)
        test_alert(url, pkey)
    if not (key and cid and pin and tsec):
        print('FAIL: Angel secrets missing'); sys.exit(1)
    if not url.startswith(('https://', 'http://127.0.0.1')):
        print('FAIL: docs/index.html me PIN_URL set nahi hai'); sys.exit(1)
    started = time.time()
    jwt = login(key, cid, pin, tsec)
    print('login ok')
    master = http_json(MASTER, None, {}, timeout=180)
    if not isinstance(master, list):
        print('master download fail: %s' % str(master)[:150]); sys.exit(1)
    tokmap = {m['symbol'][:-3]: m['token'] for m in master if m.get('exch_seg') == 'NSE' and str(m.get('symbol', '')).endswith('-EQ')}
    print('tokens: %d' % len(tokmap))
    no_trade_since = None
    loops = 0
    base = load_base()
    print('live_base: %d stocks (%s)' % (len(base.get('syms') or {}), base.get('date')))
    gviz = page_var('PICKS_GVIZ'); tsyms, tsyms_ts = [], 0
    bh, bh_ts, bh_hist, pr, prep_sent, carry_day = None, 0, [], None, False, ''
    ctx, ctx_ts, sent_keys, alert_log, alert_day = {}, 0, set(), [], ''
    try:
        import watch_alerts
    except Exception as e:
        watch_alerts = None
        print('watch_alerts import fail: %s' % e)
    while True:
        now = ist_now()
        if end_reached(now) or (time.time() - started) / 60 > MAX_RUN_MIN:
            print('end of session, bye'); break
        if now.weekday() >= 5 and not os.environ.get('LIVE_ALLOW_WEEKEND'):
            print('weekend, bye'); break
        st = server_state(url, pkey)
        pins = (st or {}).get('pins') or []
        syms = []
        if time.time() - tsyms_ts > 600:
            tsyms, tsyms_ts = sheet_trade_symbols(gviz), time.time()
        for s in screen_symbols() + pins + tsyms:
            if s not in syms:
                syms.append(s)
        syms = syms[:MAX_SYMS]
        toks = {s: tokmap[s] for s in syms if s in tokmap}
        missing = [s for s in syms if s not in tokmap]
        items, err = fetch_quotes(key, jwt, toks)
        if not items and err:
            # token expire ho gaya ho to dobara login
            try:
                jwt = login(key, cid, pin, tsec)
                items, err = fetch_quotes(key, jwt, toks)
            except Exception as e:
                err = str(e)[:120]
        today = now.date()
        n_today = sum(1 for v in items.values() if traded_today(v, today))
        status = 'ok'
        if err:
            status = 'err'
        elif items and n_today == 0:
            status = 'closed'
            if now.hour * 60 + now.minute >= 9 * 60 + 40:
                no_trade_since = no_trade_since or time.time()
        else:
            no_trade_since = None
        # ---- IGNORE alerts (Telegram + app) ----
        alert_msg = ''
        if ALERTS_ON and watch_alerts and status == 'ok':
            try:
                dstr = today.strftime('%Y-%m-%d')
                if alert_day != dstr:
                    alert_day, sent_keys, alert_log = dstr, set(), []
                    prev = ((st or {}).get('live') or {})
                    if prev.get('date') == dstr:
                        alert_log = list(prev.get('alerts') or [])[-120:]
                        sent_keys = set(a.get('k') for a in alert_log)
                if time.time() - ctx_ts > 240 or not ctx:
                    ctx, ctx_ts = watch_alerts.load_ctx(PAGES_BASE), time.time()
                fresh = {k: v for k, v in items.items() if traded_today(v, today) and v.get('ltp')}
                new = [a for a in watch_alerts.evaluate(fresh, ctx, dstr) if a[0] not in sent_keys]
                if new:
                    lines = ['%s: %s' % (a[1], a[2]) for a in new[:12]]
                    ok, why = notify(url, pkey, 'IGNORE / DHYAN (%s)\n' % now.strftime('%H:%M') + '\n'.join(lines) + ('\n+%d aur, app dekho' % (len(new) - 12) if len(new) > 12 else ''))
                    alert_msg = 'notify %s %s (%d new)' % ('ok' if ok else 'FAIL', why, len(new))
                    for a in new:
                        sent_keys.add(a[0])
                        alert_log.append({'k': a[0], 's': a[1], 't': a[2][:140], 'at': now.strftime('%H:%M')})
                    alert_log = alert_log[-120:]
            except Exception as e:
                alert_msg = 'alerts err %s' % str(e)[:100]
        # ---- live market breadth + 3:15 taiyari ----
        dstr = today.strftime('%Y-%m-%d')
        if carry_day != dstr:                      # doosri GitHub job: subah ka breadth history aur 'bheja' flag wapas lo
            carry_day = dstr
            prev = ((st or {}).get('live') or {})
            if prev.get('date') == dstr:
                bh_hist = list((prev.get('breadth') or {}).get('hist') or [])
                prep_sent = bool((prev.get('prep') or {}).get('sent'))
                bh, pr = prev.get('breadth'), prev.get('prep')
        bmsg = ''
        if base and status == 'ok' and time.time() - bh_ts > BREADTH_SEC:
            bh_ts = time.time()
            try:
                btok = {s: tokmap[s] for s in base['syms'] if s in tokmap}
                bitems, berr = fetch_quotes(key, jwt, btok)
                bitems = {k: v for k, v in bitems.items() if traded_today(v, today) and v.get('ltp')}
                b = live_scan.breadth(bitems, base)
                if b:
                    if not bh_hist or bh_hist[-1][0] != hm(now):
                        bh_hist.append([hm(now), b['pct']])
                    bh = dict(b, at=hm(now), hist=bh_hist[-80:], base_date=base.get('date'), base_regime=base.get('regime'),
                              base_pct=base.get('breadth'))
                    bmsg = 'breadth %s%% %s (%d)' % (b['pct'], b['regime'], b['n'])
                    if hm(now) >= PREP_FROM:
                        pr = dict(live_scan.prep(bitems, base), at=hm(now), sent=prep_sent)
                        if not prep_sent and hm(now) >= PREP_SEND:
                            ok, why = notify(url, pkey, prep_text(pr, bh, base.get('regime'), now))
                            prep_sent = ok; pr['sent'] = ok
                            bmsg += ' | prep notify %s %s' % ('ok' if ok else 'FAIL', why)
                else:
                    bmsg = 'breadth: kam stock mile (%d) %s' % (len(bitems), berr)
            except Exception as e:
                bmsg = 'breadth err %s' % str(e)[:100]
        live = {'ts': now.strftime('%Y-%m-%dT%H:%M:%S'), 'date': dstr, 'status': status,
                'err': err, 'missing': missing, 'n': len(items), 'items': items, 'alerts': alert_log[-60:],
                'breadth': bh, 'prep': pr}
        while len(json.dumps(live)) > LIVE_MAX_CHARS and live['alerts']:
            live['alerts'] = live['alerts'][5:]
        okp = push_live(url, pkey, live)
        loops += 1
        print('%s loop %d symbols=%d fetched=%d today=%d status=%s pushed=%s %s' % (
            now.strftime('%H:%M:%S'), loops, len(syms), len(items), n_today, status, okp, err) + (' | ' + alert_msg if alert_msg else '')
            + (' | ' + bmsg if bmsg else ''))
        if no_trade_since and time.time() - no_trade_since > 600:
            print('aaj market me trade nahi dikha (holiday?), bye'); break
        time.sleep(POLL)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print('ERROR: ' + traceback.format_exc()[-800:]); sys.exit(1)
