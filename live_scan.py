# Live (din ke beech) hisaab: docs/live_base.json (dip_scan.py roz shaam banata hai: har liquid stock ka kal tak ka
# EMA20/EMA50, RSI state, pichhle close) + Angel ka live bhav -> (1) live market breadth, (2) 3:15 taiyari list.
# Definitions dip_scan.py jaise hi (dono saath badalna). Live bhav = abhi tak ka bhav, din ka close nahi: sirf andaza.
A20, A50 = 2.0 / 21, 2.0 / 51


def regime_of(pct):
    return 'STRONG' if pct >= 60 else 'MIXED' if pct >= 40 else 'WEAK' if pct >= 25 else 'VWEAK'


def breadth(items, base):
    """items: {SYM: {'ltp':..}} (sirf aaj trade hue). base: live_base.json. -> dict ya None."""
    syms = base.get('syms') or {}
    up = tot = 0
    for s, b in syms.items():
        it = items.get(s)
        if not it or not it.get('ltp'):
            continue
        tot += 1
        up += it['ltp'] > b[1]          # ltp > kal ka EMA50  <=>  ltp > aaj ka EMA50 (EMA dono ke beech aata hai)
    if tot < max(50, 0.5 * len(syms)):
        return None
    pct = 100.0 * up / tot
    return {'pct': round(pct, 1), 'regime': regime_of(pct), 'n': tot, 'of': len(syms)}


def stock_state(ltp, b):
    e20 = A20 * ltp + (1 - A20) * b[0]
    e50 = A50 * ltp + (1 - A50) * b[1]
    d = ltp - b[8]
    au = b[6] * 13 / 14.0 + max(d, 0.0) / 14.0
    ad = b[7] * 13 / 14.0 + max(-d, 0.0) / 14.0
    rsi = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return dict(e20=e20, e50=e50, rsi=rsi, ret3=ltp / b[3] - 1, ret60=ltp / b[4] - 1, ret10=ltp / b[5] - 1)


def prep(items, base):
    """Abhi ke bhav par agar din yahin band ho to kaun Dip A / Bounce banega. -> {'dip': [...], 'bounce': [...]}"""
    dip, bounce = [], []
    for s, b in (base.get('syms') or {}).items():
        it = items.get(s)
        if not it or not it.get('ltp'):
            continue
        ltp = it['ltp']; k = stock_state(ltp, b)
        row = dict(s=s, ltp=ltp, r3=round(100 * k['ret3'], 1), rsi=round(k['rsi']), chg=round(100 * (ltp / b[8] - 1), 1))
        up = ltp > k['e50'] and k['e20'] > k['e50'] and k['e50'] > b[2]
        if up and k['ret3'] <= -0.08 and k['ret60'] > 0 and k['rsi'] < 45:
            dip.append(row)
        if ltp < k['e50'] and ((k['rsi'] < 30 and k['ret3'] <= -0.08) or (k['rsi'] < 25 and k['ret10'] <= -0.15)):
            bounce.append(dict(row, deep=not (k['rsi'] < 30 and k['ret3'] <= -0.08)))
    dip.sort(key=lambda r: r['r3']); bounce.sort(key=lambda r: r['rsi'])
    return {'dip': dip[:12], 'bounce': bounce[:12]}
