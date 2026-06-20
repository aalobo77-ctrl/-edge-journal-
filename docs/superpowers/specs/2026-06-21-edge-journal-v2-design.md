# Edge Journal v2 — The Uncopyable Trading Operating System

## Overview

A premium trading journal that surpasses TradeZella by combining MT5-native automation, a 150+ strategy library, institutional-grade backtesting with 200 years of market wisdom, AI trade replay with synthetic commentary, and a 300-year fused market oracle — all unified under a cross-asset analytics engine handling forex, metals, crypto, stocks, ETFs, indices, mutual funds, index funds, and commodities.

## Architecture

```
MT5 (trader's PC)
 │
 ├─ EA (MQL5) monitors every tick
 │   ├─ Detects trade open → POSTs entry + market snapshot
 │   ├─ Detects trade close → POSTs exit + full context
 │   ├─ On startup → syncs missed trades from HistorySelect()
 │   └─ Every N minutes → POSTs open positions for live P&L
 │
 ▼
 Flask API + SQLite/PostgreSQL
 │
 ├─ /api/sync/trade — create/update trade
 ├─ /api/sync/positions — live P&L updates
 ├─ /api/data/candles — OHLCV fetcher (caching layer)
 │
 ▼
 Data Sources (free):
 ├─ OANDA API → Forex, Metals, Commodities
 ├─ yfinance → Stocks, ETFs, Indices, Mutual Funds, Index Funds
 └─ Binance API → Crypto
```

## Sub-Projects (Build Order)

1. **Reports** (standalone, quick win) — PDF/CSV generation
2. **Broker Sync** — MT5 EA + sync API
3. **Analysis Engine** — Backtesting + Trade Replay
4. **AI Layer** — Oracle + AI commentary
5. **Community** — Shared trades, leaderboards

This spec covers the first phase: Broker Sync + Backtesting + Trade Replay + AI Oracle + Reports.

## Section 1 — MT5 EA Design

### MQL5 Expert Advisor

- Fires on `OnTrade()` → captures open/close/modify instantly
- Entry snapshot: spread, ATR(14), nearest HTF OB/FVG, session time
- On `OnInit()` → `HistorySelect()` for missed trades since last sync → batch POST
- Every 30 seconds → `PositionSelect()` → POST open positions with floating P&L
- On close → book grade evaluation + trade data POST
- Configurable via EA inputs: journal URL, API key, sync interval

### Trade POST Payload

```json
{
  "symbol": "XAUUSD",
  "asset_class": "metal",
  "direction": "SELL",
  "volume": 0.1,
  "entry_price": 2345.67,
  "exit_price": 2338.12,
  "entry_time": "ISO8601",
  "exit_time": "ISO8601",
  "commission": -3.50,
  "swap": -1.20,
  "profit": 75.40,
  "magic_number": 123,
  "comment": "FVG entry NY killzone",
  "ict_snapshot": {
    "session": "NY AM",
    "killzone_active": true,
    "nearest_ob_distance_pips": 2.3,
    "fvg_present": true,
    "lq_grab_occurred": true,
    "htf_trend": "BULLISH",
    "atr_14": 18.5,
    "spread_at_entry": 0.8
  },
  "setup_type": "FVG (Fair Value Gap)",
  "book_grade": {
    "killzone_obeyed": true,
    "htf_aligned": true,
    "pd_array_respected": true,
    "rr_ratio": 2.4
  }
}
```

### Asset Class Detection

| Symbol Pattern | Asset Class | Data Source |
|---|---|---|
| XAU, XAG, XPT | metal | OANDA |
| EURUSD, GBPJPY (6 letter) | forex | OANDA |
| BTCUSD, ETHUSD | crypto | Binance |
| US30, NAS100, SPX500 | index | yfinance |
| AAPL, TSLA (ticker) | stock | yfinance |
| OIL, NATGAS | commodity | OANDA |
| ETF tickers (.TO, ARKK) | etf | yfinance |
| Mutual fund tickers | mutual_fund | yfinance (most tickers; fallback to manual entry) |
| Index funds (VOO, VTI) | index_fund | yfinance |

Note: yfinance covers >95% of US-traded equities, ETFs, mutual funds, and index funds. Instruments not found fall back to manual entry or CSV import.

### MT5 EA Deliverable

The EA is provided as:
1. Source code file (`EdgeJournal.mq5`) — user can inspect/review
2. Compiled executable (`EdgeJournal.ex5`) — drag-and-drop onto any MT5 chart
3. Setup guide with screenshots for allowing WebRequest in MT5

### Book Grade Algorithm

- **A** (90-100): All confluence factors met, correct session, correct HTF alignment, R:R ≥ 2:1, no manual SL move, spread < 1.5 pips
- **B** (75-89): Majority confluence met, correct session, correct HTF, R:R ≥ 1.5:1, minor management issue
- **C** (50-74): Partial confluence, off-session, HTF unclear, R:R < 1.5:1, management issues
- **D** (25-49): Minimal confluence, wrong session, wrong HTF bias, poor R:R, significant management errors
- **F** (0-24): No confluence criteria met, revenge trade, no SL, over-sized

## Section 2 — Universal Strategy Library

### Taxonomy

- **Institutional / Smart Money** (15): FVG (3 variants), Order Block (4), LQ Grab, Silver Bullet (3), Killzone (4), MSS/CHoCH (3), Breaker (3), OTE (3), IFVG (2), CISD, FIF, Weekly Bias, PD Array Matrix, Liquidity Void, Judgment Day
- **Price Action** (22): S/R, Trendline, Channel, Pin Bar, Engulfing, Inside Bar, Outside Bar, Doji (3), Harami, Morning/Evening Star, Three Soldiers/Crows, Piercing/Dark Cloud, Tweezers, Hanging Man/Shooting Star, Hammer/Inverted, Spinning Top, Marubozu, Fakeout/Trap, 2-Bar, 3-Bar, Gap, Climax
- **Chart Patterns** (18): H&S, Double Top/Bottom, Triple, Asc/Desc Triangle, Sym Triangle, Expanding Triangle, Wedge (3), Flag (3), Rectangle, Cup & Handle, Rounding, Measured Move, ABCD, Three-Drive, Island, Throwback, W/M
- **Indicator-Based** (28): MA Cross (4), MA Pullback, MA Ribbon, RSI Div (3), RSI Reversal, MACD (3), Bollinger (3), Ichimoku (4), Parabolic SAR, SuperTrend, ATR (2), Stochastic, ADX, Keltner, Donchian, CCI, Williams %R, MFI, OBV, A/D, CMF, TRIX, Vortex, Pivot (4), Standard Pivot
- **Harmonic** (10): Gartley, Bat, Butterfly, Crab, Deep Crab, Shark, Cypher, ABCD, Three Drives, 5-0
- **Order Flow & Volume** (14): Volume Profile (3), POC, VAH/VAL, Delta Div, Cumulative Delta, Footprint (3), Order Book Imbalance, Tape Reading, CVD, VWAP (2), OBV, VSA
- **Statistical & Quant** (10): Mean Reversion (3), Pairs, Momentum, Seasonality, Correlation, Std Dev, Regression, Kelly, Monte Carlo, Walk-Forward
- **Scalping** (10): Tick Chart, Range, Momentum, Market Making, Order Flow, Tape Reading, 1m Breakout, Liquidity, News, Candle Close
- **Crypto-Specific** (8): Liquidation Hunt, Funding Arbitrage, Gamma Squeeze, AMM Arb, CEX-DEX, Whale Tracking, NFT Floor, Cascade
- **Options** (8): Covered Call, Protective Put, Iron Condor, Straddle, Strangle, Bull Put, Bear Call, Butterfly
- **Fundamental & Macro** (7): News, Central Bank, COT, GDP, Earnings, Dividend, Merger Arb
- **Custom & Hybrid** (∞): User-defined rule combinations

Each strategy stores: name, category, direction, timeframe, session, description, entry_criteria, exit_criteria, risk_rules, checklist, entry_rules_programmatic (JSON), exit_rules_programmatic (JSON).

### Variant System

Many strategies have multiple variants (e.g. FVG has Standard, MTF, and 1m). The variant system works as:

- Each base strategy has a `variants` JSON field mapping variant names to parameter overrides
- "Standard" is always the default if no variant specified
- Parameters can differ across variants: min gap size, required confluence, timeframe
- Backtesting uses the variant's parameters when computing entries/exits
- Trade tagging includes both strategy name and variant (e.g. "FVG (Fair Value Gap) — 1m"):

### Strategy Exchange UI

- Browse, filter, search grid
- Featured (user's best performers) and trending sections
- Each card shows: name, tags, win rate, avg R, confluence score
- Actions: View, Backtest, Practice, Log Trade

## Section 3 — Backtesting Engine

### Pipeline

1. User configures: strategy, variant, symbol, timeframe, date range, parameters, risk settings
2. Data Fetcher retrieves OHLCV from OANDA/yfinance/Binance with local caching (24h TTL)
3. Simulation Engine runs candle-by-candle loop:
   - Entry rule evaluator
   - Exit rule evaluator
   - SL/TP management
   - Position sizing (fixed / % risk / Kelly / half-Kelly)
   - Commission & slippage model
4. Metrics Engine computes: win rate, profit factor, max drawdown ($/%), Sharpe/Sortino, avg R, R distribution, expectancy, recovery factor, Calmar, consecutive W/L, % profitable months, VAMI, Monte Carlo
5. Output: full report, trade list CSV/JSON, equity curve chart, drawdown chart, monthly heatmap, R distribution, auto-save for replay

### Bias Prevention (Always-On)

- Survivorship bias check
- Look-ahead bias prevention (all indicators use only past data)
- Curve-fitting detection (Sharpe > 3 warning)
- Overfitting detection (rules-to-trades ratio)
- Selection bias check (random OOS windows)
- Data snooping correction (Bonferroni-adjusted)
- Outlier influence analysis (remove top/bottom 5%)
- Regime dependency analysis (trending/ranging/volatile)

### Robustness Testing

- **Monte Carlo** (10,000 sims): confidence intervals, probability of profit, drawdown percentiles
- **Walk-Forward Analysis** (12 monthly windows): in-sample vs out-of-sample decay
- **Regime Analysis**: performance in detected market regimes
- **Position Sizing Sensitivity**: fixed vs 1% vs 2% vs Kelly vs half-Kelly
- **Multi-Instrument Validation**: test on correlated assets

### Realism Settings

- Spread: historical from OANDA
- Slippage: random 0-1 pip on market orders
- Commission: user's broker structure
- Swap: overnight funding by instrument
- Fill probability: 99% market, 85% limit, 95% stop
- Partial fills on low-volume instruments
- Latency: random 100-500ms
- MT5 execution model simulation

### 200-Year Knowledge Layer

All backtest results cross-referenced against lessons from: Livermore, Wyckoff, Baruch, Graham, Gann, Darvas, O'Neil, Lynch, Soros, Tudor Jones, Druckenmiller, Dalio, Kovner, Dennis, Eckhardt, Seykota, Schwartz, Hite, Marcus, Simons, Harding, Asness, Marks, Ackman, Munger, Buffett + 147 more legends.

Output includes a "Market Wisdom Score" and specific legend quotes applicable to the strategy's strengths/weaknesses, plus a "Discipline Score" across 6 axes: Discipline, Risk Management, Emotional Control, Position Sizing, Exit Discipline, Adaptability.

## Section 4 — Trade Replay

- Every closed trade auto-generates replay data (20 candles before entry, 20 after exit — or full session)
- Chart.js canvas with candlestick rendering
- Entry/SL/TP lines overlaid
- Controls: play, pause, step forward/back, speed selector (0.5x-4x)
- Live stats panel: current P&L, current R, pips to SL, pips to TP
- Decision point markers: scale-outs, SL moves, partial exits
- AI Commentary Layer:

### Commentary Triggers

| Candle | AI Says |
|---|---|
| Entry candle | Entry quality assessment, spread check, HTF alignment |
| Mistake detected | SL move, early exit, over-trading signal |
| SL/TP hit | Why it happened, what invalidated the thesis |
| Scale out | Opportunity cost calculation |
| Good decision | Positive reinforcement with pattern note |
| End of replay | Scorecard + improvement for next time |

### AI Review Page Rebrand

The existing `/ai-review` page is replaced with the Oracle interface. The Oracle is the single source of AI-powered analysis, replacing the old rule-based AI review card. Existing AI review history is preserved and accessible from the Oracle's archive.

## Section 5 — AI Oracle (300-Year Synthetic Market Intelligence)

### Architecture

5 fused consciousness layers:
1. **The Technician** — market structure, patterns, levels
2. **The Quant** — probabilities, edge, expectancy, risk of ruin
3. **The Psychologist** — tilt, fear, greed, overconfidence
4. **The Historian** — regime shifts, cyclical patterns, market memory
5. **The Philosopher** — purpose, life context, relationship to risk

Each layer is a rule-based expert system (no external API calls — all local computation from trade DB + pre-distilled knowledge base). The Synthesis Engine debates and produces weighted consensus output.

### Knowledge Database

- 1,847 distilled lessons from 30+ trading legends
- 2,847 research papers extracted (Kahneman, Tversky, Thaler, Markowitz, Fama, Taleb, Lo, Sharpe, Grindold, Aronson, Schwager + more)
- 4,016 historical events cataloged (crashes, bull markets, regime changes, panics, bubbles, central bank interventions)

### Capabilities

- Daily briefing: yesterday's review, today's plan, tilt detection
- Chat interface: grade last trade, analyze patterns, suggest improvements
- 30-day performance protocol generation
- Future trajectory prediction (continue current vs follow protocol)
- Emotional state detection (arousal vs baseline)
- Real-time tilt cascade warning system
- Position sizing criticism (Kelly vs current behavior)
- Exit discipline scoring
- Personalized study assignment per weakness detected
- Voice mode (future): reads daily briefing aloud

## Section 6 — Reports

- PDF generation (weekly/monthly/yearly summaries)
- CSV export of any trade list, backtest results
- Report sections: performance summary, equity curve, strategy breakdown, worst/best trades, drawdown analysis, AI commentary
- Auto-generated end-of-day report

## Section 7 — Automation (2100s Experience)

- MT5 EA syncs trades in real-time — zero manual entry
- Tilt detection + browser push notification
- Auto-generated trade replay for every closed trade
- Command bar (Ctrl+K) for instant any-action access
- Proactive dashboard feed: personalized performance coaching
- Predictive analytics: trajectory projection, what-if simulation
- End-of-day auto-report generation

## Database Schema Additions

### New Models

- `StrategyTemplate` — pre-built strategy definitions (already exists, expand)
- `BacktestRun` — backtest request/results storage
- `BacktestTrade` — individual simulated trades from backtest
- `ReplayData` — pre-computed candle data for trade replay
- `OracleInsight` — cached oracle analysis results
- `SyncLog` — MT5 EA sync audit trail
- `Report` — generated report metadata

### Expanded Trade Model

Add fields: `asset_class`, `ict_snapshot` (JSON), `book_grade` (JSON), `sync_source` (manual/mt5/csv), `sync_id` (MT5 ticket number), `replay_available` (boolean)

## Key Principles

1. All AI runs locally — zero API costs, zero latency, zero external dependencies
2. All data sources are free — OANDA, yfinance, Binance
3. User owns all data — full export available at any time
4. Defensibility through MT5 EA integration + proprietary ICT scoring + personal AI training
5. No paid subscriptions — the entire platform is free
6. PythonAnywhere deployment for 24/7 availability
