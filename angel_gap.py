# Morning gap-check (read-only): compares today's opening with the last screen's trigger levels.
# Reads out/screen_latest.csv, fetches today's 15-min candles from Angel One, writes out/gap_check.csv/.txt
import os, sys, csv, json, time, hmac, base64, struct, hashlib, datetime, traceback
import urllib.request, urllib.error

BASE = 'https://apiconnect.angelone.in'
MASTER = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json'
GAP_SKIP = 1.015


def totp(secret):
    s = secret.replace(' ', '').upper()
    s += '=' * (-len(s) % 8)
    k = base64.b32decode(s)
    c = struct.pack('>Q', int(time.time() // 30))
    h = hmac.new(k, c, hashlib.sha1).digest()
    o = h[-1] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)


def call(key, url, body, jwt=None):
    hd = {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-UserType': 'USER',
          'X-SourceID': 'WEB', 'X-ClientLocalIP': '127.0.0.1', 'X-ClientPublicIP': '127.0.0.1',
          'X-MACAddress': '00:00:00:00:00:00', 'X-PrivateKey': key}
    if jwt:
        hd['Authorization'] = 'Bearer ' + jwt
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hd, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'status': False, 'message': 'HTTP %s %s' % (e.code, e.read().decode()[:200])}
    except Exception as e:
        return {'status': False, 'message': 'ERR %s' % e}


def decide(row, candles):
    """row: dict from screen csv; candles: list of [ts, o, h, l, c, v] for today. Returns dict."""
    prev_close = float(row['CLOSE'])
    trig = round(float(row['DAY_HIGH']) * 1.001, 2)
    low5 = float(row['LOW5'])
    out = dict(setup=row['SETUP'], symbol=row['SYMBOL'], prev_close=prev_close, trigger=trig, stop_low5=low5,
               open='', gap_pct='', ltp='', vwap='', day_high='', status='NO_DATA', note='')
    if not candles:
        out['note'] = 'no candles yet'
        return out
    op = candles[0][1]
    hi = max(c[2] for c in candles)
    ltp = candles[-1][4]
    vol = sum(c[5] for c in candles)
    vwap = (sum((c[2] + c[3] + c[4]) / 3.0 * c[5] for c in candles) / vol) if vol else ltp
    gap = (op / prev_close - 1) * 100
    out.update(open=round(op, 2), gap_pct=round(gap, 2), ltp=round(ltp, 2), vwap=round(vwap, 2),
               day_high=round(hi, 2))
    notes = []
    if op > trig * GAP_SKIP:
        status = 'SKIP_GAPUP'
        notes.append('opened >1.5% above trigger')
    elif gap <= -1.5:
        status = 'SKIP_GAPDOWN'
        notes.append('gap down')
    elif ltp <= low5:
        status = 'SKIP_STOP_HIT'
        notes.append('price at/below stop')
    elif hi >= trig:
        status = 'TRIGGERED' if ltp <= trig * GAP_SKIP else 'RUNAWAY'
        if status == 'RUNAWAY':
            notes.append('LTP >1.5% above trigger')
    else:
        status = 'WAIT'
        notes.append('%.2f%% below trigger' % ((trig / ltp - 1) * 100))
    if ltp < vwap:
        notes.append('below VWAP')
    out['status'] = status
    out['note'] = '; '.join(notes)
    return out


def main():
    key = os.environ.get('ANGEL_API_KEY', '').strip()
    cid = os.environ.get('ANGEL_CLIENT_ID', '').strip()
    pin = os.environ.get('ANGEL_PIN', '').strip()
    tsec = os.environ.get('ANGEL_TOTP_SECRET', '').strip()
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    today = ist.strftime('%Y-%m-%d')
    lines = ['GAP CHECK %s IST (screen data date from screen_latest.csv)' % ist.strftime('%Y-%m-%d %H:%M')]
    os.makedirs('out', exist_ok=True)

    def finish(code):
        with open('out/gap_check.txt', 'w') as h:
            h.write('\n'.join(lines) + '\n')
        print('\n'.join(lines))
        sys.exit(code)

    try:
        if not (key and cid and pin and tsec):
            lines.append('FAIL: secrets missing'); finish(1)
        with open('out/screen_latest.csv', newline='', encoding='utf-8') as h:
            rows = list(csv.DictReader(h))
        if not rows:
            lines.append('screen_latest.csv is empty'); finish(1)
        lines.append('screen data date: %s | candidates: %d' % (rows[0]['DATE'], len(rows)))
        res = call(key, BASE + '/rest/auth/angelbroking/user/v1/loginByPassword',
                   {'clientcode': cid, 'password': pin, 'totp': totp(tsec)})
        if not res.get('status') or not res.get('data'):
            lines.append('LOGIN FAIL: %s' % res.get('message')); finish(1)
        jwt = res['data']['jwtToken']
        with urllib.request.urlopen(MASTER, timeout=120) as r:
            master = json.loads(r.read().decode())
        tok = {m['symbol']: m['token'] for m in master if m.get('exch_seg') == 'NSE' and m['symbol'].endswith('-EQ')}
        results = []
        for row in rows:
            t = tok.get(row['SYMBOL'] + '-EQ')
            if not t:
                results.append(dict(setup=row['SETUP'], symbol=row['SYMBOL'], status='NO_TOKEN', note='symbol not in master'))
                continue
            r = call(key, BASE + '/rest/secure/angelbroking/historical/v1/getCandleData',
                     {'exchange': 'NSE', 'symboltoken': t, 'interval': 'FIFTEEN_MINUTE',
                      'fromdate': today + ' 09:15', 'todate': today + ' 15:30'}, jwt)
            cs = [c for c in (r.get('data') or []) if str(c[0]).startswith(today)]
            d = decide(row, cs)
            if not r.get('status'):
                d['note'] = (d.get('note', '') + ' API: %s' % r.get('message'))[:120]
            results.append(d)
            time.sleep(1.1)
        cols = ['setup', 'symbol', 'status', 'prev_close', 'trigger', 'stop_low5', 'open', 'gap_pct', 'ltp', 'vwap',
                'day_high', 'note']
        order = {'TRIGGERED': 0, 'WAIT': 1, 'RUNAWAY': 2}
        results.sort(key=lambda x: (order.get(x['status'], 3), x['symbol']))
        with open('out/gap_check.csv', 'w', newline='', encoding='utf-8') as h:
            w = csv.DictWriter(h, fieldnames=cols, extrasaction='ignore')
            w.writeheader(); w.writerows(results)
        lines.append('%-10s %-14s %-13s %9s %9s %8s %7s %9s  %s' % (
            'setup', 'symbol', 'status', 'trigger', 'open', 'gap%', 'ltp', 'vwap', 'note'))
        for x in results:
            lines.append('%-10s %-14s %-13s %9s %9s %8s %7s %9s  %s' % (
                x['setup'], x['symbol'], x['status'], x.get('trigger', ''), x.get('open', ''), x.get('gap_pct', ''),
                x.get('ltp', ''), x.get('vwap', ''), x.get('note', '')))
        lines.append('Status guide: TRIGGERED = price crossed trigger and is within 1.5%; WAIT = not yet; '
                     'SKIP_* / RUNAWAY = do not enter. Not financial advice.')
        finish(0)
    except SystemExit:
        raise
    except Exception:
        lines.append('ERROR: ' + traceback.format_exc()[-600:])
        finish(1)


if __name__ == '__main__':
    main()
