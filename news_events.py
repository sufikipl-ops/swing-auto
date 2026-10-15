# News/events check for the latest screen candidates (read-only, public NSE endpoints + RSS headlines).
# Reads out/screen_latest.csv. Writes out/news_events.txt and out/news_events.csv. Never fails the workflow silently.
import os, sys, csv, json, time, datetime, re, traceback
import urllib.request, urllib.error, http.cookiejar
import xml.etree.ElementTree as ET

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')
FEEDS = [('ET Markets', 'https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms'),
         ('Business Standard', 'https://www.business-standard.com/rss/markets-106.rss')]
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def get(url, accept='application/json, text/plain, */*', referer='https://www.nseindia.com/'):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept, 'Referer': referer,
                                               'Accept-Language': 'en-US,en;q=0.9'})
    with opener.open(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='ignore')


def pdate(s):
    for f in ('%d-%b-%Y %H:%M:%S', '%d-%b-%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.datetime.strptime(str(s).strip()[:len(datetime.datetime.now().strftime(f)) + 3], f).date()
        except ValueError:
            continue
    m = re.match(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', str(s).strip())
    if m:
        return datetime.datetime.strptime(m.group(1), '%d-%b-%Y').date()
    return None


def main():
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    today = ist.date()
    lines = ['NEWS/EVENTS CHECK %s IST' % ist.strftime('%Y-%m-%d %H:%M')]
    os.makedirs('out', exist_ok=True)
    try:
        with open('out/screen_latest.csv', newline='', encoding='utf-8') as h:
            rows = list(csv.DictReader(h))
        syms = [r['SYMBOL'] for r in rows]
        lines.append('screen data date: %s | candidates: %d' % (rows[0]['DATE'] if rows else '-', len(syms)))
        # 1. NSE event calendar (board meetings / results)
        events = {}
        try:
            get('https://www.nseindia.com/', accept='text/html')
            time.sleep(1)
            raw = get('https://www.nseindia.com/api/event-calendar?index=equities')
            data = json.loads(raw)
            data = data if isinstance(data, list) else data.get('data', [])
            lines.append('NSE event calendar: OK, %d events' % len(data))
            if data:
                lines.append('event keys: %s' % ','.join(sorted(data[0].keys())))
            for e in data:
                s = (e.get('symbol') or '').strip()
                if s in syms:
                    events.setdefault(s, []).append(e)
        except Exception as ex:
            lines.append('NSE event calendar FAIL: %s' % str(ex)[:150])
                  # 2. NSE corporate announcements per symbol
        ann = {}
        ann_ok = 0
        for s in syms:
            try:
                raw = get('https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=%s' % s)
                d = json.loads(raw)
                d = d if isinstance(d, list) else d.get('data', [])
                ann[s] = d[:5]
                ann_ok += 1
            except Exception as ex:
                if ann_ok == 0 and len(ann) == 0 and s == syms[0]:
                    lines.append('NSE announcements FAIL: %s' % str(ex)[:150])
            time.sleep(0.8)
        lines.append('NSE announcements fetched for %d of %d symbols' % (ann_ok, len(syms)))
        # 3. RSS headlines
        heads = []
        for name, url in FEEDS:
            try:
                root = ET.fromstring(get(url, accept='application/rss+xml, text/xml', referer=url))
                items = root.findall('.//item')
                for it in items[:40]:
                    heads.append((name, (it.findtext('title') or '').strip(), (it.findtext('pubDate') or '').strip()))
                lines.append('RSS %s: OK, %d items' % (name, len(items)))
            except Exception as ex:
                lines.append('RSS %s FAIL: %s' % (name, str(ex)[:100]))
        # 4. combine
        out_rows = []
        for r in rows:
            s = r['SYMBOL']
            flag, nxt = [], ''
            for e in events.get(s, []):
                d = pdate(e.get('date') or e.get('bm_date') or '')
                purpose = (e.get('purpose') or e.get('bm_desc') or '')[:60]
                if d and today <= d <= today + datetime.timedelta(days=7):
                    nxt = '%s %s' % (d.isoformat(), purpose)
                    if re.search(r'result|financial', purpose, re.I) and d <= today + datetime.timedelta(days=2):
                        flag.append('RESULTS_SOON')
                    elif not flag:
                        flag.append('EVENT_7D')
            last = ''
            for a in ann.get(s, []):
                d = pdate(a.get('an_dt') or a.get('sort_date') or '')
                if d and (today - d).days <= 2:
                    last = '%s %s' % (d.isoformat(), (a.get('desc') or a.get('attchmntText') or '')[:80])
                    flag.append('NEW_ANNOUNCEMENT')
                    break
            hl = [h[1][:90] for h in heads if re.search(r'\b%s\b' % re.escape(s), h[1], re.I)][:2]
            if hl:
                flag.append('IN_NEWS')
            out_rows.append(dict(setup=r['SETUP'], symbol=s, flags=' '.join(flag) or 'none', next_event=nxt,
                                 last_announcement=last, headlines=' | '.join(hl)))
        with open('out/news_events.csv', 'w', newline='', encoding='utf-8') as h:
            w = csv.DictWriter(h, fieldnames=['setup', 'symbol', 'flags', 'next_event', 'last_announcement',
                                              'headlines'])
            w.writeheader(); w.writerows(out_rows)
        for x in out_rows:
            if x['flags'] != 'none':
                lines.append('%-12s %-10s %-34s | %s | %s | %s' % (x['symbol'], x['setup'], x['flags'], x['next_event'],
                                                                  x['last_announcement'], x['headlines']))
        lines.append('Symbols with no flags: %d. Top market headlines:' % sum(1 for x in out_rows if x['flags'] == 'none'))
        for hname, t, pdt in heads[:15]:
            lines.append('  [%s] %s' % (hname, t[:110]))
        lines.append('Note: flags come from public feeds and can be incomplete. Verify before acting. Not financial advice.')
    except Exception:
        lines.append('ERROR: ' + traceback.format_exc()[-500:])
    with open('out/news_events.txt', 'w') as h:
        h.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
