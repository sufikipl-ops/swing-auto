# Swing Desk: handoff for a new Claude session

Owner: Sufiyan (Surat, part-time NSE swing trader). Capital Rs 50,000, max loss/day Rs 500-1,000, max 2 trades/day,
delivery holds 2-5 days, never options. Speaks Hinglish: reply in simple Hinglish, give click-level steps,
do the coding yourself (edit, test, commit, merge to main). Do not make him upload files.

## Pieces
- GitHub Pages app: docs/index.html (single-file vanilla JS PWA, "Swing Desk"). Tabs: Picks, Search, Trades, News, Global.
- Google Sheet 1KNw0jZTk29jwo2ohxdYl11CNxXAvOTcE4Y4lG1Vromw (tabs Screen, Picks, Pins, Settings, Live, TG) + Apps Script
  web app (PinsApi.gs, NOT in GitHub; he pastes it into Apps Script manually and deploys via Manage deployments -> Edit ->
  New version, never a new deployment: the /exec URL is hard-coded in docs/index.html). Live prices, locks, Telegram notes
  and alert push go through it. Telegram notes now come by POLLING (setupTelegramPolling, 5-min trigger tgPoll) because the
  webhook got "302 Found" from Apps Script and Telegram stalled (fixed 2026-10-17; bot token was rotated).
  The Google Sheets connector (if attached) can read the TG/Picks/Settings tabs directly for debugging.
- Actions (workflows in .github/workflows): screen, dip (evening), news (every 20 min in market hours), live (every ~25 s
  market hours, Angel One quotes -> Sheet; also runs watch_alerts.py -> Telegram IGNORE alerts), gap, restrict (ASM/GSM/
  circuit via NSE), global (Yahoo indices/commodities/big stocks + headlines), review (nightly picks_review.py),
  names, funda (19:25 IST: promoter pledge/holding from NSE, D/E + PE/ROE/growth from Yahoo -> docs/funda.json),
  app (stocks.json; also 19:50 backup run). screen/gap/review copy their CSV into docs/ themselves; all daily workflows
  retry their push 5x (an app run once lost the push race to dip and left the app on old picks).
- news_events.py + news_more.py: NSE + BSE announcements (BSE needs cookie warm-up; NSE/BSE dupes merged within 20 min),
  Google News per stock (docs/stock_news.json), ET/BS/Moneycontrol/Mint RSS; locked stocks included; EVENT_UNKNOWN flag
  when the result-date lookup fails (checklist shows '?', never a false pass).
- Studies (manual workflow_dispatch): dip_enh, dipstudy, dip_validate, backtest, sweep, signals, events, filters,
  orb (Angel 15-min), momdip, trendline. Results in out/*_summary.txt.
- Scheduled tasks (Claude): morning shortlist 8:12 IST and gap-check 9:41 IST.

## Strategy facts (do not oversell)
- Breakout/pullback picks have no backtested edge. Dip-in-uptrend is the one verified setup: avgR ~+0.12 to +0.2,
  ~60% win, ~2 signals/week, 2025 ~0. Tier A (3d drop <= -8%) is stable; Tier B weaker. Dip A+ = Tier A + RVOL<1 + ADX>=25
  (hint only: n=253, +0.22R). Entry next open ~9:20, stop 2 ATR, max 5 days. Skip if gap >+1.5% or < -3%.
- Forward test: log 30-50 small trades as DIP-A / DIP-A+ / DIP-B in the Picks sheet reason column.
- Filters tested and rejected: candle patterns (twice: dip_enh and momdip reversal candle overfit), Fibonacci, MACD,
  SMA200. Hold 10d is not stable (2025 negative).
- Out-of-sample (2025-26) numbers are what the app quotes: Tier A ~+0.09R, A+ ~+0.15R, Tier B ~0R.
- momdip (2026-10-17): only the sharp 3-day dip zone works; EMA20/EMA50 touch, 10% off high, breakout retest do not.
  60-day return top 20% ("Momentum") + dip: test +0.04R vs plain dip +0.02R -> shown only as a 'Momentum' tag
  (dip_scan.py MOM60_TOP20 column), not a rule.
- Intraday ORB 15-min + 8 EMA (an Instagram reel): 213 F&O stocks, 1 year: ~0R before costs, -0.2 to -0.35R after 0.15%
  costs; 0 of 32 combos positive. Do not add intraday setups; costs kill tight stops.
- Trendline break (>=3 pivots, owner's reel, long+short, sweep/trend filters, 2-4R): 0 of 48 combos positive in both
  train and test. Long test -0.09 to -0.19R (random -0.15R). Short test slightly plus only because 2025-26 was weak (train
  negative). Not added.
- R:R rule in app: picks without room for 1:2 before the next 20/60-day/52-week high get an 'R:R kam' chip and -12 rank
  (not backtested; targets themselves stay realistic, since 2R targets did not help in the sweep backtest).
- Owner wants 2-3 setups side by side, each labelled with its strategy + backtest status, and the daily move (ATR) shown.
  Shorts: cash market allows intraday only; 2-5 day shorts need futures (too big for Rs 50k) or options (he avoids).

## Data rules
- Analysis (EMA/RSI/ATR/trend/picks/Dip) uses the previous close (bhavcopy appears ~6 PM IST). Only prices/gap/SL are live.
- NSE and Yahoo are blocked from Claude's sandbox but work from GitHub Actions. raw.githubusercontent.com is readable.
- Alerts are rule-based, not backtested. Macro dates in docs/macro.json: RBI, India CPI, Budget need verifying.

## App notes (2026-10-17)
- Plan tiles open list pages; floating "AI se poocho" on stock detail opens claude.ai/new?q=<context prompt> (no API key;
  owner declined an in-app paid API chat). Ignore list = watchlist rows grouped by reason with the numbers behind each
  (ASM type LT/ST from restrict.py + how far it ran, circuit as info only). Quality screen is a PASS/FAIL table.
- Pre-trade checklist is fully automatic (no manual ticks except optional fundamentals). Logged trades are checked
  against the app's trigger (picks_review.py entry_check: OK / EARLY / CHASED).

## Known open items
- docs/picks_review.csv scorecard: picks_review.py now handles DIP rows (market entry next open).
- Dip stocks are not in angel_gap.py, but live alerts (watch_alerts.py) cover the Dip gap rule.
- Morning scheduled prompt could mention restrict/ASM, A+ and IGNORE rules.
- Offered, not built: bulk/block deal + insider buying chip on picks.

## Market regime (regime_study.py, regime.yml har Shanivar)
- Regime = liquid stocks (20-din turnover 5cr+) me kitne % EMA50 ke upar: STRONG 60+, MIXED 40-60, WEAK 25-40, VWEAK <25.
- Result (SL 2ATR, max 5 din, 0.25% cost): WEAK me Dip A +0.15R (59% jeet, 4/5 saal); VWEAK me Oversold bounce +0.26R (67%, 5/5) aur Gehra oversold +0.16R (5/5);
  MIXED me koi setup pakka nahi; Breakout har haal me minus.
- App: Picks par "Aaj ka market" card (docs/regime.json + docs/regime_today.json), Breakout/Pullback/Dip strategy line par
  "Is market me chala / nahi chalta" chip, Oversold bounce cards sirf VWEAK me (warna ek line).
- dip_scan.py roz: BOUNCE/DEEP rows dip_latest.csv me (app inhe Dip list se alag rakhta hai) + docs/regime_today.json.

## Live setup study (intraswing_study.py, Actions > intraswing, manual)
- 15-min Angel data (F&O 213 stocks, Jan-Oct 2026, ~176 test din). Breakout / reversal / Dip A / bounce din me pakad ke 3:15 entry vs kal open.
- Result 2026-10-17: koi setup PASS nahi. Breakout har haal me minus (-0.04 se -0.55R). Reversal minus. Bounce 3:15 VWEAK +0.13R
  par doosre aadhe me -0.18R (fail). 3:15 entry aksar kal-open se thoda kam bura (gap ka nuksan bachta hai) par dono minus.
- Faisla: live "trade layak" highlighter nahi banaya. Data kam hai: data_orb cache badhta nahi (fetch_all purani file skip karta hai).
