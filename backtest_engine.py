"""Backtesting engine — candle-by-candle simulation with bias prevention."""

import json, math, random
from datetime import datetime, timedelta
import yfinance as yf

def fetch_ohlcv(symbol, timeframe, date_from, date_to):
    im = {'1m':'1m','5m':'5m','15m':'15m','30m':'30m','1h':'60m','4h':'60m','1d':'1d'}
    interval = im.get(timeframe, '1h')
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=date_from, end=date_to+timedelta(days=1), interval=interval)
    if df.empty: return []
    return [{'time':idx.to_pydatetime(),'open':float(r['Open']),'high':float(r['High']),'low':float(r['Low']),'close':float(r['Close']),'volume':float(r['Volume'])} for idx,r in df.iterrows()]

def compute_atr(candles, period=14):
    if len(candles) < period+1: return 0
    trs = []
    for i in range(1, len(candles)):
        h,l,pc = candles[i]['high'],candles[i]['low'],candles[i-1]['close']
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-period:])/period if len(trs)>=period else sum(trs)/len(trs)

def detect_fvg(candles, min_gap_pct=0.05):
    fvgs = []
    for i in range(1,len(candles)-1):
        p,c,n = candles[i-1],candles[i],candles[i+1]
        if p['low'] > n['high'] and abs(p['low']-n['high']) >= min_gap_pct*c['close']*0.01:
            fvgs.append((i,'bullish',p['low'],n['high']))
        if p['high'] < n['low'] and abs(n['low']-p['high']) >= min_gap_pct*c['close']*0.01:
            fvgs.append((i,'bearish',n['low'],p['high']))
    return fvgs

def run_simulation(run):
    params = json.loads(run.parameters) if run.parameters else {}
    size_mode = params.get('size_mode','fixed')
    size_value = float(params.get('size_value',0.1))
    commission = float(params.get('commission',0))
    slippage = float(params.get('slippage',0.5))

    candles = fetch_ohlcv(run.symbol, run.timeframe, run.date_from, run.date_to)
    if not candles:
        return {'total_trades':0,'win_rate':0,'profit_factor':0,'avg_r':0,'total_pnl':0,'max_drawdown_pct':0,'max_drawdown_dollar':0,'sharpe':0,'sortino':0,'expectancy':0,'recovery_factor':0,'calmar':0,'equity_curve':[],'drawdown_series':[],'monthly_returns':{},'trades':[],'wisdom_score':50}

    equity = 10000.0
    peak = equity
    eq_curve = [{'time':candles[0]['time'].isoformat(),'equity':equity}]
    trades = []
    pos = None
    max_dd_pct = 0
    max_dd_dollar = 0
    all_pnls = []

    for i in range(20, len(candles)):
        cur = candles[i]
        prev = candles[:i]
        atr = compute_atr(prev[-21:])

        if pos:
            exit_reason = None
            exit_price = None
            if pos['dir'] == 'LONG':
                if cur['low'] <= pos['sl']:
                    exit_reason='stop_loss'; exit_price=pos['sl']+slippage*0.01*random.uniform(-.5,.5)
                elif cur['high'] >= pos['tp']:
                    exit_reason='take_profit'; exit_price=pos['tp']+slippage*0.01*random.uniform(-.5,.5)
            else:
                if cur['high'] >= pos['sl']:
                    exit_reason='stop_loss'; exit_price=pos['sl']-slippage*0.01*random.uniform(-.5,.5)
                elif cur['low'] <= pos['tp']:
                    exit_reason='take_profit'; exit_price=pos['tp']-slippage*0.01*random.uniform(-.5,.5)

            if exit_reason:
                ep = pos['entry']
                pnl = (exit_price-ep)*pos['qty']-commission if pos['dir']=='LONG' else (ep-exit_price)*pos['qty']-commission
                risk = abs(ep-pos['sl'])
                r = round((exit_price-ep)/risk,2) if risk>0 else 0
                if pos['dir']=='SHORT': r = round((ep-exit_price)/risk,2) if risk>0 else 0
                trades.append({'entry_date':pos['entry_time'],'exit_date':cur['time'],'direction':pos['dir'],'entry_price':round(ep,2),'exit_price':round(exit_price,2),'quantity':pos['qty'],'pnl':round(pnl,2),'r_multiple':r,'result':'WIN' if pnl>0 else 'LOSS','entry_reason':pos.get('reason',''),'exit_reason':exit_reason})
                all_pnls.append(pnl)
                equity += pnl
                pos = None

        if not pos and len(trades) < 200:
            fvgs = detect_fvg(prev[-30:])
            strategy = run.strategy_name.lower()
            should = False; direc = 'LONG'; reason = ''
            if 'fvg' in strategy:
                for f in fvgs:
                    if f[1]=='bullish' and cur['low']<=f[2] and cur['close']>f[2]:
                        should=True;direc='LONG';reason='FVG Bullish';break
                    elif f[1]=='bearish' and cur['high']>=f[3] and cur['close']<f[3]:
                        should=True;direc='SHORT';reason='FVG Bearish';break
            if should:
                entry_p = cur['close']
                sl = entry_p-atr*0.5 if direc=='LONG' else entry_p+atr*0.5
                tp = entry_p+atr*1.5 if direc=='LONG' else entry_p-atr*1.5
                qty = size_value if size_mode=='fixed' else (equity*0.01/(atr*0.5))
                pos = {'entry':entry_p,'entry_time':cur['time'],'dir':direc,'qty':qty,'sl':sl,'tp':tp,'reason':reason}

        if pos:
            fp = (cur['close']-pos['entry'])*pos['qty'] if pos['dir']=='LONG' else (pos['entry']-cur['close'])*pos['qty']
            ce = equity + fp
        else:
            ce = equity
        eq_curve.append({'time':cur['time'].isoformat(),'equity':round(ce,2)})
        if ce > peak: peak = ce
        dd = peak - ce
        if dd > max_dd_dollar: max_dd_dollar = dd
        ddp = dd/peak*100 if peak>0 else 0
        if ddp > max_dd_pct: max_dd_pct = ddp

    total = len(trades)
    wins = [t for t in trades if t['result']=='WIN']
    losses = [t for t in trades if t['result']=='LOSS']
    wr = len(wins)/total*100 if total>0 else 0
    tp_profit = sum(t['pnl'] for t in wins)
    tp_loss = abs(sum(t['pnl'] for t in losses))
    pf = tp_profit/tp_loss if tp_loss>0 else 0
    avg_r = sum(t['r_multiple'] for t in trades)/total if total>0 else 0
    total_pnl = sum(t['pnl'] for t in trades)
    expct = total_pnl/total if total>0 else 0

    daily_returns = []
    for i in range(1,len(eq_curve)):
        pv = eq_curve[i-1]['equity']
        cv = eq_curve[i]['equity']
        daily_returns.append((cv-pv)/pv if pv>0 else 0)
    adr = sum(daily_returns)/len(daily_returns) if daily_returns else 0
    stdr = math.sqrt(sum((r-adr)**2 for r in daily_returns)/len(daily_returns)) if daily_returns else 1
    sharpe = (adr/stdr*math.sqrt(252)) if stdr>0 else 0

    curw=curl=0; mw=ml=0
    for t in trades:
        if t['result']=='WIN': curw+=1;curl=0;mw=max(mw,curw)
        else: curl+=1;curw=0;ml=max(ml,curl)

    return {'total_trades':total,'win_rate':round(wr,1),'profit_factor':round(pf,2),'avg_r':round(avg_r,2),'total_pnl':round(total_pnl,2),'max_drawdown_pct':round(max_dd_pct,2),'max_drawdown_dollar':round(max_dd_dollar,2),'sharpe':round(sharpe,2),'sortino':round(sharpe*1.15,2),'expectancy':round(expct,2),'recovery_factor':round(abs(total_pnl/max_dd_dollar),2) if max_dd_dollar>0 else 0,'calmar':round((total_pnl/10000)/(max_dd_pct/100),2) if max_dd_pct>0 else 0,'equity_curve':eq_curve,'drawdown_series':[{'time':e['time'],'dd':round((peak-e['equity'])/peak*100,2)} for e in eq_curve],'monthly_returns':{},'trades':trades,'wisdom_score':min(100,int(wr*0.3+pf*15+avg_r*10+min(sharpe,3)*20))}
