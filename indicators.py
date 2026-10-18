# Mashhoor indicators aur platform-style signals (TradingView rating, Chartink jaise screeners) - sirf LONG, din ke close par.
# Har function list[bool] deta hai: sig[i] = din i ke close tak ke data se signal (aage ka data kabhi nahi).
# regime_study.py inhe baaki setups ki tarah har market haal me test karta hai (entry agle din open, kharcha 0.25%).


def sma(v, n):
    out = [None] * len(v); s = 0.0
    for i, x in enumerate(v):
        s += x
        if i >= n: s -= v[i - n]
        if i >= n - 1: out[i] = s / n
    return out


def ema(v, n):
    a = 2.0 / (n + 1); out = []; e = None
    for x in v:
        e = x if e is None else a * x + (1 - a) * e; out.append(e)
    return out


def wilder(v, n):
    out = [None] * len(v); e = None
    for i, x in enumerate(v):
        if i < n - 1: continue
        e = sum(v[i - n + 1:i + 1]) / n if e is None else (e * (n - 1) + x) / n
        out[i] = e
    return out


def rsi(cl, n=14):
    out = [None] * len(cl); au = ad = None
    for i in range(1, len(cl)):
        d = cl[i] - cl[i - 1]; up, dn = max(d, 0.0), max(-d, 0.0)
        if au is None: au, ad = up, dn
        else: au = (au * (n - 1) + up) / n; ad = (ad * (n - 1) + dn) / n
        if i >= n: out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


def roll(v, p, fn):
    """Rolling max/min over last p values (i-p+1..i), O(n). fn = max ya min. None jab tak p values na hon."""
    from collections import deque
    out = [None] * len(v); q = deque()
    better = (lambda a, b: a >= b) if fn is max else (lambda a, b: a <= b)
    for i, x in enumerate(v):
        if x is None:
            continue
        while q and better(x, v[q[-1]]): q.pop()
        q.append(i)
        while q[0] <= i - p: q.popleft()
        if i >= p - 1: out[i] = v[q[0]]
    return out


def cross_up(a, b, i):
    return a[i] is not None and b[i] is not None and a[i - 1] is not None and b[i - 1] is not None and a[i - 1] <= b[i - 1] and a[i] > b[i]


def stdev(v, n, i):
    w = v[i - n + 1:i + 1]; m = sum(w) / n
    return (sum((x - m) ** 2 for x in w) / n) ** 0.5


def all_signals(op, hi, lo, cl, vo, dl):
    n = len(cl); S = {}
    def arr(): return [False] * n
    tr = [hi[0] - lo[0]] + [max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1])) for i in range(1, n)]
    atr10 = wilder(tr, 10)
    r = rsi(cl)
    # 1) MACD (12,26,9) signal line ke upar cross
    m = [a - b for a, b in zip(ema(cl, 12), ema(cl, 26))]; ms = ema(m, 9)
    x = arr()
    for i in range(35, n): x[i] = cross_up(m, ms, i)
    S['MACD_CROSS'] = x
    # 2) RSI 30 ke upar wapas
    x = arr()
    for i in range(20, n): x[i] = r[i - 1] is not None and r[i - 1] < 30 <= r[i]
    S['RSI30_UP'] = x
    # 3) Supertrend (10,3) neeche se upar palta
    st_dir = [0] * n; fu = [0.0] * n; fl = [0.0] * n
    for i in range(n):
        if atr10[i] is None: continue
        mid = (hi[i] + lo[i]) / 2; ub = mid + 3 * atr10[i]; lb = mid - 3 * atr10[i]
        if i == 0 or atr10[i - 1] is None:
            fu[i], fl[i], st_dir[i] = ub, lb, 1; continue
        fu[i] = ub if (ub < fu[i - 1] or cl[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb if (lb > fl[i - 1] or cl[i - 1] < fl[i - 1]) else fl[i - 1]
        d = st_dir[i - 1]
        st_dir[i] = 1 if (d == -1 and cl[i] > fu[i - 1]) else -1 if (d == 1 and cl[i] < fl[i - 1]) else d
    x = arr()
    for i in range(30, n): x[i] = st_dir[i - 1] == -1 and st_dir[i] == 1
    S['SUPERTREND_FLIP'] = x
    # 4/5) Bollinger (20,2): lower band ke neeche close (mean reversion) / squeeze ke baad upper band ke upar
    s20 = sma(cl, 20); bw = [None] * n; lowb = [False] * n; up_bo = [False] * n
    for i in range(19, n):
        sd = stdev(cl, 20, i); bw[i] = 4 * sd / s20[i] if s20[i] else None
        lowb[i] = cl[i] < s20[i] - 2 * sd
        up_bo[i] = cl[i] > s20[i] + 2 * sd
    x = arr(); y = arr(); bw120 = roll(bw, 120, min); bw5 = roll(bw, 5, min)
    for i in range(140, n):
        x[i] = lowb[i] and not lowb[i - 1]
        y[i] = up_bo[i] and not up_bo[i - 1] and bw120[i - 1] is not None and bw5[i - 1] <= bw120[i - 1] * 1.05
    S['BB_LOWER'] = x; S['BB_SQUEEZE_BO'] = y
    # 6) Golden cross SMA50/200, 7) EMA 9/21 cross
    a50, a200 = sma(cl, 50), sma(cl, 200); e9, e21 = ema(cl, 9), ema(cl, 21)
    x = arr(); y = arr()
    for i in range(201, n): x[i] = cross_up(a50, a200, i)
    for i in range(25, n): y[i] = cross_up(e9, e21, i)
    S['GOLDEN_CROSS'] = x; S['EMA9_21_CROSS'] = y
    # 8) Stochastic (14,3,3): oversold (20 se neeche) me %K ne %D ko upar kaata
    k_ = [None] * n; h14, l14 = roll(hi, 14, max), roll(lo, 14, min)
    for i in range(13, n):
        h, l = h14[i], l14[i]; k_[i] = 100 * (cl[i] - l) / (h - l) if h > l else 50
    ks = [None] * n
    for i in range(15, n): ks[i] = sum(k_[i - 2:i + 1]) / 3
    ds_ = [None] * n
    for i in range(17, n): ds_[i] = sum(ks[i - 2:i + 1]) / 3
    x = arr()
    for i in range(20, n): x[i] = cross_up(ks, ds_, i) and ks[i - 1] < 20
    S['STOCH_OVERSOLD_X'] = x
    # 9) ADX > 25 aur +DI ne -DI ko upar kaata
    pdm = [0.0] + [max(hi[i] - hi[i - 1], 0) if hi[i] - hi[i - 1] > lo[i - 1] - lo[i] else 0.0 for i in range(1, n)]
    mdm = [0.0] + [max(lo[i - 1] - lo[i], 0) if lo[i - 1] - lo[i] > hi[i] - hi[i - 1] else 0.0 for i in range(1, n)]
    a14, p14, m14 = wilder(tr, 14), wilder(pdm, 14), wilder(mdm, 14)
    pdi = [100 * p / a if a and p is not None else None for p, a in zip(p14, a14)]
    mdi = [100 * m_ / a if a and m_ is not None else None for m_, a in zip(m14, a14)]
    dx = [abs(p - q) / (p + q) * 100 if p is not None and q is not None and p + q else 0.0 for p, q in zip(pdi, mdi)]
    adx = wilder(dx, 14)
    x = arr()
    for i in range(40, n): x[i] = adx[i] is not None and adx[i] > 25 and cross_up(pdi, mdi, i)
    S['ADX_DI_CROSS'] = x
    # 10) Donchian 55 (turtle): 55-din high ke upar close
    x = arr(); h55 = roll(hi, 55, max)
    for i in range(56, n): x[i] = cl[i] > h55[i - 1] and cl[i - 1] <= h55[i - 2]
    S['DONCHIAN55'] = x
    # 11) NR7: kal 7 din ki sabse chhoti range thi, aaj kal ke high ke upar close
    x = arr()
    for i in range(8, n):
        rg = [hi[k] - lo[k] for k in range(i - 7, i)]
        x[i] = rg[-1] == min(rg) and cl[i] > hi[i - 1]
    S['NR7_BREAK'] = x
    # 12) Gap & go (news/result jaisa): 3%+ gap up, volume 2x+, gap tika (close >= open)
    x = arr()
    for i in range(21, n):
        av = sum(vo[i - 20:i]) / 20.0
        x[i] = op[i] >= cl[i - 1] * 1.03 and av > 0 and vo[i] >= 2 * av and cl[i] >= op[i]
    S['GAP_AND_GO'] = x
    # 13) Delivery surge: delivery % apne 20-din avg ka 1.5x+, volume 1.5x+, price 2%+ upar (bade kharidar)
    x = arr()
    for i in range(21, n):
        if dl[i] is None: continue
        w = [d for d in dl[i - 20:i] if d is not None]
        av = sum(vo[i - 20:i]) / 20.0
        x[i] = len(w) >= 15 and dl[i] >= 1.5 * (sum(w) / len(w)) and av > 0 and vo[i] >= 1.5 * av and cl[i] >= cl[i - 1] * 1.02
    S['DELIVERY_SURGE'] = x
    # 14) TradingView jaisa "Strong Buy": 12 moving averages (SMA+EMA 10/20/30/50/100/200) me 11+ ke upar, aur 6 oscillator me 4+ buy
    mas = [sma(cl, p) for p in (10, 20, 30, 50, 100, 200)] + [ema(cl, p) for p in (10, 20, 30, 50, 100, 200)]
    cci = [None] * n
    tp = [(h + l + c) / 3 for h, l, c in zip(hi, lo, cl)]
    for i in range(19, n):
        w = tp[i - 19:i + 1]; mu = sum(w) / 20; md = sum(abs(t - mu) for t in w) / 20
        cci[i] = (tp[i] - mu) / (0.015 * md) if md else 0
    strong = [False] * n
    for i in range(201, n):
        ma_buy = sum(1 for a in mas if a[i] is not None and cl[i] > a[i])
        osc = sum([r[i] is not None and 50 < r[i] < 70, m[i] > ms[i], ks[i] is not None and ds_[i] is not None and ks[i] > ds_[i],
                   cci[i] is not None and cci[i] > 0, cl[i] > cl[i - 10], adx[i] is not None and adx[i] > 20 and pdi[i] > mdi[i]])
        strong[i] = ma_buy >= 11 and osc >= 4
    x = arr()
    for i in range(202, n): x[i] = strong[i] and not strong[i - 1]
    S['TV_STRONG_BUY'] = x
    # 15) Ichimoku: close cloud ke upar nikla aur tenkan > kijun
    RH = {p: roll(hi, p, max) for p in (9, 26, 52)}; RL = {p: roll(lo, p, min) for p in (9, 26, 52)}
    def mid(i, p): return (RH[p][i] + RL[p][i]) / 2
    x = arr()
    for i in range(80, n):
        j = i - 26
        top = max((mid(j, 9) + mid(j, 26)) / 2, mid(j, 52)); j1 = j - 1
        top1 = max((mid(j1, 9) + mid(j1, 26)) / 2, mid(j1, 52))
        x[i] = cl[i] > top and cl[i - 1] <= top1 and mid(i, 9) > mid(i, 26)
    S['ICHIMOKU_BREAK'] = x
    # 16) Parabolic SAR (0.02, 0.2) neeche palta
    x = arr(); up = True; sar = lo[0]; ep = hi[0]; af = 0.02
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, lo[i - 1], lo[i - 2] if i > 1 else lo[i - 1])
            if lo[i] < sar: up, sar, ep, af = False, ep, lo[i], 0.02
            elif hi[i] > ep: ep, af = hi[i], min(af + 0.02, 0.2)
        else:
            sar = max(sar, hi[i - 1], hi[i - 2] if i > 1 else hi[i - 1])
            if hi[i] > sar:
                up, sar, ep, af = True, ep, hi[i], 0.02
                if i > 30: x[i] = True
            elif lo[i] < ep: ep, af = lo[i], min(af + 0.02, 0.2)
    S['PSAR_FLIP'] = x
    # 17) CCI -100 ke upar wapas, 18) Williams %R -80 ke upar wapas
    x = arr(); y = arr()
    for i in range(21, n):
        x[i] = cci[i - 1] is not None and cci[i - 1] < -100 <= cci[i]
        y[i] = k_[i - 1] is not None and k_[i - 1] < 20 <= k_[i]
    S['CCI_UP'] = x; S['WILLR_UP'] = y
    # 19) Heikin-Ashi: 3+ laal ke baad pehli hari candle
    hao = [op[0]]; hac = [(op[0] + hi[0] + lo[0] + cl[0]) / 4]
    for i in range(1, n):
        hac.append((op[i] + hi[i] + lo[i] + cl[i]) / 4); hao.append((hao[-1] + hac[-2]) / 2)
    x = arr()
    for i in range(5, n): x[i] = hac[i] > hao[i] and all(hac[k] < hao[k] for k in range(i - 3, i))
    S['HEIKIN_FLIP'] = x
    # 20) Uptrend me kam-volume pullback ke baad kal ke high ke upar close (volume dry-up)
    x = arr(); e20, e50 = ema(cl, 20), ema(cl, 50)
    for i in range(55, n):
        av = sum(vo[i - 23:i - 3]) / 20.0
        x[i] = (cl[i] > e50[i] and e20[i] > e50[i] and av > 0 and max(vo[i - 3:i]) < 0.8 * av and cl[i - 1] < cl[i - 4]
                and cl[i] > hi[i - 1])
    S['VOL_DRYUP_PULLBACK'] = x
    return S


DESC = {'MACD_CROSS': 'MACD ne signal line ko upar kaata', 'RSI30_UP': 'RSI 30 ke neeche se upar aaya',
        'SUPERTREND_FLIP': 'Supertrend (10,3) green hua', 'BB_LOWER': 'Bollinger lower band ke neeche close',
        'BB_SQUEEZE_BO': 'Bollinger squeeze ke baad upper band ke upar', 'GOLDEN_CROSS': '50 SMA ne 200 SMA ko upar kaata',
        'EMA9_21_CROSS': 'EMA 9 ne EMA 21 ko upar kaata', 'STOCH_OVERSOLD_X': 'Stochastic oversold me cross',
        'ADX_DI_CROSS': 'ADX>25 aur +DI ne -DI kaata', 'DONCHIAN55': '55-din high ke upar (turtle)',
        'NR7_BREAK': 'NR7 (7 din ki sabse chhoti candle) ke upar break', 'GAP_AND_GO': '3%+ gap up, 2x volume, gap tika (news/result)',
        'DELIVERY_SURGE': 'Delivery % 1.5x, volume 1.5x, price 2%+ upar', 'TV_STRONG_BUY': 'TradingView jaisa Strong Buy rating',
        'ICHIMOKU_BREAK': 'Ichimoku cloud ke upar nikla', 'PSAR_FLIP': 'Parabolic SAR neeche palta',
        'CCI_UP': 'CCI -100 ke upar wapas', 'WILLR_UP': 'Williams %R -80 ke upar wapas',
        'HEIKIN_FLIP': 'Heikin-Ashi 3 laal ke baad hara', 'VOL_DRYUP_PULLBACK': 'Uptrend me kam-volume pullback ke baad break'}
