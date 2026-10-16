# Live "IGNORE" alerts: jo stock suggest hua tha uski halat badal gayi to turant batao (Telegram).
# live.py har cycle me evaluate() bulata hai. Rules app (docs/index.html) ke same hain:
#   - Pick:  entry se 1.5% upar khula / gap-down <= -1.5% / stop-loss ke neeche / bahut upar nikal gaya
#   - Dip:   gap > +1.5% ya < -3% / stop (open - 2 ATR) ke neeche
#   - Sab:   ASM/GSM/series/suspended, bura news keyword, result/board meeting paas, circuit lag gaya
#   - Open trade (picks_review.csv): SL hit (live) / target touch (live)
import os, re, csv, json, time, datetime
import urllib.request

BADNEWS = re.compile(r'fraud|show[- ]cause|sebi (order|probe|notice)|penalt|default|insolven|nclt|auditor (resign|qualif)|'
                     r'resignation of (cfo|ceo|auditor|managing)|downgrad|rating (cut|withdraw)|forensic|search and seizure|'
                     r'enforcement directorate|\bcbi\b|suspension|delisting|invocation|warning letter|import alert|form 483|'
                     r'shutdown|fire at|lock-?out|strike|tax demand|raid', re.I)
# NSE ki category jiske naam me hi "suspension" likha hai (grant bhi isi me aata hai): sirf text dekho
NEUTRAL_CAT = re.compile(r'granting/withdrawal/surrender/cancellation/suspension', re.I)


def _get(url, timeout=25):
    req = urllib.request.Request(url + ('&' if '?' in url else '?') + 't=%d' % int(time.time()), headers={'User-Agent': 'swing-watch'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='ignore')


def _csv_text(txt):
    return list(csv.DictReader(txt.splitlines())) if txt else []


def _local(path):
    for base in ('docs', 'out'):
        p = os.path.join(base, path)
        if os.path.exists(p):
            return open(p, encoding='utf-8').read()
    return ''


def load_ctx(pages_base=''):
    """Files: pehle Pages (taaki din bhar ki taza news mile), fail ho to repo ki local copy."""
    ctx = {}
    for name in ('stocks.json', 'announcements.json', 'restrict.json'):
        txt = ''
        if pages_base:
            try:
                txt = _get(pages_base + name)
            except Exception:
                txt = ''
        txt = txt or _local(name)
        try:
            ctx[name] = json.loads(txt) if txt else {}
        except Exception:
            ctx[name] = {}
    for name in ('screen_latest.csv', 'dip_latest.csv', 'news_events.csv', 'picks_review.csv'):
        txt = ''
        if pages_base:
            try:
                txt = _get(pages_base + name)
            except Exception:
                txt = ''
        ctx[name] = _csv_text(txt or _local(name))
    return ctx


def num(x):
    try:
        return float(str(x).replace(',', ''))
    except Exception:
        return None


def evaluate(items, ctx, today_str):
    """items: live quotes {SYM: {ltp,o,h,l,pc,...}} (sirf aaj trade hue). Return [(key, sym, text)]."""
    out = []
    stocks = (ctx.get('stocks.json') or {}).get('stocks', {})
    ann = (ctx.get('announcements.json') or {}).get('items', {})
    rs = (ctx.get('restrict.json') or {}).get('items', {})
    news = {r.get('symbol', '').upper(): r for r in ctx.get('news_events.csv', [])}

    def add(sym, code, txt):
        out.append(('%s|%s|%s' % (today_str, sym, code), sym, txt))

    def common(sym, it):
        r = rs.get(sym) or {}
        if r.get('asm') or r.get('gsm') or r.get('surv'):
            add(sym, 'asm', 'ASM/GSM list me hai: trade mat lo')
        if r.get('series'):
            add(sym, 'series', 'NSE series %s (EQ nahi): trade mat lo' % r['series'])
        if r.get('suspended'):
            add(sym, 'susp', 'Trading suspended hai')
        for a in ann.get(sym, []):
            cat = '' if NEUTRAL_CAT.search(a.get('cat', '') or '') else a.get('cat', '')
            if BADNEWS.search('%s %s' % (cat, a.get('text', ''))):
                add(sym, 'news', 'Bura news ka shak: %s %s' % (a.get('cat', ''), (a.get('text', '') or '')[:80]))
                break
        n = news.get(sym)
        if n and 'RESULTS_SOON' in str(n.get('flags', '')):
            add(sym, 'result', 'Result/board meeting paas (%s): skip' % (n.get('next_event') or ''))
        try:
            band = float(r.get('band'))
        except Exception:
            band = None
        pc = it.get('pc')
        if band and pc and it.get('ltp'):
            if it['ltp'] >= pc * (1 + band / 100.0) * 0.995:
                add(sym, 'upc', 'Upper circuit (%g%%) lag gaya: entry nahi milegi, peecha mat karo' % band)
            elif it['ltp'] <= pc * (1 - band / 100.0) * 1.005:
                add(sym, 'lc', 'Lower circuit (%g%%): exit me phans sakta hai' % band)

    seen_pick = set()
    for r in ctx.get('screen_latest.csv', []):
        sym = (r.get('SYMBOL') or '').upper()
        it = items.get(sym)
        if not sym or not it or not it.get('ltp'):
            continue
        seen_pick.add(sym)
        hi, low5 = num(r.get('DAY_HIGH')), num(r.get('LOW5'))
        st = stocks.get(sym) or {}
        stop = st.get('stop') or low5
        if hi and stop:
            entry = hi * 1.001
            pc = it.get('pc') or num(r.get('CLOSE')) or it['ltp']
            o = it.get('o') or it['ltp']
            gap = (o / pc - 1) * 100 if pc else 0
            if o > entry * 1.015:
                add(sym, 'gapup', 'Entry (%.2f) se 1.5%% upar khula (%.2f): skip, peecha mat karo' % (entry, o))
            elif gap <= -1.5:
                add(sym, 'gapdn', 'Gap-down %.1f%%: skip' % gap)
            elif it['ltp'] <= stop:
                add(sym, 'sl', 'Price stop-loss (%.2f) ke neeche (%.2f): skip' % (stop, it['ltp']))
            elif (it.get('h') or 0) >= entry and it['ltp'] > entry * 1.015:
                add(sym, 'ran', 'Entry se bahut upar nikal gaya: peecha mat karo')
        common(sym, it)
    for r in ctx.get('dip_latest.csv', []):
        sym = (r.get('SYMBOL') or '').upper()
        it = items.get(sym)
        if not sym or not it or not it.get('ltp'):
            continue
        atr = num(r.get('ATR14'))
        pc = it.get('pc') or num(r.get('CLOSE')) or it['ltp']
        o = it.get('o') or it['ltp']
        gap = (o / pc - 1) * 100 if pc else 0
        if gap > 1.5:
            add(sym, 'dgapup', 'Dip: gap-up %.1f%% (limit +1.5%%): skip' % gap)
        elif gap < -3:
            add(sym, 'dgapdn', 'Dip: gap-down %.1f%% (limit -3%%): skip' % gap)
        elif atr and it['ltp'] <= o - 2 * atr:
            add(sym, 'dsl', 'Dip: price stop (%.2f) ke neeche: skip' % (o - 2 * atr))
        if sym not in seen_pick:
            common(sym, it)
    for r in ctx.get('picks_review.csv', []):
        sym = (r.get('symbol') or '').upper()
        it = items.get(sym)
        if (r.get('status') or '').strip() != 'OPEN' or not it:
            continue
        sl, tg = num(r.get('sl')), num(r.get('target'))
        if sl and ((it.get('l') or 1e18) <= sl or it['ltp'] <= sl):
            add(sym, 'tsl', 'Tumhara OPEN trade: SL (%.2f) hit hua lagta hai. Broker/GTT me exit confirm karo.' % sl)
        elif tg and (it.get('h') or 0) >= tg:
            add(sym, 'ttg', 'Tumhara OPEN trade: target (%.2f) touch hua. Broker me confirm karo.' % tg)
    return out
