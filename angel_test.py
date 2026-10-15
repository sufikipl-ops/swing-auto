# Angel One SmartAPI connection test (read-only). Writes out/angel_test.txt, never prints secrets.
import os, sys, json, time, hmac, base64, struct, hashlib, datetime
import urllib.request, urllib.error

KEY = os.environ.get('ANGEL_API_KEY', '').strip()
CID = os.environ.get('ANGEL_CLIENT_ID', '').strip()
PIN = os.environ.get('ANGEL_PIN', '').strip()
TSEC = os.environ.get('ANGEL_TOTP_SECRET', '').replace(' ', '').strip()
lines = ['ANGEL TEST %s' % datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')]
lines.append('secrets present: key=%s client=%s pin=%s totp=%s' % (bool(KEY), bool(CID), bool(PIN), bool(TSEC)))


def finish(code):
    os.makedirs('out', exist_ok=True)
    with open('out/angel_test.txt', 'w') as h:
        h.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    sys.exit(code)


def totp(secret):
    s = secret.upper()
    s += '=' * (-len(s) % 8)
    k = base64.b32decode(s)
    c = struct.pack('>Q', int(time.time() // 30))
    h = hmac.new(k, c, hashlib.sha1).digest()
    o = h[-1] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)


def call(url, body, jwt=None):
    hd = {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-UserType': 'USER',
          'X-SourceID': 'WEB', 'X-ClientLocalIP': '127.0.0.1', 'X-ClientPublicIP': '127.0.0.1',
          'X-MACAddress': '00:00:00:00:00:00', 'X-PrivateKey': KEY}
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


if not (KEY and CID and PIN and TSEC):
    lines.append('FAIL: one or more secrets missing')
    finish(1)
base = 'https://apiconnect.angelone.in'
res = call(base + '/rest/auth/angelbroking/user/v1/loginByPassword',
           {'clientcode': CID, 'password': PIN, 'totp': totp(TSEC)})
if not res.get('status') or not res.get('data'):
    lines.append('LOGIN FAIL: %s (code %s)' % (res.get('message'), res.get('errorcode')))
    finish(1)
jwt = res['data']['jwtToken']
lines.append('LOGIN OK')
today = datetime.date.today()
frm = (today - datetime.timedelta(days=4)).strftime('%Y-%m-%d') + ' 09:15'
to = today.strftime('%Y-%m-%d') + ' 15:30'
bad = 0
for name, tok in (('RELIANCE', '2885'), ('TCS', '11536'), ('INFY', '1594')):
    r = call(base + '/rest/secure/angelbroking/historical/v1/getCandleData',
             {'exchange': 'NSE', 'symboltoken': tok, 'interval': 'FIFTEEN_MINUTE', 'fromdate': frm, 'todate': to}, jwt)
    d = r.get('data') or []
    if r.get('status') and d:
        lines.append('%s: %d candles, last = %s' % (name, len(d), d[-1]))
    else:
        bad += 1
        lines.append('%s FAIL: %s (code %s)' % (name, r.get('message'), r.get('errorcode')))
    time.sleep(1.2)
lines.append('RESULT: %s' % ('ALL OK' if bad == 0 else '%d failed' % bad))
finish(0 if bad == 0 else 1)
