# Swing Desk: handoff for a new Claude session

Owner: Sufiyan (Surat, part-time NSE swing trader). Capital Rs 50,000, max loss/day Rs 500-1,000, max 2 trades/day,
delivery holds 2-5 days, never options. Speaks Hinglish: reply in simple Hinglish, give click-level steps,
do the coding yourself (edit, test, commit, merge to main). Do not make him upload files.

## Pieces
- GitHub Pages app: docs/index.html (single-file vanilla JS PWA, "Swing Desk"). Tabs: Picks, Search, Trades, News, Global.
- Google Sheet 1KNw0jZTk29jwo2ohxdYl11CNxXAvOTcE4Y4lG1Vromw (tabs Screen, Picks, Pins, Settings, Live, TG) + Apps Script
  web app (PinsApi.gs, NOT in GitHub; he pastes it into Apps Script manually and deploys a New version; BOT_TOKEN is a
  placeholder in the repo copy). Live prices, locks, Telegram notes and alert push go through it.
- Actions (workflows in .github/workflows): screen, dip (evening), news (every 20 min in market hours), live (every ~25 s
  market hours, Angel One quotes -> Sheet; also runs watch_alerts.py -> Telegram IGNORE alerts), gap, restrict (ASM/GSM/
  circuit via NSE), global (Yahoo indices/commodities/big stocks + headlines), review (nightly picks_review.py),
  names, dip_enh/dipstudy/backtest/sweep/signals (studies).
- Scheduled tasks (Claude): morning shortlist 8:12 IST and gap-check 9:41 IST.

## Strategy facts (do not oversell)
- Breakout/pullback picks have no backtested edge. Dip-in-uptrend is the one verified setup: avgR ~+0.12 to +0.2,
  ~60% win, ~2 signals/week, 2025 ~0. Tier A (3d drop <= -8%) is stable; Tier B weaker. Dip A+ = Tier A + RVOL<1 + ADX>=25
  (hint only: n=253, +0.22R). Entry next open ~9:20, stop 2 ATR, max 5 days. Skip if gap >+1.5% or < -3%.
- Forward test: log 30-50 small trades as DIP-A / DIP-A+ / DIP-B in the Picks sheet reason column.
- Filters tested and rejected: candle patterns, Fibonacci, MACD, SMA200. Hold 10d is not stable (2025 negative).

## Data rules
- Analysis (EMA/RSI/ATR/trend/picks/Dip) uses the previous close (bhavcopy appears ~6 PM IST). Only prices/gap/SL are live.
- NSE and Yahoo are blocked from Claude's sandbox but work from GitHub Actions. raw.githubusercontent.com is readable.
- Alerts are rule-based, not backtested. Macro dates in docs/macro.json: RBI, India CPI, Budget need verifying.

## Known open items
- docs/picks_review.csv scorecard: picks_review.py now handles DIP rows (market entry next open).
- Dip stocks are not in angel_gap.py, but live alerts (watch_alerts.py) cover the Dip gap rule.
- Morning scheduled prompt could mention restrict/ASM, A+ and IGNORE rules.
- A stray folder github/ (no dot) in the repo root is a leftover and can be deleted.
