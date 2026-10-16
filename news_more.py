# Extra news sources for news_events.py: Google News (stock-wise), BSE announcements, Moneycontrol + Mint RSS.
# Read-only, public endpoints, no secrets. Har function fail hone par khali list deta hai (workflow kabhi nahi tootta).
import os, re, json, time, datetime, html, email.utils
import urllib.request, urllib.parse, http.cookiejar
import xml.etree.ElementTree as ET

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')
MORE_FEEDS = [('Moneycontrol', 'https://www.moneycontrol.com/rss/buzzingstocks.xml'),
              ('Moneycontrol', 'https://www.moneycontrol.com/rss/marketreports.xml'),
              ('Mint', 'https://www.livemint.com/rss/markets')]
BSE_CODES = 'out/bse_codes.json'
GENERIC = {'india', 'indian', 'bharat', 'global', 'power', 'steel', 'energy', 'central', 'united', 'general', 'tata',
           'national', 'state', 'bank', 'finance', 'capital', 'trading', 'industries', 'enterprises', 'infra', 'textiles',
           'chemicals', 'pharma', 'tech', 'systems', 'limited', 'the', 'new', 'first', 'eastern', 'western', 'southern'}


_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_WARM = {}


def _get(url, referer='', accept='*/*', timeout=30):
    h = {'User-Agent': UA, 'Accept': accept, 'Accept-Language': 'en-US,en;q=0.9'}
    if referer:
        h['Referer'] = referer
        h['Origin'] = re.match(r'https://[^/]+', referer).group(0)
        h['Sec-Fetch-Site'] = 'same-site'; h['Sec-Fetch-Mode'] = 'cors'; h['Sec-Fetch-Dest'] = 'empty'
    with _op.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read().decode('utf-8', errors='ignore')


def _bse_warm():
    """BSE (Akamai) pehle homepage ki cookie maangta hai, warna api 403 deta hai."""
    if not _WARM.get('bse'):
        _WARM['bse'] = 1
        try:
            _get('https://www.bseindia.com/', accept='text/html,application/xhtml+xml,*/*')
            time.sleep(1)
        except Exception:
            pass


def load_names():
    for p in ('docs/names.json', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'names.json')):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return {}


def short_name(sym, names):
    """'Redington Limited' -> 'Redington'; 'Adani Ports and Special Economic Zone Limited' -> 'Adani Ports'."""
    n = re.sub(r'\b(limited|ltd\.?|\(india\)|india limited)\b', ' ', names.get(sym, ''), flags=re.I)
    w = [x for x in re.split(r'[\s.&,()-]+', n) if x]
    while w and w[0].lower() in ('the', 'm/s'):
        w = w[1:]
    j = []                         # 'R R Kabel' -> 'RR Kabel'
    for x in w:
        if len(x) == 1 and j and re.fullmatch(r'[A-Za-z]+', j[-1]) and len(j[-1]) <= 3 and j[-1].isupper():
            j[-1] += x
        else:
            j.append(x)
    w = j
    if not w:
        return ''
    return ' '.join(w[:2])        # do shabd: 'Adani' akela poore group ki khabar pakad leta


def name_pat(sym, names):
    """Headline me stock pakadne ka regex: symbol ya chhota company naam (word boundary ke saath)."""
    alts = ['(?-i:%s)' % re.escape(sym)]      # symbol sirf CAPITAL me (APOLLO != Apollo Hospitals)
    sn = short_name(sym, names)
    if sn and len(sn) >= 5 and sn.lower() not in GENERIC:
        alts.append(r'\s+'.join(re.escape(x) for x in sn.split()))
    return re.compile(r'\b(?:%s)\b' % '|'.join(alts), re.I)


def _when(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    except Exception:
        return None


def rss_items(url, limit=40):
    root = ET.fromstring(_get(url, accept='application/rss+xml, text/xml, */*'))
    out = []
    for it in root.findall('.//item')[:limit]:
        out.append(dict(t=html.unescape((it.findtext('title') or '').strip()), link=(it.findtext('link') or '').strip(),
                        date=(it.findtext('pubDate') or '').strip(),
                        src=((it.find('source').text if it.find('source') is not None else '') or '').strip()))
    return out


def google_news(sym, names, days=3, limit=4):
    """Google News RSS search: is stock ki pichhle `days` din ki khabar (sab sites: Moneycontrol, ET, Mint, CNBC...)."""
    sn = short_name(sym, names)
    q = '"%s"' % (sn if sn and len(sn) >= 5 else sym)
    q += ' share OR stock when:%dd' % days
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'})
    pat, out = name_pat(sym, names), []
    for it in rss_items(url, 20):
        t = it['t']
        src = it['src']
        if src and t.endswith(' - ' + src):
            t = t[:-len(src) - 3]
        if not pat.search(t):          # sirf woh headline jisme sach me ye company ho
            continue
        w = _when(it['date'])
        out.append(dict(t=t[:200], src=src[:40], date=w.strftime('%Y-%m-%d %H:%M') if w else '', link=it['link']))
        if len(out) >= limit:
            break
    return out


# ---------------- BSE ----------------
def bse_codes(lines):
    """NSE symbol -> BSE scrip code. BSE ki scrip list 7 din cache (out/bse_codes.json)."""
    try:
        d = json.load(open(BSE_CODES, encoding='utf-8'))
        if (datetime.date.today() - datetime.date.fromisoformat(d['at'])).days < 7 and d.get('codes'):
            return d['codes']
    except Exception:
        pass
    _bse_warm()
    raw = json.loads(_get('https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry='
                          '&segment=Equity&status=Active', referer='https://www.bseindia.com/',
                          accept='application/json, text/plain, */*', timeout=60))
    rows = raw if isinstance(raw, list) else raw.get('Table') or raw.get('data') or []
    codes = {}
    for r in rows:
        sid = str(r.get('scrip_id') or r.get('SCRIP_ID') or '').strip().upper()
        cd = str(r.get('SCRIP_CD') or r.get('scrip_cd') or '').strip()
        if sid and cd.isdigit():
            codes[sid] = cd
    if codes:
        os.makedirs('out', exist_ok=True)
        json.dump({'at': datetime.date.today().isoformat(), 'codes': codes}, open(BSE_CODES, 'w', encoding='utf-8'))
    lines.append('BSE scrip list: %d codes' % len(codes))
    return codes


def bse_ann(code, today, days=3):
    """BSE announcements, NSE wale format me (an_dt/desc/attchmntText/attchmntFile) taaki baaki code same chale."""
    u = ('https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=%s&strScrip=%s'
         '&strSearch=P&strToDate=%s&strType=C&subcategory=-1'
         % ((today - datetime.timedelta(days=days)).strftime('%Y%m%d'), code, today.strftime('%Y%m%d')))
    _bse_warm()
    d = json.loads(_get(u, referer='https://www.bseindia.com/', accept='application/json, text/plain, */*'))
    out = []
    for r in (d.get('Table') or []):
        try:
            dt = datetime.datetime.fromisoformat(str(r.get('NEWS_DT') or r.get('DT_TM') or '')[:19])
        except ValueError:
            continue
        sub = str(r.get('NEWSSUB') or '')
        cat = (r.get('SUBCATNAME') or r.get('CATEGORYNAME') or sub.split(' - ')[-1] or 'Announcement').strip()
        att = str(r.get('ATTACHMENTNAME') or '').strip()
        out.append({'an_dt': dt.strftime('%d-%b-%Y %H:%M:%S'), 'desc': cat,
                    'attchmntText': (r.get('HEADLINE') or sub or '').strip(),
                    'attchmntFile': ('https://www.bseindia.com/xml-data/corpfiling/AttachLive/' + att) if att else '',
                    'src': 'BSE'})
    return out


def _words(s):
    return set(w for w in re.findall(r'[a-z0-9]{4,}', (s or '').lower()) if w not in GENERIC)


def merge_bse(nse_list, bse_list):
    """Jo announcement NSE par pehle se hai (same din, milte-julte shabd) use BSE se dobara mat jodo."""
    out = list(nse_list)
    for b in bse_list:
        bw, bd = _words(b['desc'] + ' ' + b['attchmntText']), b['an_dt'][:11]
        dup = False
        for a in nse_list:
            if str(a.get('an_dt') or a.get('sort_date') or '')[:11].lower() != bd.lower():
                continue
            aw = _words('%s %s' % (a.get('desc'), a.get('attchmntText')))
            if bw and len(bw & aw) >= 0.5 * len(bw):
                dup = True; break
        if not dup:
            out.append(b)

    def key(a):
        try:
            return datetime.datetime.strptime(str(a.get('an_dt') or '')[:20].strip(), '%d-%b-%Y %H:%M:%S')
        except ValueError:
            return datetime.datetime(1900, 1, 1)
    out.sort(key=key, reverse=True)
    return out
