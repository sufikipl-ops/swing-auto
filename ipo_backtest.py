# IPO score ka asli test: purane IPO (ipowatch: aakhri din ka subscription, aakhri GMP, company data) + NSE bhavcopy
# (listing din ka open/close, 20/60 din baad) -> kya ipo.py ka "Listing" aur "Company" faisla sach me kaam karta hai?
# Pages ek baar laate hain, out/ipo_hist.json me cache (agli baar sirf naye). Listing ka bhav NSE se (ipowatch se nahi).
# usage: python ipo_backtest.py <bhav_folder>   -> out/ipo_backtest_summary.txt, out/ipo_backtest.csv, docs/ipo_backtest.json
import os, re, sys, csv, json, glob, time, datetime, collections, statistics
import ipo

CACHE = 'out/ipo_hist.json'
MAX_FETCH = int(os.environ.get('IPO_MAX_FETCH', '2500'))
LINES = []


def log(s=''):
    print(s, flush=True); LINES.append(s)


def pdate(s):
    s = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', str(s or '').strip().rstrip(','))
    for f in ('%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d-%b-%Y', '%d-%B-%Y', '%B %d %Y'):
        try:
            return datetime.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def kv(tabs):
    out = {}
    for tb in tabs:
        for r in tb:
            r = r[:-1]
            if len(r) == 2 and r[0]:
                out.setdefault(r[0].rstrip(':').strip(), r[1])
    return out


def sub_page(url):
    """Aakhri din ka subscription: QIB/NII/RII/Total (aakhri column)."""
    out = {}
    for tb in ipo.tables(ipo.get(url)):
        if not tb or len(tb[0]) < 3:
            continue
        h = [c.lower() for c in tb[0][:-1]]
        if not (h and h[0].startswith('categor') and any(x.startswith('day') for x in h)):
            continue
        for r in tb[1:]:
            r = r[:-1]
            vals = [ipo.num(x) for x in r[1:] if ipo.num(x) is not None]
            if not vals:
                continue
            k = r[0].strip().upper()
            k = 'QIB' if k.startswith('QIB') else 'NII' if k in ('NII', 'HNI') else 'RII' if k.startswith('RII') or k.startswith('RETAIL') \
                else 'TOTAL' if k.startswith('TOTAL') else None
            if k and k not in out:
                out[k] = vals[-1]
        if out:
            break
    return out


def gmp_page(url):
    s = ipo.get(url); tabs = ipo.tables(s); g = None
    for tb in tabs:
        if tb and tb[0] and tb[0][0].lower() == 'date' and len(tb[0]) >= 3 and 'gmp' in tb[0][1].lower():
            for r in tb[1:]:
                v = ipo.num(r[1])
                if v is not None:
                    g = v; break           # sabse upar = aakhri GMP (listing se pehle)
            break
    info = kv(tabs)
    band = info.get('IPO Price Band') or info.get('IPO Price Band:') or info.get('Price Band') or ''
    nums = [ipo.num(x) for x in re.findall(r'[\d,]+(?:\.\d+)?', band.replace('₹', ''))]
    nums = [x for x in nums if x]
    return dict(gmp=g, upper=max(nums) if nums else None,
                open=str(pdate(info.get('IPO Open Date') or info.get('IPO Open'))),
                close=str(pdate(info.get('IPO Close Date') or info.get('IPO Close'))),
                listing=str(pdate(info.get('IPO Listing Date'))), size=info.get('Issue Size') or info.get('IPO Size'),
                fresh=info.get('Fresh Issue'), ofs=info.get('Offer for Sale'))


def collect():
    try:
        cache = json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        cache = {}
    urls = []
    for i in [''] + [str(k) for k in range(2, 20)]:
        try:
            x = ipo.get('https://ipowatch.in/post-sitemap%s.xml' % i)
        except Exception:
            break
        u = re.findall(r'<loc>([^<]+)</loc>', x)
        if not u:
            break
        urls += u
    us = set(urls)
    bases = sorted(set(u[:-len('-subscription-status/')] for u in urls if u.endswith('-ipo-subscription-status/')))
    log('sitemap: %d url, %d IPO (subscription page wale), cache %d' % (len(urls), len(bases), len(cache)))
    n = 0
    for b in bases:
        slug = b.rstrip('/').split('/')[-1]
        if slug in cache:
            continue
        if n >= MAX_FETCH:
            break
        gu = next((u for u in (b + '-gmp-grey-market-premium/', b + '-gmp-today/', b + '-gmp/') if u in us), None)
        if not gu:
            cache[slug] = {'skip': 'no gmp page'}; continue
        rec = {}
        try:
            rec['sub'] = sub_page(b + '-subscription-status/'); time.sleep(0.35)
            rec.update(gmp_page(gu)); time.sleep(0.35)
            du = b + '/' if (b + '/') in us else None
            if du:
                d = ipo.detail_page(du); time.sleep(0.35)
                rec['kpi'] = d.get('kpi'); rec['fin'] = ipo.fin_summary(d)
                pes = sorted(v for v in (ipo.num(r[2]) for r in (d.get('peers') or []) if len(r) > 2) if v and 0 < v < 400)
                rec['peer_pe'] = pes[len(pes) // 2] if pes else None
                info = d.get('info', {})
                rec['fresh'] = rec.get('fresh') or info.get('Fresh Issue')
                rec['ofs'] = rec.get('ofs') or info.get('Offer for Sale') or info.get('Offer for Sale:')
            rec['name'] = slug.replace('-ipo', '').replace('-', ' ')
        except Exception as e:
            rec = {'err': str(e)[:80]}
        cache[slug] = rec; n += 1
        if n % 50 == 0:
            log('  %d naye IPO pages padhe' % n)
            json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return cache


def nse_past():
    try:
        return ipo.nse('public-past-issues')
    except Exception as e:
        log('NSE past issues FAIL %s' % str(e)[:80]); return []


def load_bhav(bhav, syms):
    px = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(bhav, 'sec_bhavdata_full_*.csv')):
        with open(f, newline='', encoding='utf-8', errors='ignore') as h:
            rd = csv.reader(h); next(rd, None)
            for r in rd:
                if len(r) < 15:
                    continue
                s = r[0].strip()
                if s not in syms:
                    continue
                try:
                    d = datetime.datetime.strptime(r[2].strip(), '%d-%b-%Y').date()
                    o, c = float(r[4]), float(r[8])
                except ValueError:
                    continue
                px[s][d] = (o, c)
    return px


def stats(v):
    if not v:
        return '-'
    return 'n %3d | avg %+6.1f%% | median %+6.1f%% | plus %3d%%' % (len(v), sum(v) / len(v), statistics.median(v), 100 * sum(1 for x in v if x > 0) / len(v))


def main():
    os.makedirs('out', exist_ok=True)
    bhav = sys.argv[1] if len(sys.argv) > 1 else 'data'
    cache = collect()
    past = nse_past()
    log('NSE past issues: %d' % len(past))
    # NSE: naam ke shabd + listing date (+-4 din) se symbol
    idx = []
    for p in past:
        ld = pdate(p.get('listingDate')); ip = ipo.num(p.get('issuePrice'))
        if ld and ip:
            idx.append((set(ipo.nkey(p.get('company') or p.get('companyName') or '')), ld, p['symbol'], ip, p.get('securityType'),
                        pdate(p.get('ipoEndDate'))))
    recs = []
    for slug, r in cache.items():
        if not r or r.get('skip') or r.get('err'):
            continue
        iso = lambda v: datetime.date.fromisoformat(v) if v and v != 'None' else None
        ld, cd = iso(r.get('listing')), iso(r.get('close'))
        if not ld and not cd:
            continue
        w = set(ipo.nkey(r.get('name', '')))
        best = None
        for nk, nld, sym, ip, st, ned in idx:      # listing date (+-4 din) ya IPO band hone ki date (+-2 din) + naam
            okd = (ld and abs((nld - ld).days) <= 4) or (cd and ned and abs((ned - cd).days) <= 2)
            if okd and len(w & nk) >= min(2, len(w), len(nk)):
                best = (sym, ip, st, nld); break
        if best:
            recs.append(dict(r, slug=slug, sym=best[0], issue=best[1], kind='SME' if best[2] == 'SME' else 'MAIN', ld=best[3]))
    log('NSE se jude IPO: %d (baaki BSE-only / naam nahi mila)' % len(recs))
    px = load_bhav(bhav, set(x['sym'] for x in recs))
    rows = []
    for x in recs:
        p = px.get(x['sym'])
        if not p:
            continue
        ds = sorted(d for d in p if d >= x['ld'])
        if not ds or (ds[0] - x['ld']).days > 5:
            continue
        o, c = p[ds[0]]; ip = x['issue']
        d20 = p[ds[20]][1] if len(ds) > 20 else None; d60 = p[ds[60]][1] if len(ds) > 60 else None
        up = x.get('upper') or ip                       # price band na mile to NSE ka issue price
        y = dict(status='CLOSED', sub=x.get('sub') or {}, gmp_pct=(100.0 * x['gmp'] / up) if x.get('gmp') is not None and up else None,
                 kpi=x.get('kpi'), fin=x.get('fin') or {}, peer_pe=x.get('peer_pe'), fresh=x.get('fresh'), ofs=x.get('ofs'))
        y['ofs_only'] = bool(y['ofs']) and not y['fresh']
        eps = ipo.num((y['kpi'] or {}).get('Earning Per Share (EPS)'))
        y['pe'] = round(up / eps, 1) if eps and eps > 0 and up else None
        L, lv, _, F, fv, _ = ipo.score(y, 10 ** 9)
        rows.append(dict(sym=x['sym'], kind=x['kind'], listed=str(ds[0]), year=ds[0].year, issue=ip, open_g=round((o / ip - 1) * 100, 2),
                         close_g=round((c / ip - 1) * 100, 2), d20=round((d20 / ip - 1) * 100, 2) if d20 else None,
                         d60=round((d60 / ip - 1) * 100, 2) if d60 else None, qib=y['sub'].get('QIB'), total=y['sub'].get('TOTAL'),
                         rii=y['sub'].get('RII'), gmp_pct=round(y['gmp_pct'], 1) if y['gmp_pct'] is not None else None,
                         L=L, lv=lv, F=F, fv=fv))
    log('Listing bhav mila: %d IPO (%s se %s)' % (len(rows), min((r['listed'] for r in rows), default='-'), max((r['listed'] for r in rows), default='-')))
    log('Listing gain = listing din ka OPEN issue price se (allotment mila to yahi fayda). Close = listing din ka close.')
    out = {}
    for kind in ('MAIN', 'SME'):
        R = [r for r in rows if r['kind'] == kind]
        if not R:
            continue
        log(''); log('===== %s (%d IPO) =====' % ('MAINBOARD' if kind == 'MAIN' else 'SME', len(R)))
        log('Sab IPO          open: %s' % stats([r['open_g'] for r in R]))
        log('')
        log('-- "Listing" faisla (QIB + GMP) vs listing gain (open) / listing din close --')
        res = {}
        for v in ('APPLY', 'SOCH', 'SKIP'):
            a = [r['open_g'] for r in R if r['lv'] == v]; b = [r['close_g'] for r in R if r['lv'] == v]
            log('  %-6s open: %s' % (v, stats(a))); log('  %-6s close: %s' % ('', stats(b)))
            res[v] = dict(n=len(a), avg=round(sum(a) / len(a), 1) if a else None, med=round(statistics.median(a), 1) if a else None,
                          pos=round(100 * sum(1 for x in a if x > 0) / len(a)) if a else None)
        log(''); log('-- QIB (aakhri din) vs listing gain --')
        for lo_, hi_, lab in ((0, 1, '<1x'), (1, 10, '1-10x'), (10, 50, '10-50x'), (50, 1e9, '50x+')):
            log('  QIB %-7s %s' % (lab, stats([r['open_g'] for r in R if r['qib'] is not None and lo_ <= r['qib'] < hi_])))
        log(''); log('-- Aakhri GMP vs listing gain --')
        for lo_, hi_, lab in ((-1e9, 3, '<3%'), (3, 10, '3-10%'), (10, 25, '10-25%'), (25, 50, '25-50%'), (50, 1e9, '50%+')):
            v_ = [r for r in R if r['gmp_pct'] is not None and lo_ <= r['gmp_pct'] < hi_]
            err = [r['open_g'] - r['gmp_pct'] for r in v_]
            log('  GMP %-7s %s%s' % (lab, stats([r['open_g'] for r in v_]), ' | asli - GMP avg %+.1f%%' % (sum(err) / len(err)) if err else ''))
        log(''); log('-- "Company" faisla vs 60 din baad (issue price se) --')
        resf = {}
        for v in ('ACHHA', 'THEEK', 'KAMZOR'):
            a = [r['d60'] for r in R if r['fv'] == v and r['d60'] is not None]
            log('  %-6s 60 din: %s' % (v, stats(a)))
            log('  %-6s listing open: %s' % ('', stats([r['open_g'] for r in R if r['fv'] == v])))
            resf[v] = dict(n=len(a), avg=round(sum(a) / len(a), 1) if a else None, med=round(statistics.median(a), 1) if a else None,
                           pos=round(100 * sum(1 for x in a if x > 0) / len(a)) if a else None)
        log(''); log('-- Saal-war: APPLY vs SKIP (listing open avg) --')
        for yv in sorted(set(r['year'] for r in R)):
            a = [r['open_g'] for r in R if r['year'] == yv and r['lv'] == 'APPLY']; b = [r['open_g'] for r in R if r['year'] == yv and r['lv'] == 'SKIP']
            log('  %d  APPLY %s' % (yv, stats(a))); log('        SKIP  %s' % stats(b))
        out[kind] = dict(n=len(R), listing=res, company=resf, all=round(sum(r['open_g'] for r in R) / len(R), 1))
    with open('out/ipo_backtest.csv', 'w', newline='') as h:
        if rows:
            w = csv.DictWriter(h, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    open('out/ipo_backtest_summary.txt', 'w').write('\n'.join(LINES) + '\n')
    json.dump(dict(date=str(datetime.date.today()), n=len(rows), res=out), open('docs/ipo_backtest.json', 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
