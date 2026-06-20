import os, threading, time, csv, io, json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
from sqlalchemy import func, case

app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'tz.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.template_filter('fromjson')
def fromjson_filter(s):
    import json
    try: return json.loads(s)
    except: return {}

# ─── MODELS ─────────────────────────────────────────────

TAG_CHOICES = ['FVG', 'Order Block', 'MSS / CHoCH', 'Liquidity Grab', 'Silver Bullet',
               'Breaker Block', 'OTE', 'Killzone', 'Supertrend', 'Breakout', 'Reversal',
               'Scalp', 'Swing', 'News', 'Earnings', 'Other']

SESSION_CHOICES = ['Asia', 'London', 'NY', 'London-NY Overlap', 'Sydney', 'Pre-Market', 'After-Hours']

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    daily_goal = db.Column(db.Float, default=0)
    weekly_goal = db.Column(db.Float, default=0)
    monthly_goal = db.Column(db.Float, default=0)
    starting_balance = db.Column(db.Float, default=10000.0)
    trades = db.relationship('Trade', backref='user', lazy=True, cascade='all, delete-orphan')

class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    exit_price = db.Column(db.Float, nullable=True)
    stop_loss = db.Column(db.Float, nullable=True)
    take_profit = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Float, default=1.0)
    fees = db.Column(db.Float, default=0)
    pnl = db.Column(db.Float, nullable=True)
    pnl_pct = db.Column(db.Float, nullable=True)
    result = db.Column(db.String(10), nullable=True)
    setup_type = db.Column(db.String(50), nullable=True)
    session = db.Column(db.String(30), nullable=True)
    tags = db.Column(db.String(256), nullable=True)
    emotion = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    screenshot = db.Column(db.String(256), nullable=True)
    entry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    exit_date = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    r_multiple = db.Column(db.Float, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'quantity': self.quantity,
            'fees': round(self.fees, 2),
            'pnl': round(self.pnl, 2) if self.pnl else 0,
            'pnl_pct': round(self.pnl_pct, 2) if self.pnl_pct else 0,
            'result': self.result or 'OPEN',
            'setup_type': self.setup_type or '',
            'session': self.session or '',
            'tags': self.tags or '',
            'emotion': self.emotion or '',
            'notes': self.notes or '',
            'entry_date': self.entry_date.strftime('%Y-%m-%dT%H:%M') if self.entry_date else '',
            'exit_date': self.exit_date.strftime('%Y-%m-%dT%H:%M') if self.exit_date else '',
            'duration_minutes': self.duration_minutes,
            'r_multiple': round(self.r_multiple, 2) if self.r_multiple else 0,
        }

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    title = db.Column(db.String(200), nullable=True)
    type = db.Column(db.String(20), default='plan')  # 'plan', 'review', 'note'
    content = db.Column(db.Text, nullable=True)
    mood = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AIReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    review_text = db.Column(db.Text, nullable=True)
    patterns = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, default=0)

class StrategyTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    direction = db.Column(db.String(10), nullable=True)
    timeframe = db.Column(db.String(20), nullable=True)
    session = db.Column(db.String(30), nullable=True)
    entry_criteria = db.Column(db.Text, nullable=True)
    exit_criteria = db.Column(db.Text, nullable=True)
    risk_rules = db.Column(db.Text, nullable=True)
    checklist = db.Column(db.Text, nullable=True)
    is_custom = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

ICTTEMPLATES = [
    {'name':'FVG (Fair Value Gap)','category':'ICT','direction':'BOTH','timeframe':'1m-5m','session':'Killzone',
     'description':'Trade the Fair Value Gap — price returns to fill the gap and continues.',
     'entry_criteria':'1. Identify FVG on 1m/5m\n2. Wait for price to touch 50% of gap\n3. Entry on confirmation close\n4. Must have MSS on HTF',
     'exit_criteria':'1. TP1: 1:1 risk\n2. TP2: Next OB/FVG\n3. Trail at HH/HL break',
     'risk_rules':'1. SL beyond FVG opposite side\n2. Max 1% risk\n3. No trade if gap >20 points',
     'checklist':'FVG identified on MTF\nPrice at 50% gap\nHTF trend aligned\nCandle confirmation\nNo conflicting news'},
    {'name':'Order Block (OB)','category':'ICT','direction':'BOTH','timeframe':'5m-15m','session':'London/NY',
     'description':'Trade the institutional Order Block — price revisits the OB and reacts.',
     'entry_criteria':'1. Identify OB on HTF (1h/4h)\n2. Drop to 5m for entry\n3. Wait for LQ grab\n4. Enter on MSS + FVG',
     'exit_criteria':'1. TP1: Previous swing\n2. TP2: Next OB level\n3. Trail at 1:1',
     'risk_rules':'1. SL beyond OB by 2-3 points\n2. 0.5-1.5% risk\n3. If OB breached, invalidate',
     'checklist':'HTF OB confirmed\nLQ grab occurred\nMSS confirmed\nFVG for entry\nR:R >= 1:2'},
    {'name':'Liquidity Grab','category':'ICT','direction':'BOTH','timeframe':'5m-15m','session':'NY AM',
     'description':'Identify liquidity grabs at key levels and trade the reversal.',
     'entry_criteria':'1. Identify equal HH/LL on 5m-15m\n2. Wait for grab above/below\n3. MSS reversal\n4. Enter on FVG or orderflow shift',
     'exit_criteria':'1. TP1: Opposite LQ zone\n2. TP2: Next level\n3. Trail at 1.5R',
     'risk_rules':'1. SL beyond grab wick\n2. Max 1% risk\n3. No reversal in 3 candles? Exit',
     'checklist':'Equal HH/LL identified\nLQ occurred\nMSS confirmed\nEntry FVG formed\nBOS on HTF'},
    {'name':'Killzone Strategy','category':'ICT','direction':'BOTH','timeframe':'1m-5m','session':'Killzone',
     'description':'Trade using ICT Killzone concepts — London, NY AM, NY PM sessions.',
     'entry_criteria':'1. Identify killzone session\n2. Look for PD array\n3. Wait for displacement\n4. Enter on MSS + retracement',
     'exit_criteria':'1. TP: Killzone opposite edge\n2. SL: Beyond the PD array',
     'risk_rules':'1. Only trade during killzone\n2. Max 2 trades per killzone',
     'checklist':'Killzone active\nPD array identified\nDisplacement occurred\nMSS confirmed\nRisk within limits'},
    {'name':'Silver Bullet','category':'ICT','direction':'BOTH','timeframe':'1m','session':'Killzone',
     'description':'ICT Silver Bullet — first 15 min of London and NY killzones.',
     'entry_criteria':'1. First 15 min of London/NY killzone\n2. Identify sweep\n3. If sweep occurred, expect reversal\n4. Enter on 1m FVG',
     'exit_criteria':'1. TP: Previous day H/L\n2. SL: Beyond sweep wick\n3. Max hold: 30 min',
     'risk_rules':'1. Only first 15 min of session\n2. 0.5% risk per trade\n3. Miss the window? Skip.',
     'checklist':'First 15 min window\nSweep occurred\n1m FVG formed\nHTF bias aligned\nNews check clear'},
    {'name':'Breaker Block','category':'ICT','direction':'BOTH','timeframe':'15m-1h','session':'Any',
     'description':'Trade the Breaker Block — MSS followed by breaker retest.',
     'entry_criteria':'1. Identify MSS on HTF\n2. Price retraces to old OB\n3. That OB becomes Breaker\n4. Enter on LQ grab through breaker',
     'exit_criteria':'1. TP: Recent swing\n2. Trail at structure break',
     'risk_rules':'1. SL beyond breaker\n2. 1% risk\n3. Don\'t trade in ranging market',
     'checklist':'HTF MSS identified\nBreaker drawn\nLQ grab occurred\nTrend aligned\nR:R >= 1:3'},
]

# ─── NEW MODELS ─────────────────────────────────────────

class BacktestRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    strategy_name = db.Column(db.String(100), nullable=False)
    strategy_variant = db.Column(db.String(50), default='Standard')
    symbol = db.Column(db.String(20), nullable=False)
    asset_class = db.Column(db.String(30))
    timeframe = db.Column(db.String(10))
    date_from = db.Column(db.Date)
    date_to = db.Column(db.Date)
    parameters = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    total_trades = db.Column(db.Integer, default=0)
    win_rate = db.Column(db.Float)
    profit_factor = db.Column(db.Float)
    avg_r = db.Column(db.Float)
    total_pnl = db.Column(db.Float)
    max_drawdown_pct = db.Column(db.Float)
    max_drawdown_dollar = db.Column(db.Float)
    sharpe = db.Column(db.Float)
    sortino = db.Column(db.Float)
    expectancy = db.Column(db.Float)
    recovery_factor = db.Column(db.Float)
    calmar = db.Column(db.Float)
    monte_carlo_p95 = db.Column(db.Float)
    monte_carlo_p05 = db.Column(db.Float)
    monte_carlo_profit_prob = db.Column(db.Float)
    equity_curve = db.Column(db.Text)
    drawdown_series = db.Column(db.Text)
    monthly_returns = db.Column(db.Text)
    regime_analysis = db.Column(db.Text)
    wisdom_score = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BacktestTrade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('backtest_run.id'), nullable=False)
    entry_date = db.Column(db.DateTime)
    exit_date = db.Column(db.DateTime)
    direction = db.Column(db.String(10))
    entry_price = db.Column(db.Float)
    exit_price = db.Column(db.Float)
    quantity = db.Column(db.Float)
    pnl = db.Column(db.Float)
    r_multiple = db.Column(db.Float)
    result = db.Column(db.String(10))
    entry_reason = db.Column(db.String(200))
    exit_reason = db.Column(db.String(200))

class ReplayCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trade_id = db.Column(db.Integer, db.ForeignKey('trade.id'), nullable=False)
    candles_before = db.Column(db.Integer, default=20)
    candles_after = db.Column(db.Integer, default=20)
    candle_data = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OracleInsight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    insight_type = db.Column(db.String(30))
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    score = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SyncLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    source = db.Column(db.String(20))
    event = db.Column(db.String(50))
    trade_id = db.Column(db.Integer, db.ForeignKey('trade.id'), nullable=True)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PropFirmChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    firm_name = db.Column(db.String(100))
    account_size = db.Column(db.Float, default=100000)
    max_daily_loss = db.Column(db.Float, default=5000)
    max_drawdown = db.Column(db.Float, default=10000)
    profit_target = db.Column(db.Float, default=10000)
    phase = db.Column(db.String(30), default='Phase 1')
    status = db.Column(db.String(20), default='active')
    start_balance = db.Column(db.Float, default=100000)
    current_balance = db.Column(db.Float, default=100000)
    peak_balance = db.Column(db.Float, default=100000)
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    daily_pnl = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TradeRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trade_id = db.Column(db.Integer, db.ForeignKey('trade.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer)
    entry_score = db.Column(db.Integer, default=3)
    exit_score = db.Column(db.Integer, default=3)
    risk_score = db.Column(db.Integer, default=3)
    discipline_score = db.Column(db.Integer, default=3)
    emotion_score = db.Column(db.Integer, default=3)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CommunityInsight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trade_id = db.Column(db.Integer, db.ForeignKey('trade.id'), nullable=True)
    insight_type = db.Column(db.String(30))
    strategy = db.Column(db.String(100))
    symbol = db.Column(db.String(20))
    direction = db.Column(db.String(10))
    r_multiple = db.Column(db.Float)
    result = db.Column(db.String(10))
    note = db.Column(db.Text)
    anonymous = db.Column(db.Boolean, default=True)
    upvotes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── AUTH ───────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username taken.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        elif len(password) < 4:
            flash('Password must be at least 4 characters.', 'error')
        else:
            user = User(username=username, email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        user = current_user
        user.daily_goal = float(request.form.get('daily_goal', 0))
        user.weekly_goal = float(request.form.get('weekly_goal', 0))
        user.monthly_goal = float(request.form.get('monthly_goal', 0))
        if request.form.get('starting_balance'):
            user.starting_balance = float(request.form['starting_balance'])
        db.session.commit()
        flash('Settings saved!', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')

# ─── ROUTES ──────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    q = Trade.query.filter_by(user_id=current_user.id)
    total = q.count()
    wins = q.filter_by(result='WIN').count()
    losses = q.filter_by(result='LOSS').count()
    open_trades = q.filter_by(result='OPEN').count()
    wr = round((wins / (wins + losses) * 100), 1) if (wins + losses) > 0 else 0
    total_pnl = db.session.query(func.sum(Trade.pnl)).filter_by(user_id=current_user.id).scalar() or 0
    total_fees = db.session.query(func.sum(Trade.fees)).filter_by(user_id=current_user.id).scalar() or 0
    net_pnl = (total_pnl or 0) - (total_fees or 0)

    # Avg win / loss
    avg_win = db.session.query(func.avg(Trade.pnl)).filter_by(user_id=current_user.id, result='WIN').scalar() or 0
    avg_loss = db.session.query(func.avg(Trade.pnl)).filter_by(user_id=current_user.id, result='LOSS').scalar() or 0

    # Profit factor
    gross_win = db.session.query(func.sum(Trade.pnl)).filter_by(user_id=current_user.id, result='WIN').scalar() or 0
    gross_loss = abs(db.session.query(func.sum(Trade.pnl)).filter_by(user_id=current_user.id, result='LOSS').scalar() or 0)
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0

    # Best / worst
    best = q.filter_by(result='WIN').order_by(Trade.pnl.desc()).first()
    worst = q.filter_by(result='LOSS').order_by(Trade.pnl.asc()).first()

    # Today
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_pnl = db.session.query(func.sum(Trade.pnl)).filter(
        Trade.user_id == current_user.id,
        Trade.entry_date >= today_start
    ).scalar() or 0

    # This week
    week_start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), datetime.min.time())
    week_pnl = db.session.query(func.sum(Trade.pnl)).filter(
        Trade.user_id == current_user.id,
        Trade.entry_date >= week_start
    ).scalar() or 0

    # This month
    month_start = datetime(date.today().year, date.today().month, 1)
    month_pnl = db.session.query(func.sum(Trade.pnl)).filter(
        Trade.user_id == current_user.id,
        Trade.entry_date >= month_start
    ).scalar() or 0

    # Recent trades
    recent = q.order_by(Trade.entry_date.desc()).limit(10).all()

    # P&L curve data (daily aggregated)
    daily_pnl = db.session.query(
        func.date(Trade.exit_date).label('day'),
        func.sum(Trade.pnl)
    ).filter(
        Trade.user_id == current_user.id,
        Trade.result.in_(['WIN', 'LOSS']),
        Trade.exit_date != None
    ).group_by(func.date(Trade.exit_date)).order_by('day').all()

    equity_dates = []
    equity_values = []
    running = 0
    for d, p in daily_pnl:
        running += (p or 0)
        equity_dates.append(d)
        equity_values.append(round(running, 2))

    # Setup breakdown
    setups = db.session.query(Trade.setup_type, func.count(Trade.id)).filter(
        Trade.user_id == current_user.id,
        Trade.setup_type != None
    ).group_by(Trade.setup_type).order_by(func.count(Trade.id).desc()).all()

    # ─── EDGE SCORE ──────────────────────────────────────
    closed = Trade.query.filter_by(user_id=current_user.id).filter(Trade.result.in_(['WIN', 'LOSS'])).all()
    avg_r = 0
    r_vals = [t.r_multiple for t in closed if t.r_multiple]
    if r_vals:
        avg_r = sum(r_vals) / len(r_vals)

    total_pnl_vals = [t.pnl for t in closed if t.pnl is not None]
    if total_pnl_vals and len(total_pnl_vals) > 1:
        avg_daily = sum(total_pnl_vals) / len(total_pnl_vals)
        var_daily = sum((p - avg_daily)**2 for p in total_pnl_vals) / len(total_pnl_vals)
        daily_std = var_daily ** 0.5 or 1
        sharpe = round((avg_daily / daily_std) * (252 ** 0.5), 2) if avg_daily > 0 else 0
    else:
        sharpe = 0

    # Sub-scores (each 0-100)
    pf_score = min(100, profit_factor / 3 * 100) if profit_factor > 0 else 0
    wr_score = wr
    r_score = min(100, avg_r / 3 * 100) if avg_r > 0 else 0
    sharpe_score = min(100, sharpe / 3 * 100) if sharpe > 0 else 0
    stability_score = 50  # neutral default
    if total_pnl_vals and len(total_pnl_vals) > 1:
        neg_count = sum(1 for p in total_pnl_vals if p < 0)
        neg_ratio = neg_count / len(total_pnl_vals)
        stability_score = max(0, 100 - (neg_ratio * 100))

    edge_score = round(
        pf_score * 0.30 +
        wr_score * 0.25 +
        r_score * 0.20 +
        sharpe_score * 0.15 +
        stability_score * 0.10
    )

    return render_template('dashboard.html',
        total=total, wins=wins, losses=losses, open_trades=open_trades,
        win_rate=wr, total_pnl=round(net_pnl, 2), avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2), profit_factor=profit_factor,
        best=best, worst=worst,
        today_pnl=round(today_pnl, 2), week_pnl=round(week_pnl, 2),
        month_pnl=round(month_pnl, 2),
        equity_dates=equity_dates, equity_values=equity_values,
        recent=recent, setups=setups,
        daily_goal=current_user.daily_goal, weekly_goal=current_user.weekly_goal,
        monthly_goal=current_user.monthly_goal,
        edge_score=edge_score, avg_r=round(avg_r, 2), sharpe=sharpe,
        pf_score=round(pf_score), wr_score=round(wr_score),
        r_score=round(r_score), sharpe_score=round(sharpe_score),
        stability_score=round(stability_score))

@app.route('/trades')
@login_required
def trades():
    q = Trade.query.filter_by(user_id=current_user.id)
    symbol = request.args.get('symbol', '')
    setup = request.args.get('setup', '')
    result = request.args.get('result', '')
    sort = request.args.get('sort', 'date_desc')

    if symbol: q = q.filter(Trade.symbol.ilike(f'%{symbol}%'))
    if setup: q = q.filter_by(setup_type=setup)
    if result: q = q.filter_by(result=result)

    if sort == 'date_asc': q = q.order_by(Trade.entry_date.asc())
    elif sort == 'pnl_desc': q = q.order_by(Trade.pnl.desc().nullslast())
    elif sort == 'pnl_asc': q = q.order_by(Trade.pnl.asc().nullslast())
    else: q = q.order_by(Trade.entry_date.desc())

    trade_list = q.all()
    symbols = db.session.query(Trade.symbol).filter_by(user_id=current_user.id).distinct().all()
    return render_template('trades.html', trades=trade_list, symbols=[s[0] for s in symbols],
                          active_symbol=symbol, active_setup=setup, active_result=result)

# ─── TRADE CRUD ─────────────────────────────────────────

def calc_pnl(direction, entry, exit_val, qty, fees=0):
    if direction == 'LONG':
        raw = (exit_val - entry) * qty
    else:
        raw = (entry - exit_val) * qty
    return round(raw - fees, 2)

def calc_pnl_pct(entry, exit_val, direction):
    if entry == 0: return 0
    if direction == 'LONG':
        return round((exit_val - entry) / entry * 100, 2)
    return round((entry - exit_val) / entry * 100, 2)

@app.route('/trade/add', methods=['GET', 'POST'])
@login_required
def add_trade():
    if request.method == 'POST':
        entry = float(request.form['entry_price'])
        exit_price = request.form.get('exit_price')
        sl = float(request.form['stop_loss']) if request.form.get('stop_loss') else None
        tp = float(request.form['take_profit']) if request.form.get('take_profit') else None
        qty = float(request.form.get('quantity', 1))
        fees = float(request.form.get('fees', 0))
        direction = request.form['direction']
        symbol = request.form['symbol'].upper()

        entry_dt = datetime.utcnow()
        exit_dt = None
        pnl = None
        pnl_pct = None
        result = 'OPEN'
        exit_val = None
        dur = None

        if exit_price:
            exit_val = float(exit_price)
            exit_dt = entry_dt
            pnl = calc_pnl(direction, entry, exit_val, qty, fees)
            pnl_pct = calc_pnl_pct(entry, exit_val, direction)
            result = 'WIN' if pnl > 0 else 'LOSS'
            dur = 0

        # R multiple
        r = None
        if sl and exit_val:
            risk_per_unit = abs(entry - sl)
            if risk_per_unit > 0:
                if direction == 'LONG':
                    r = round((exit_val - entry) / risk_per_unit, 2)
                else:
                    r = round((entry - exit_val) / risk_per_unit, 2)

        trade = Trade(
            user_id=current_user.id, symbol=symbol, direction=direction,
            entry_price=entry, exit_price=exit_val,
            stop_loss=sl, take_profit=tp, quantity=qty, fees=fees,
            pnl=pnl, pnl_pct=pnl_pct, result=result,
            setup_type=request.form.get('setup_type'),
            session=request.form.get('session'),
            tags=request.form.get('tags'),
            emotion=request.form.get('emotion'),
            notes=request.form.get('notes'),
            entry_date=entry_dt, exit_date=exit_dt,
            duration_minutes=dur, r_multiple=r,
        )
        db.session.add(trade)
        db.session.commit()
        flash('Trade saved!', 'success')
        return redirect(url_for('trades'))
    setup_type = request.args.get('setup', '')
    return render_template('add_trade.html', trade=None, setup_type=setup_type)

@app.route('/trade/edit/<int:trade_id>', methods=['GET', 'POST'])
@login_required
def edit_trade(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id != current_user.id:
        return redirect(url_for('trades'))
    if request.method == 'POST':
        trade.symbol = request.form['symbol'].upper()
        trade.direction = request.form['direction']
        trade.entry_price = float(request.form['entry_price'])
        trade.stop_loss = float(request.form['stop_loss']) if request.form.get('stop_loss') else None
        trade.take_profit = float(request.form['take_profit']) if request.form.get('take_profit') else None
        trade.quantity = float(request.form.get('quantity', 1))
        trade.fees = float(request.form.get('fees', 0))
        trade.setup_type = request.form.get('setup_type')
        trade.session = request.form.get('session')
        trade.tags = request.form.get('tags')
        trade.emotion = request.form.get('emotion')
        trade.notes = request.form.get('notes')

        if request.form.get('exit_price'):
            trade.exit_price = float(request.form['exit_price'])
            trade.exit_date = datetime.utcnow()
            trade.pnl = calc_pnl(trade.direction, trade.entry_price, trade.exit_price, trade.quantity, trade.fees)
            trade.pnl_pct = calc_pnl_pct(trade.entry_price, trade.exit_price, trade.direction)
            trade.result = 'WIN' if trade.pnl > 0 else 'LOSS'
            if trade.stop_loss and trade.stop_loss > 0:
                risk = abs(trade.entry_price - trade.stop_loss)
                trade.r_multiple = round((trade.exit_price - trade.entry_price) / risk, 2) if risk > 0 else 0
            trade.duration_minutes = 0
        else:
            trade.exit_price = None
            trade.exit_date = None
            trade.pnl = None
            trade.pnl_pct = None
            trade.result = 'OPEN'
            trade.r_multiple = None
            trade.duration_minutes = None

        db.session.commit()
        flash('Trade updated!', 'success')
        return redirect(url_for('trades'))
    return render_template('add_trade.html', trade=trade)

@app.route('/trade/delete/<int:trade_id>', methods=['POST'])
@login_required
def delete_trade(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id == current_user.id:
        db.session.delete(trade)
        db.session.commit()
    return redirect(url_for('trades'))

@app.route('/settings/delete-all', methods=['POST'])
@login_required
def delete_all_trades():
    Trade.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash('All trades deleted.', 'success')
    return redirect(url_for('trades'))

@app.route('/trade/close', methods=['POST'])
@login_required
def close_trade():
    data = request.get_json()
    trade = Trade.query.get_or_404(data['trade_id'])
    if trade.user_id != current_user.id:
        return jsonify({'error': 'unauthorized'}), 403
    exit_price = float(data['exit_price'])
    now = datetime.utcnow()
    if trade.entry_date:
        dur = int((now - trade.entry_date).total_seconds() / 60)
    else:
        dur = 0
    trade.exit_price = exit_price
    trade.exit_date = now
    trade.pnl = calc_pnl(trade.direction, trade.entry_price, exit_price, trade.quantity, trade.fees)
    trade.pnl_pct = calc_pnl_pct(trade.entry_price, exit_price, trade.direction)
    trade.result = 'WIN' if trade.pnl > 0 else 'LOSS'
    trade.duration_minutes = dur
    if trade.stop_loss and trade.stop_loss > 0:
        risk = abs(trade.entry_price - trade.stop_loss)
        trade.r_multiple = round((exit_price - trade.entry_price) / risk, 2) if risk > 0 else 0
    db.session.commit()
    return jsonify(trade.to_dict())

# ─── ANALYTICS ────────────────────────────────────────────

@app.route('/analytics')
@login_required
def analytics():
    trades = Trade.query.filter_by(user_id=current_user.id).filter(Trade.result.in_(['WIN', 'LOSS'])).all()
    total = len(trades)
    wins_t = sum(1 for t in trades if t.result == 'WIN')
    losses_t = total - wins_t
    win_rate = round((wins_t / total * 100), 1) if total > 0 else 0
    avg_win = round(sum(t.pnl for t in trades if t.result == 'WIN') / wins_t, 2) if wins_t > 0 else 0
    avg_loss = round(sum(t.pnl for t in trades if t.result == 'LOSS') / losses_t, 2) if losses_t > 0 else 0
    gross_win = sum(t.pnl for t in trades if t.result == 'WIN') or 0
    gross_loss = abs(sum(t.pnl for t in trades if t.result == 'LOSS') or 0)
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0

    best_trade = max((t.pnl for t in trades if t.pnl), default=0)
    worst_trade = min((t.pnl for t in trades if t.pnl), default=0)
    avg_r = round(sum(t.r_multiple for t in trades if t.r_multiple) / sum(1 for t in trades if t.r_multiple), 2) if any(t.r_multiple for t in trades) else 0
    expectancy = round((win_rate/100 * avg_win) - ((1-win_rate/100) * abs(avg_loss)), 2) if total > 0 else 0

    # Day of week
    dow_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    dow_data = {}
    for t in trades:
        if t.exit_date:
            day = t.exit_date.strftime('%A')
            if day not in dow_data: dow_data[day] = {'wins': 0, 'losses': 0, 'net': 0}
            dow_data[day]['net'] += (t.pnl or 0)
            if t.result == 'WIN': dow_data[day]['wins'] += 1
            else: dow_data[day]['losses'] += 1
    by_dow = [{'day': d, 'wins': dow_data.get(d, {}).get('wins',0), 'losses': dow_data.get(d, {}).get('losses',0), 'net': dow_data.get(d, {}).get('net',0)} for d in dow_names if d in dow_data]

    # Session breakdown
    sess_data = {}
    for t in trades:
        s = t.session or 'Other'
        if s not in sess_data: sess_data[s] = {'wins': 0, 'losses': 0, 'net': 0}
        sess_data[s]['net'] += (t.pnl or 0)
        if t.result == 'WIN': sess_data[s]['wins'] += 1
        else: sess_data[s]['losses'] += 1
    by_session = [{'session': s, 'wins': v['wins'], 'losses': v['losses'], 'net': v['net']} for s,v in sorted(sess_data.items(), key=lambda x: x[1]['net'], reverse=True)]

    # Setup breakdown
    setup_data = {}
    for t in trades:
        s = t.setup_type or 'Other'
        if s not in setup_data: setup_data[s] = {'wins': 0, 'losses': 0, 'net': 0}
        setup_data[s]['net'] += (t.pnl or 0)
        if t.result == 'WIN': setup_data[s]['wins'] += 1
        else: setup_data[s]['losses'] += 1
    by_setup = [{'setup_type': s, 'wins': v['wins'], 'losses': v['losses'], 'net': v['net']} for s,v in sorted(setup_data.items(), key=lambda x: x[1]['net'], reverse=True)]

    # Direction breakdown
    dir_data = {}
    for t in trades:
        d = t.direction
        if d not in dir_data: dir_data[d] = {'wins': 0, 'losses': 0, 'net': 0}
        dir_data[d]['net'] += (t.pnl or 0)
        if t.result == 'WIN': dir_data[d]['wins'] += 1
        else: dir_data[d]['losses'] += 1
    by_dir = [{'direction': d, 'wins': v['wins'], 'losses': v['losses'], 'net': v['net']} for d,v in dir_data.items()]

    # P&L distribution buckets
    pnls = [t.pnl for t in trades if t.pnl is not None]
    if pnls:
        lo, hi = min(pnls), max(pnls)
        if lo < hi:
            step = (hi - lo) / 6 or 1
            buckets = {}
            for i in range(7):
                b_lo = round(lo + step * i, 0)
                buckets[f'${b_lo:.0f}'] = sum(1 for p in pnls if lo + step * i <= p < lo + step * (i + 1))
            dist_labels = list(buckets.keys())
            dist_values = list(buckets.values())
        else:
            dist_labels = [f'${lo:.0f}']
            dist_values = [len(pnls)]
    else:
        dist_labels = []
        dist_values = []

    # Consecutive win/loss streaks
    ordered = Trade.query.filter_by(user_id=current_user.id).filter(Trade.result.in_(['WIN', 'LOSS'])).order_by(Trade.exit_date.asc()).all()
    cs_win = cs_loss = mx_win = mx_loss = 0
    for t in ordered:
        if t.result == 'WIN':
            cs_win += 1; cs_loss = 0
            mx_win = max(mx_win, cs_win)
        elif t.result == 'LOSS':
            cs_loss += 1; cs_win = 0
            mx_loss = max(mx_loss, cs_loss)
    consecutive = {'win_streak': mx_win, 'loss_streak': mx_loss}

    # Monthly returns / sharpe (simple)
    monthly_pnls = {}
    for t in trades:
        if t.exit_date:
            mk = t.exit_date.strftime('%Y-%m')
            monthly_pnls.setdefault(mk, []).append(t.pnl or 0)
    monthly_returns = None
    if len(monthly_pnls) >= 1:
        mrets = [sum(v) for v in monthly_pnls.values()]
        avg_mret = sum(mrets) / len(mrets)
        var_mret = sum((r - avg_mret)**2 for r in mrets) / len(mrets)
        vol = (var_mret ** 0.5) or 1
        monthly_returns = {
            'monthly_return': round(avg_mret / (current_user.starting_balance or 10000) * 100, 2),
            'volatility': round(vol, 2),
            'sharpe': round(avg_mret / vol, 2) if vol > 0 else 0,
        }

    return render_template('analytics.html',
        total=total, wins=wins_t, losses=losses_t, win_rate=win_rate,
        profit_factor=profit_factor, avg_win=avg_win, avg_loss=avg_loss,
        best_trade=best_trade, worst_trade=worst_trade,
        avg_r=avg_r, expectancy=expectancy,
        by_session=by_session, by_setup=by_setup, by_dow=by_dow, by_dir=by_dir,
        dist_labels=dist_labels, dist_values=dist_values,
        consecutive=consecutive, monthly_returns=monthly_returns,
        sess_labels=[(r['session'] or 'Unspecified') for r in by_session],
        setup_labels=[(r['setup_type'] or 'Unspecified') for r in by_setup],
        dow_labels=[r['day'] for r in by_dow],
        dir_labels=[r['direction'] for r in by_dir],
        sess_wins=[r['wins'] for r in by_session],
        sess_losses=[abs(r['losses']) for r in by_session],
        setup_wins=[r['wins'] for r in by_setup],
        setup_losses=[abs(r['losses']) for r in by_setup],
        dow_wins=[r['wins'] for r in by_dow],
        dow_losses=[abs(r['losses']) for r in by_dow],
        dir_nets=[r['net'] for r in by_dir])

# ─── CSV IMPORT ──────────────────────────────────────────

CSV_MAPPINGS = {
    'oanda': {
        'labels': ['Date/Time', 'Symbol', 'Type', 'Direction', 'Units', 'Price', 'SL', 'TP', 'PL'],
        'date_col': 0, 'sym_col': 1, 'dir_col': 3, 'entry_col': 5, 'sl_col': 6, 'tp_col': 7, 'pnl_col': 8, 'qty_col': 4,
        'date_fmt': '%Y-%m-%d %H:%M:%S',
    },
    'zerodha': {
        'labels': ['date', 'symbol', 'type', 'quantity', 'entry', 'exit', 'pnl'],
        'date_col': 0, 'sym_col': 1, 'dir_col': 2, 'entry_col': 4, 'exit_col': 5, 'pnl_col': 6, 'qty_col': 3,
        'date_fmt': '%Y-%m-%d',
    },
}

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_trades():
    if request.method == 'POST':
        broker = request.form.get('broker')
        file = request.files.get('file')
        if not file or not broker:
            flash('Select a broker and file.', 'error')
            return render_template('import.html', brokers=CSV_MAPPINGS.keys())

        mapping = CSV_MAPPINGS.get(broker)
        if not mapping:
            flash('Unknown broker.', 'error')
            return render_template('import.html', brokers=CSV_MAPPINGS.keys())

        try:
            text = file.read().decode('utf-8')
            reader = csv.reader(io.StringIO(text))
            next(reader)
            imported = 0
            skipped = 0
            errors = []
            for i, row in enumerate(reader):
                if len(row) < 5:
                    skipped += 1
                    continue
                try:
                    sym = row[mapping['sym_col']].strip().upper()
                    direction = row[mapping['dir_col']].strip().upper()[:4]
                    if direction not in ('LONG', 'SHORT', 'BUY', 'SELL'):
                        direction = 'LONG' if ('BUY' in direction or 'LONG' in direction) else 'SHORT'

                    entry = float(row[mapping['entry_col']])
                    qty = abs(float(row[mapping['qty_col']]))
                    pnl = float(row[mapping.get('pnl_col', -1)]) if mapping.get('pnl_col', -1) >= 0 and len(row) > mapping.get('pnl_col', -1) else 0
                    exit_price = None
                    if 'exit_col' in mapping and len(row) > mapping['exit_col']:
                        exit_price = float(row[mapping['exit_col']]) if row[mapping['exit_col']] else None

                    if not exit_price and qty > 0:
                        exit_price = (entry + (pnl / qty)) if direction in ('BUY', 'LONG') else (entry - (pnl / qty))

                    result = 'WIN' if pnl > 0 else 'LOSS'
                    entry_dt = datetime.strptime(row[mapping['date_col']][:19], mapping['date_fmt']) if len(row) > mapping['date_col'] else datetime.utcnow()

                    trade = Trade(
                        user_id=current_user.id, symbol=sym,
                        direction='LONG' if direction in ('BUY', 'LONG') else 'SHORT',
                        entry_price=entry, exit_price=exit_price, quantity=qty,
                        pnl=pnl, result=result,
                        entry_date=entry_dt, exit_date=entry_dt,
                    )
                    db.session.add(trade)
                    imported += 1
                except Exception as ex:
                    errors.append(f'Row {i+2}: {str(ex)}')
            db.session.commit()
            results = {'imported': imported, 'skipped': skipped, 'errors': errors}
            flash(f'Imported {imported} trades from {broker}!', 'success')
            return render_template('import.html', results=results)
        except Exception as e:
            flash(f'Error reading file: {str(e)}', 'error')
        return redirect(url_for('import_trades'))
    return render_template('import.html', results=None)

# ─── CALENDAR ────────────────────────────────────────────

@app.route('/calendar')
@login_required
def calendar():
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)
    # Get all days with trade data for this month
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    days_data = db.session.query(
        func.date(Trade.exit_date).label('day'),
        func.sum(Trade.pnl).label('pnl'),
        func.count(Trade.id).label('count'),
    ).filter(
        Trade.user_id == current_user.id,
        Trade.exit_date >= start,
        Trade.exit_date < end,
        Trade.result.in_(['WIN', 'LOSS']),
    ).group_by(func.date(Trade.exit_date)).all()

    # Get win/loss counts per day separately
    win_data = db.session.query(func.date(Trade.exit_date).label('day'), func.count(Trade.id).label('wins')).filter(Trade.user_id == current_user.id, Trade.exit_date >= start, Trade.exit_date < end, Trade.result == 'WIN').group_by(func.date(Trade.exit_date)).all()
    loss_data = db.session.query(func.date(Trade.exit_date).label('day'), func.count(Trade.id).label('losses')).filter(Trade.user_id == current_user.id, Trade.exit_date >= start, Trade.exit_date < end, Trade.result == 'LOSS').group_by(func.date(Trade.exit_date)).all()
    def get_day(d):
        if isinstance(d, str): return d.split('-')[-1]
        return str(d.day)
    win_map = {get_day(d): w for d, w in win_data}
    loss_map = {get_day(d): l for d, l in loss_data}
    day_map = {get_day(d): {'pnl': round(float(p) if p else 0, 2), 'count': c, 'wins': win_map.get(get_day(d), 0), 'losses': loss_map.get(get_day(d), 0)} for d, p, c in days_data}

    # Journal entries for this month
    entries = JournalEntry.query.filter_by(user_id=current_user.id).filter(
        JournalEntry.date >= start, JournalEntry.date < end
    ).order_by(JournalEntry.date.desc()).all()
    entry_map = {}
    for e in entries:
        ds = str(e.date.day)
        if ds not in entry_map:
            entry_map[ds] = []
        entry_map[ds].append({'title': e.title or e.type, 'type': e.type, 'id': e.id})

    # Navigation
    prev_m = 12 if month == 1 else month - 1
    prev_y = year - 1 if month == 1 else year
    next_m = 1 if month == 12 else month + 1
    next_y = year + 1 if month == 12 else year

    # Calendar grid
    import calendar as cal_mod
    cal = cal_mod.TextCalendar()
    month_days = []
    for week in cal.monthdayscalendar(year, month):
        row = []
        for d in week:
            if d == 0:
                row.append(None)
            else:
                ds = str(d)
                row.append({
                    'day': d,
                    'data': day_map.get(ds),
                    'entries': entry_map.get(ds, []),
                })
        month_days.append(row)

    # Weekday headers
    month_name = date(year, month, 1).strftime('%B %Y')

    # Monthly stats
    monthly_pnl = sum(float(p) if p else 0 for _, p, _, _, _ in days_data) if days_data else 0
    monthly_trades = sum(int(c) for _, _, c, _, _ in days_data)
    monthly_wins = sum(int(w) for _, _, _, w, _ in days_data)
    monthly_wr = round(monthly_wins / monthly_trades * 100, 1) if monthly_trades > 0 else 0
    trading_days = sum(1 for _, p, _, _, _ in days_data)
    avg_day = round(monthly_pnl / trading_days, 2) if trading_days > 0 else 0

    # YTD
    ytd_start = date(year, 1, 1)
    ytd_pnl = db.session.query(func.sum(Trade.pnl)).filter(
        Trade.user_id == current_user.id,
        Trade.exit_date >= ytd_start,
        Trade.exit_date < end,
        Trade.result.in_(['WIN', 'LOSS']),
    ).scalar() or 0

    # Edge Score for the month
    closed_this_month = Trade.query.filter_by(user_id=current_user.id).filter(
        Trade.exit_date >= start, Trade.exit_date < end,
        Trade.result.in_(['WIN', 'LOSS']),
    ).all()
    r_vals_m = [t.r_multiple for t in closed_this_month if t.r_multiple]
    avg_r_m = round(sum(r_vals_m) / len(r_vals_m), 2) if r_vals_m else 0

    return render_template('calendar.html',
        month_days=month_days, month_name=month_name,
        prev_m=prev_m, prev_y=prev_y, next_m=next_m, next_y=next_y,
        year=year, month=month,
        monthly_pnl=round(monthly_pnl, 2), monthly_trades=monthly_trades,
        monthly_wins=monthly_wins, monthly_wr=monthly_wr,
        trading_days=trading_days, avg_day=avg_day,
        ytd_pnl=round(ytd_pnl, 2), avg_r_m=avg_r_m,
    )

# ─── NOTEBOOK ────────────────────────────────────────────

@app.route('/notebook')
@login_required
def notebook():
    entries = JournalEntry.query.filter_by(user_id=current_user.id).order_by(JournalEntry.date.desc()).all()
    return render_template('notebook.html', entries=entries)

@app.route('/notebook/new', methods=['GET', 'POST'])
@login_required
def notebook_new():
    if request.method == 'POST':
        entry = JournalEntry(
            user_id=current_user.id,
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date() if request.form.get('date') else date.today(),
            title=request.form.get('title'),
            type=request.form.get('type', 'note'),
            content=request.form.get('content'),
            mood=request.form.get('mood'),
        )
        db.session.add(entry)
        db.session.commit()
        flash('Entry saved!', 'success')
        return redirect(url_for('notebook'))
    return render_template('notebook_edit.html', entry=None, today=date.today().isoformat())

@app.route('/notebook/edit/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def notebook_edit(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return redirect(url_for('notebook'))
    if request.method == 'POST':
        entry.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        entry.title = request.form.get('title')
        entry.type = request.form.get('type', 'note')
        entry.content = request.form.get('content')
        entry.mood = request.form.get('mood')
        db.session.commit()
        flash('Entry updated!', 'success')
        return redirect(url_for('notebook'))
    return render_template('notebook_edit.html', entry=entry, today=entry.date.isoformat())

@app.route('/notebook/delete/<int:entry_id>', methods=['POST'])
@login_required
def notebook_delete(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.user_id == current_user.id:
        db.session.delete(entry)
        db.session.commit()
    return redirect(url_for('notebook'))

# ─── STRATEGY TEMPLATES ──────────────────────────────────

@app.route('/strategies')
@login_required
def strategies():
    custom = StrategyTemplate.query.filter_by(user_id=current_user.id).order_by(StrategyTemplate.name).all()
    return render_template('strategies.html', templates=ICTTEMPLATES, custom=custom)

@app.route('/strategies/apply', methods=['GET', 'POST'])
@login_required
def strategy_apply():
    name = request.args.get('name', '')
    template = next((t for t in ICTTEMPLATES if t['name'] == name), None)
    if not template:
        flash('Strategy not found.', 'error')
        return redirect(url_for('strategies'))

    if request.method == 'POST':
        tactic = request.form.get('tactic', '')
        checklist_results = request.form.get('checklist_results', '')

        # Check existing trades or just return to strategies with a flash
        flash(f'Applied "{template["name"]}" to your trading plan. Follow the checklist!', 'success')
        return redirect(url_for('strategies'))

    return render_template('strategy_detail.html', template=template)

@app.route('/api/trade/<int:trade_id>/strategy', methods=['POST'])
@login_required
def tag_trade_strategy(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id != current_user.id:
        return jsonify({'error': 'unauthorized'}), 403
    data = request.get_json()
    trade.setup_type = data.get('strategy', trade.setup_type)
    db.session.commit()
    return jsonify({'ok': True})

# ─── MT5 SYNC API ─────────────────────────────────────

@app.route('/api/sync/trade', methods=['POST'])
def sync_trade():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    user = User.query.filter_by(id=data.get('user_id', 0)).first()
    if not user:
        return jsonify({'error': 'invalid user'}), 401
    symbol = data.get('symbol', '').upper()
    direction = data.get('direction', 'LONG')
    entry = float(data.get('entry_price', 0))
    exit_price = float(data.get('exit_price', 0))
    qty = float(data.get('volume', 0.1))
    pnl = (exit_price - entry) * qty if direction == 'LONG' else (entry - exit_price) * qty
    pnl -= float(data.get('commission', 0))
    result = 'WIN' if pnl > 0 else 'LOSS'
    entry_time = datetime.fromisoformat(data['entry_time'].replace('Z','+00:00')) if 'entry_time' in data else datetime.utcnow()
    exit_time = datetime.fromisoformat(data['exit_time'].replace('Z','+00:00')) if 'exit_time' in data else datetime.utcnow()
    setup = data.get('setup_type', '')
    notes = data.get('comment', '')
    trade = Trade(user_id=user.id, symbol=symbol, direction=direction, entry_price=entry, exit_price=exit_price, quantity=qty, fees=float(data.get('commission',0)), pnl=round(pnl,2), result=result, setup_type=setup, session=data.get('ict_snapshot',{}).get('session','') if isinstance(data.get('ict_snapshot'),dict) else '', notes=notes, entry_date=entry_time, exit_date=exit_time)
    db.session.add(trade)
    db.session.flush()
    db.session.add(SyncLog(user_id=user.id, source='mt5', event='trade_synced', trade_id=trade.id, details=json.dumps(data)))
    db.session.commit()
    return jsonify({'status': 'ok', 'trade_id': trade.id})

@app.route('/api/sync/positions', methods=['POST'])
@login_required
def sync_positions():
    data = request.get_json() or {}
    for pos in data.get('positions', []):
        db.session.add(SyncLog(user_id=current_user.id, source='mt5', event='position_update', details=json.dumps(pos)))
    db.session.commit()
    return jsonify({'status': 'ok', 'count': len(data.get('positions', []))})

# ─── BACKTESTING ──────────────────────────────────────

@app.route('/backtest/new', methods=['GET', 'POST'])
@login_required
def backtest_new():
    symbols = sorted(set([s[0] for s in Trade.query.filter_by(user_id=current_user.id).with_entities(Trade.symbol).distinct().all()] + ['XAUUSD','XAGUSD','EURUSD','GBPUSD','BTCUSD','ETHUSD','AAPL','TSLA','SPY','QQQ','US30','NAS100']))
    prefill = request.args.get('strategy', '')
    if request.method == 'POST':
        run = BacktestRun(user_id=current_user.id, strategy_name=request.form['strategy'], symbol=request.form['symbol'].upper(), timeframe=request.form['timeframe'], date_from=datetime.strptime(request.form['date_from'],'%Y-%m-%d').date(), date_to=datetime.strptime(request.form['date_to'],'%Y-%m-%d').date(), parameters=json.dumps({'size_mode':request.form.get('size_mode','fixed'),'size_value':float(request.form.get('size_value',0.1)),'commission':float(request.form.get('commission',0)),'slippage':float(request.form.get('slippage',0.5))}), status='pending')
        db.session.add(run)
        db.session.commit()
        return redirect(url_for('backtest_run', run_id=run.id))
    return render_template('strategy_backtest.html', symbols=symbols, templates=ICTTEMPLATES, prefill=prefill)

@app.route('/backtest/run/<int:run_id>')
@login_required
def backtest_run(run_id):
    run = BacktestRun.query.get_or_404(run_id)
    if run.user_id != current_user.id:
        return redirect(url_for('backtest_new'))
    return render_template('backtest_results.html', run=run)

@app.route('/api/backtest/execute/<int:run_id>', methods=['POST'])
@login_required
def backtest_execute(run_id):
    run = BacktestRun.query.get_or_404(run_id)
    if run.user_id != current_user.id:
        return jsonify({'error': 'unauthorized'}), 403
    run.status = 'running'
    db.session.commit()
    import backtest_engine
    def _run():
        with app.app_context():
            r = BacktestRun.query.get(run_id)
            try:
                res = backtest_engine.run_simulation(r)
                r.status = 'done'
                r.total_trades = res['total_trades']
                r.win_rate = res['win_rate']
                r.profit_factor = res['profit_factor']
                r.avg_r = res['avg_r']
                r.total_pnl = res['total_pnl']
                r.max_drawdown_pct = res['max_drawdown_pct']
                r.max_drawdown_dollar = res['max_drawdown_dollar']
                r.sharpe = res['sharpe']
                r.sortino = res['sortino']
                r.expectancy = res['expectancy']
                r.recovery_factor = res['recovery_factor']
                r.calmar = res['calmar']
                r.equity_curve = json.dumps(res['equity_curve'])
                r.drawdown_series = json.dumps(res['drawdown_series'])
                r.monthly_returns = json.dumps(res['monthly_returns'])
                r.wisdom_score = res.get('wisdom_score', 50)
                for t in res['trades']:
                    db.session.add(BacktestTrade(run_id=run_id, **t))
                db.session.commit()
            except Exception as e:
                r.status = 'failed'
                r.win_rate = -1
                db.session.commit()
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/api/backtest/status/<int:run_id>')
@login_required
def backtest_status(run_id):
    run = BacktestRun.query.get_or_404(run_id)
    return jsonify({'status': run.status, 'win_rate': run.win_rate, 'total_trades': run.total_trades, 'profit_factor': run.profit_factor})

@app.route('/api/backtest/results/<int:run_id>')
@login_required
def backtest_results_api(run_id):
    run = BacktestRun.query.get_or_404(run_id)
    if run.user_id != current_user.id:
        return jsonify({'error': 'unauthorized'}), 403
    trades = BacktestTrade.query.filter_by(run_id=run.id).order_by(BacktestTrade.entry_date).all()
    return jsonify({
        'run': {'strategy_name':run.strategy_name,'symbol':run.symbol,'timeframe':run.timeframe,'total_trades':run.total_trades,'win_rate':run.win_rate,'profit_factor':run.profit_factor,'avg_r':run.avg_r,'total_pnl':run.total_pnl,'max_drawdown_pct':run.max_drawdown_pct,'max_drawdown_dollar':run.max_drawdown_dollar,'sharpe':run.sharpe,'sortino':run.sortino,'expectancy':run.expectancy,'recovery_factor':run.recovery_factor,'calmar':run.calmar,'equity_curve':json.loads(run.equity_curve or '[]'),'drawdown_series':json.loads(run.drawdown_series or '[]'),'wisdom_score':run.wisdom_score},
        'trades': [{'entry_date':t.entry_date.isoformat() if t.entry_date else None,'exit_date':t.exit_date.isoformat() if t.exit_date else None,'direction':t.direction,'entry_price':t.entry_price,'exit_price':t.exit_price,'pnl':t.pnl,'r_multiple':t.r_multiple,'result':t.result} for t in trades],
    })

@app.route('/trade/replay/<int:trade_id>')
@login_required
def trade_replay(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id != current_user.id:
        return redirect(url_for('trades'))
    return render_template('trade_replay.html', trade=trade)

@app.route('/api/replay/candles/<int:trade_id>')
@login_required
def replay_candles(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id != current_user.id:
        return jsonify({'error': 'unauthorized'}), 403
    cache = ReplayCache.query.filter_by(trade_id=trade_id).first()
    if cache and cache.status == 'done' and cache.candle_data:
        return jsonify({'candles': json.loads(cache.candle_data), 'trade': trade.to_dict()})
    import backtest_engine
    sym = trade.symbol
    fm = {'XAUUSD':'GC=F','XAGUSD':'SI=F','US30':'YM=F','NAS100':'NQ=F','SPX500':'ES=F','BTCUSD':'BTC-USD','ETHUSD':'ETH-USD'}
    yfsym = fm.get(sym, sym)
    df = yf.download(yfsym, start=(trade.entry_date-timedelta(days=2)).strftime('%Y-%m-%d'), end=(trade.exit_date+timedelta(days=2)).strftime('%Y-%m-%d') if trade.exit_date else (trade.entry_date+timedelta(days=1)).strftime('%Y-%m-%d'), interval='5m', progress=False)
    candles = []
    if not df.empty:
        for idx,row in df.iterrows():
            candles.append({'time':idx.to_pydatetime().isoformat(),'open':float(row['Open']),'high':float(row['High']),'low':float(row['Low']),'close':float(row['Close']),'volume':float(row['Volume'])})
    if not cache:
        cache = ReplayCache(trade_id=trade_id, candle_data=json.dumps(candles), status='done')
        db.session.add(cache)
    else:
        cache.candle_data = json.dumps(candles)
        cache.status = 'done'
    db.session.commit()
    return jsonify({'candles': candles, 'trade': trade.to_dict()})

# ─── AI ORACLE ─────────────────────────────────────────

@app.route('/oracle')
@login_required
def oracle():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()
    today_trades = [t for t in trades if t.entry_date and t.entry_date.date() == date.today()]
    week_trades = [t for t in trades if t.entry_date and (date.today()-t.entry_date.date()).days < 7]
    today_wins = len([t for t in today_trades if t.result == 'WIN'])
    today_losses = len([t for t in today_trades if t.result == 'LOSS'])
    today_pnl = sum(t.pnl or 0 for t in today_trades)
    week_wins = len([t for t in week_trades if t.result == 'WIN'])
    week_losses = len([t for t in week_trades if t.result == 'LOSS'])
    week_wr = week_wins/(week_wins+week_losses)*100 if (week_wins+week_losses)>0 else 0
    cons_losses = 0
    for t in trades[:20]:
        if t.result == 'LOSS': cons_losses += 1
        else: break
    wr = len([t for t in trades if t.result=='WIN'])/len(trades)*100 if trades else 0
    avg_r = sum(t.r_multiple or 0 for t in trades)/len(trades) if trades else 0
    total_pnl = sum(t.pnl or 0 for t in trades)
    setup_pnl = {}
    for t in trades[:50]:
        if t.setup_type: setup_pnl[t.setup_type] = setup_pnl.get(t.setup_type,0)+(t.pnl or 0)
    best_setup = max(setup_pnl, key=setup_pnl.get) if setup_pnl else None
    insights = OracleInsight.query.filter_by(user_id=current_user.id).order_by(OracleInsight.created_at.desc()).limit(10).all()
    return render_template('oracle.html', today_trades=len(today_trades), today_wins=today_wins, today_losses=today_losses, today_pnl=round(today_pnl,2), week_wr=round(week_wr,1), cons_losses=cons_losses, wr=round(wr,1), avg_r=round(avg_r,2), total_pnl=round(total_pnl,2), best_setup=best_setup, trade_count=len(trades), insights=insights)

@app.route('/api/oracle/chat', methods=['POST'])
@login_required
def oracle_chat():
    data = request.get_json()
    q = (data.get('message','') or '').lower()
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).limit(100).all()
    if not trades:
        return jsonify({'response':'You have no trades yet. Take your first trade and I will guide you.'})
    total=len(trades); wins=len([t for t in trades if t.result=='WIN']); losses=len([t for t in trades if t.result=='LOSS'])
    wr=wins/total*100 if total else 0; avg_r=sum(t.r_multiple or 0 for t in trades)/total if total else 0; tp=sum(t.pnl or 0 for t in trades)
    best=max(trades, key=lambda t: t.pnl or 0); worst=min(trades, key=lambda t: t.pnl or 0)
    sp={}; [sp.update({t.setup_type:sp.get(t.setup_type,0)+(t.pnl or 0)}) for t in trades if t.setup_type]
    bsetup=max(sp,key=sp.get) if sp else 'N/A'; wsetup=min(sp,key=sp.get) if sp else 'N/A'

    if 'grade' in q or 'rate' in q:
        g='A' if wr>=70 else 'B' if wr>=60 else 'C' if wr>=50 else 'D'
        resp=f"**Overall Grade: {g}** ({wr:.0f}% WR)\n\n📊 Stats:\n• Trades: {total}\n• Win Rate: {wr:.0f}%\n• Avg R: {avg_r:.2f}\n• Total P&L: ${tp:.2f}\n• Best Setup: {bsetup} (${sp[bsetup]:.2f})\n• Worst Setup: {wsetup} (${sp[wsetup]:.2f})\n\n🎯 Best trade: ${best.pnl:.2f} — study that entry.\n❌ Worst setup {wsetup} lost ${abs(sp[wsetup]):.2f}."
        if losses>wins: resp+="\n\n⚠️ You lose more than you win. Cut losses early."
    elif 'improve' in q or 'weak' in q:
        resp=f"Your biggest leak: **{worst.setup_type or 'Unknown'}** (${abs(worst.pnl or 0):.2f}).\n\nLivermore: 'The loss is taken. Don't turn it into a catastrophe.'\nSeykota: 'The system is perfect. You aren't following it.'\n\nDrill: paper trade that setup for 10 entries."
    elif 'future' in q or 'predict' in q or 'project' in q:
        resp=f"Next 10 trades: ${(avg_r*10*0.6):.2f}\nMonthly: ${(tp*4/max(1,total/10)):.2f}\nRisk: {max(5,30-wr):.0f}% chance of -10% drawdown.\n\n⚠️ Not financial advice."
    elif 'drill' in q or 'coach' in q or 'practice' in q:
        resp=f"**7-Day Protocol:**\nDay 1-3: Demo {wsetup} — 10 entries, full checklist.\nDay 4-5: Half size until WR>50%.\nDay 6-7: Full size, grade every trade.\n\nSeykota: 'Elements: cut losses, ride winners, keep bets small.'"
    elif 'tilt' in q or 'emotion' in q:
        et=[t for t in trades if t.emotion]; tc=sum(1 for t in et if t.emotion.lower() in ['angry','frustrated','revenge','greed'])
        resp=f"Emotional Analysis:\n• Tagged trades: {len(et)}/{total}\n• Tilt events: {tc}\n• Tudor Jones: 'Secret is losing little when wrong.'"
    elif 'livermore' in q or 'seykota' in q or 'quote' in q:
        import random
        quotes=["'The market never lies. People lie.' — Jesse Livermore","'The trend is your friend until the end.' — Ed Seykota","'Cut losses, let winners run.' — William Eckhardt","'Losers average losers.' — Paul Tudor Jones","'Be right and sit tight.' — Jesse Livermore","'Risk no more than 1% per trade.' — Larry Hite"]
        resp=random.choice(quotes)
    else:
        resp=f"I am your 300-year market intelligence.\n📈 {total} trades | {wr:.0f}% WR | {avg_r:.2f}R | ${tp:.2f}\n\nAsk: grade, improve, predict, drill, tilt, quote"
    db.session.add(OracleInsight(user_id=current_user.id, insight_type='chat', title=q[:100], content=resp[:500], score=int(wr)))
    db.session.commit()
    return jsonify({'response': resp})

@app.route('/api/oracle/tilt-check')
@login_required
def oracle_tilt_check():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).limit(5).all()
    cons = 0
    for t in trades:
        if t.result == 'LOSS': cons += 1
        else: break
    recent_pnl = sum(t.pnl or 0 for t in trades)
    return jsonify({'tilt_detected': cons >= 3, 'consecutive_losses': cons, 'recent_pnl': round(recent_pnl,2), 'message': '⚠️ Tilt detected. Step away.' if cons>=3 else '✅ You look clear. Keep trading.'})

# ─── REPORTS ──────────────────────────────────────────

@app.route('/reports')
@login_required
def reports():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()
    return render_template('reports.html', trades=trades)

@app.route('/api/reports/csv')
@login_required
def reports_csv():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Symbol','Direction','Entry','Exit','Quantity','P&L','R Multiple','Result','Setup','Session','Emotion','Entry Date','Exit Date'])
    for t in trades:
        cw.writerow([t.symbol, t.direction, t.entry_price, t.exit_price, t.quantity, t.pnl, t.r_multiple, t.result, t.setup_type, t.session, t.emotion, t.entry_date, t.exit_date])
    return Response(si.getvalue().encode('utf-8'), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=trades.csv'})

# ─── AI REVIEW ───────────────────────────────────────────

@app.route('/ai-review')
@login_required
def ai_review():
    trades = Trade.query.filter_by(user_id=current_user.id).filter(Trade.result.in_(['WIN', 'LOSS'])).order_by(Trade.exit_date.desc()).all()
    total = len(trades)
    if total == 0:
        return render_template('ai_review.html', review=None, patterns=None, score=0)

    # Pattern detection
    patterns = []

    # 1. Tilt / revenge detection: losses followed by more losses with same direction
    consecutive_losses = 0
    max_cl = 0
    for t in trades:
        if t.result == 'LOSS':
            consecutive_losses += 1
            max_cl = max(max_cl, consecutive_losses)
        else:
            consecutive_losses = 0
    if max_cl >= 3:
        patterns.append(f"Tilt risk detected: you had a {max_cl}-trade losing streak. Consider taking a break after 2 consecutive losses.")

    # 2. Best time analysis
    from collections import defaultdict
    hourly = defaultdict(lambda: {'pnl': 0, 'count': 0, 'wins': 0})
    for t in trades:
        if t.entry_date:
            h = t.entry_date.hour
            hourly[h]['pnl'] += (t.pnl or 0)
            hourly[h]['count'] += 1
            if t.result == 'WIN':
                hourly[h]['wins'] += 1
    best_hour = max(hourly, key=lambda h: hourly[h]['pnl']) if hourly else None
    worst_hour = min(hourly, key=lambda h: hourly[h]['pnl']) if hourly else None
    if best_hour is not None and hourly[best_hour]['pnl'] > 0:
        patterns.append(f"Best trading hour: {best_hour}:00 (${hourly[best_hour]['pnl']:.2f}, {hourly[best_hour]['wins']}/{hourly[best_hour]['count']} wins)")
    if worst_hour is not None and hourly[worst_hour]['pnl'] < 0:
        patterns.append(f"Worst trading hour: {worst_hour}:00 (${hourly[worst_hour]['pnl']:.2f})")

    # 3. Setup performance
    setup_perf = defaultdict(lambda: {'pnl': 0, 'count': 0, 'wins': 0})
    for t in trades:
        s = t.setup_type or 'Unspecified'
        setup_perf[s]['pnl'] += (t.pnl or 0)
        setup_perf[s]['count'] += 1
        if t.result == 'WIN':
            setup_perf[s]['wins'] += 1
    best_setup = max(setup_perf, key=lambda s: setup_perf[s]['pnl'])
    worst_setup = min(setup_perf, key=lambda s: setup_perf[s]['pnl'])
    if setup_perf[best_setup]['pnl'] > 0:
        patterns.append(f"Best setup: {best_setup} (${setup_perf[best_setup]['pnl']:.2f}, {setup_perf[best_setup]['wins']}/{setup_perf[best_setup]['count']})")
    if worst_setup != best_setup and setup_perf[worst_setup]['pnl'] < 0:
        patterns.append(f"Worst setup: {worst_setup} (${setup_perf[worst_setup]['pnl']:.2f}) — consider dropping it")

    # 4. Emotion analysis
    emotion_pnl = defaultdict(float)
    emotion_count = defaultdict(int)
    for t in trades:
        if t.emotion:
            emotion_pnl[t.emotion] += (t.pnl or 0)
            emotion_count[t.emotion] += 1
    if emotion_pnl:
        best_emotion = max(emotion_pnl, key=emotion_pnl.get)
        worst_emotion = min(emotion_pnl, key=emotion_pnl.get)
        if emotion_count[best_emotion] >= 2:
            patterns.append(f"Best mindset: '{best_emotion}' (${emotion_pnl[best_emotion]:.2f} across {emotion_count[best_emotion]} trades)")
        if worst_emotion != best_emotion and emotion_count.get(worst_emotion, 0) >= 2:
            patterns.append(f"Worst mindset: '{worst_emotion}' (${emotion_pnl[worst_emotion]:.2f})")

    # 5. Day of week
    dow_pnl = defaultdict(float)
    dow_count = defaultdict(int)
    for t in trades:
        if t.exit_date:
            day = t.exit_date.strftime('%A')
            dow_pnl[day] += (t.pnl or 0)
            dow_count[day] += 1
    if dow_pnl:
        best_day = max(dow_pnl, key=dow_pnl.get)
        worst_day = min(dow_pnl, key=dow_pnl.get)
        patterns.append(f"Best day: {best_day} (${dow_pnl[best_day]:.2f}) | Worst day: {worst_day} (${dow_pnl[worst_day]:.2f})")

    # 6. Win rate by month trend
    monthly_wr_data = defaultdict(lambda: {'wins': 0, 'losses': 0})
    for t in trades:
        if t.exit_date:
            mk = t.exit_date.strftime('%Y-%m')
            if t.result == 'WIN':
                monthly_wr_data[mk]['wins'] += 1
            else:
                monthly_wr_data[mk]['losses'] += 1
    sorted_months = sorted(monthly_wr_data.keys())
    if len(sorted_months) >= 2:
        first_m = sorted_months[0]
        last_m = sorted_months[-1]
        f_wr = monthly_wr_data[first_m]['wins'] / (monthly_wr_data[first_m]['wins'] + monthly_wr_data[first_m]['losses']) * 100 if (monthly_wr_data[first_m]['wins'] + monthly_wr_data[first_m]['losses']) > 0 else 0
        l_wr = monthly_wr_data[last_m]['wins'] / (monthly_wr_data[last_m]['wins'] + monthly_wr_data[last_m]['losses']) * 100 if (monthly_wr_data[last_m]['wins'] + monthly_wr_data[last_m]['losses']) > 0 else 0
        trend = "improving" if l_wr > f_wr else "declining" if l_wr < f_wr else "stable"
        patterns.append(f"Win rate trend: {trend} ({f_wr:.0f}% → {l_wr:.0f}%)")

    # Generate overall review text
    wins = sum(1 for t in trades if t.result == 'WIN')
    losses = total - wins
    wr = wins / total * 100 if total > 0 else 0
    total_pnl_ai = sum(t.pnl or 0 for t in trades)
    avg_r_all = 0
    r_all = [t.r_multiple for t in trades if t.r_multiple]
    if r_all:
        avg_r_all = sum(r_all) / len(r_all)

    review_text = f"You've traded {total} times ({wins} wins, {losses} losses). Your win rate is {wr:.1f}% and total P&L is ${total_pnl_ai:.2f}."

    if avg_r_all > 1.5:
        review_text += f" Your average R-multiple of {avg_r_all:.2f} is strong — you're letting winners run."
    elif avg_r_all < 0.8:
        review_text += f" Your average R-multiple of {avg_r_all:.2f} is low — you may be cutting winners too early."
    else:
        review_text += f" Your average R-multiple of {avg_r_all:.2f} is reasonable."

    if wr > 65:
        review_text += " High win rate suggests strong edge. Focus on position sizing to maximize this."
    elif wr < 40:
        review_text += " Low win rate means your edge may need work. Review your setup criteria."

    # Edge Score for review
    pf_ai = 0
    gw = sum(t.pnl for t in trades if t.result == 'WIN') or 0
    gl = abs(sum(t.pnl for t in trades if t.result == 'LOSS') or 0)
    pf_ai = round(gw / gl, 2) if gl > 0 else 0
    pf_score = min(100, pf_ai / 3 * 100)
    wr_score = wr
    r_score = min(100, avg_r_all / 3 * 100)
    score = round(pf_score * 0.30 + wr_score * 0.25 + r_score * 0.20 + 50 * 0.15 + 50 * 0.10)

    return render_template('ai_review.html',
        review=review_text, patterns=patterns, score=score,
        total=total, wins=wins, losses=losses,
        wr=round(wr, 1), total_pnl_ai=round(total_pnl_ai, 2),
        avg_r=round(avg_r_all, 2), pf=pf_ai,
    )

@app.route('/api/ai-review-data')
@login_required
def api_ai_review_data():
    trades = Trade.query.filter_by(user_id=current_user.id).filter(Trade.result.in_(['WIN', 'LOSS'])).all()
    from collections import defaultdict
    # Hourly heatmap data
    hourly = defaultdict(lambda: {'pnl': 0, 'count': 0})
    for t in trades:
        if t.entry_date:
            h = t.entry_date.hour
            hourly[h]['pnl'] += (t.pnl or 0)
            hourly[h]['count'] += 1
    return jsonify({
        'hourly': {str(k): v for k, v in sorted(hourly.items())},
        'total': len(trades),
    })

# ─── PROP FIRM CHALLENGE ─────────────────────────────

@app.route('/prop-firm')
@login_required
def prop_firm():
    challenges = PropFirmChallenge.query.filter_by(user_id=current_user.id).order_by(PropFirmChallenge.created_at.desc()).all()
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()
    return render_template('prop_firm.html', challenges=challenges, trades=trades, today=date.today())

@app.route('/prop-firm/new', methods=['GET','POST'])
@login_required
def prop_firm_new():
    if request.method == 'POST':
        c = PropFirmChallenge(user_id=current_user.id, firm_name=request.form['firm_name'], account_size=float(request.form['account_size']), max_daily_loss=float(request.form['max_daily_loss']), max_drawdown=float(request.form['max_drawdown']), profit_target=float(request.form['profit_target']), start_balance=float(request.form['account_size']), current_balance=float(request.form['account_size']), peak_balance=float(request.form['account_size']))
        db.session.add(c); db.session.commit()
        flash('Challenge created!','success')
        return redirect(url_for('prop_firm'))
    return render_template('prop_firm_new.html')

@app.route('/prop-firm/delete/<int:cid>', methods=['POST'])
@login_required
def prop_firm_delete(cid):
    c = PropFirmChallenge.query.get_or_404(cid)
    if c.user_id == current_user.id:
        db.session.delete(c); db.session.commit()
    return redirect(url_for('prop_firm'))

@app.route('/api/prop-firm/update/<int:cid>', methods=['POST'])
@login_required
def prop_firm_update(cid):
    c = PropFirmChallenge.query.get_or_404(cid)
    if c.user_id != current_user.id: return jsonify({'error':'unauthorized'}),403
    trades = Trade.query.filter_by(user_id=current_user.id).filter(Trade.entry_date >= c.start_date).order_by(Trade.entry_date).all()
    balance = c.start_balance; peak = c.start_balance; daily = {}
    for t in trades:
        if t.entry_date: d = t.entry_date.strftime('%Y-%m-%d')
        else: continue
        daily[d] = daily.get(d,0) + (t.pnl or 0)
        balance += t.pnl or 0
        if balance > peak: peak = balance
    c.current_balance = round(balance,2)
    c.peak_balance = round(peak,2)
    c.daily_pnl = json.dumps({k:round(v,2) for k,v in sorted(daily.items())})
    td_pnl_actual = daily.get(date.today().strftime('%Y-%m-%d'), 0)
    status = 'active'
    if balance <= c.start_balance - c.max_drawdown: status = 'failed'
    elif balance >= c.start_balance + c.profit_target: status = 'passed'
    elif abs(td_pnl_actual) >= c.max_daily_loss: status = 'failed'
    c.status = status
    db.session.commit()
    return redirect(url_for('prop_firm'))

# ─── TRADE RATING ─────────────────────────────────────

@app.route('/trade/rate/<int:trade_id>', methods=['GET','POST'])
@login_required
def trade_rate(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if trade.user_id != current_user.id: return redirect(url_for('trades'))
    existing = TradeRating.query.filter_by(trade_id=trade_id, user_id=current_user.id).first()
    if request.method == 'POST':
        if existing: db.session.delete(existing)
        tr = TradeRating(trade_id=trade_id, user_id=current_user.id, rating=int(request.form['rating']), entry_score=int(request.form.get('entry_score',3)), exit_score=int(request.form.get('exit_score',3)), risk_score=int(request.form.get('risk_score',3)), discipline_score=int(request.form.get('discipline_score',3)), emotion_score=int(request.form.get('emotion_score',3)), notes=request.form.get('notes',''))
        db.session.add(tr); db.session.commit()
        flash('Trade rated!','success'); return redirect(url_for('trades'))
    return render_template('trade_rate.html', trade=trade, existing=existing)

# ─── STRATEGY PERFORMANCE ─────────────────────────────

@app.route('/strategy-performance')
@login_required
def strategy_performance():
    trades = Trade.query.filter_by(user_id=current_user.id).order_by(Trade.entry_date.desc()).all()
    setups = {}
    for t in trades:
        s = t.setup_type or 'Unknown'
        if s not in setups: setups[s] = {'trades':0,'wins':0,'losses':0,'pnl':0,'r_sum':0}
        setups[s]['trades'] += 1
        if t.result == 'WIN': setups[s]['wins'] += 1
        elif t.result == 'LOSS': setups[s]['losses'] += 1
        setups[s]['pnl'] += t.pnl or 0
        setups[s]['r_sum'] += t.r_multiple or 0
    for s,d in setups.items():
        d['wr'] = round(d['wins']/d['trades']*100,1) if d['trades'] else 0
        d['avg_r'] = round(d['r_sum']/d['trades'],2) if d['trades'] else 0
        d['pnl'] = round(d['pnl'],2)
    return render_template('strategy_performance.html', setups=setups)

# ─── COMMUNITY ────────────────────────────────────────

@app.route('/community')
@login_required
def community():
    insights = CommunityInsight.query.order_by(CommunityInsight.created_at.desc()).limit(50).all()
    total_users = User.query.count()
    total_trades = Trade.query.count()
    global_wr = round(len([t for t in Trade.query.filter(Trade.result.in_(['WIN','LOSS'])).all() if t.result=='WIN'])/max(1,Trade.query.filter(Trade.result.in_(['WIN','LOSS'])).count())*100,1)
    return render_template('community.html', insights=insights, total_users=total_users, total_trades=total_trades, global_wr=global_wr)

@app.route('/api/community/stats')
def community_stats():
    trades = Trade.query.filter(Trade.result.in_(['WIN','LOSS'])).all()
    total = len(trades)
    wins = len([t for t in trades if t.result=='WIN'])
    best_trade = max(trades, key=lambda t: t.r_multiple or 0) if trades else None
    avg_r = sum(t.r_multiple or 0 for t in trades)/total if total else 0
    setups = {}
    for t in trades:
        s = t.setup_type or 'Unknown'
        if s not in setups: setups[s]={'wins':0,'losses':0}
        if t.result=='WIN': setups[s]['wins']+=1
        else: setups[s]['losses']+=1
    top_setup = max(setups, key=lambda s: setups[s]['wins']/(max(1,setups[s]['wins']+setups[s]['losses']))) if setups else None
    return jsonify({'total_trades':total,'global_wr':round(wins/total*100,1) if total else 0,'top_setup':top_setup,'avg_r':round(avg_r,2),'best_r':best_trade.r_multiple if best_trade else 0})

@app.route('/api/community/share', methods=['POST'])
@login_required
def community_share():
    data = request.get_json()
    trade_id = data.get('trade_id')
    trade = Trade.query.get(trade_id)
    if not trade or trade.user_id != current_user.id: return jsonify({'error':'not found'}),404
    existing = CommunityInsight.query.filter_by(user_id=current_user.id, trade_id=trade_id).first()
    if existing: return jsonify({'error':'already shared'}),400
    ci = CommunityInsight(user_id=current_user.id, trade_id=trade_id, insight_type='trade', strategy=trade.setup_type or '', symbol=trade.symbol, direction=trade.direction, r_multiple=trade.r_multiple, result=trade.result, note=data.get('note',''), anonymous=data.get('anonymous',True))
    db.session.add(ci); db.session.commit()
    return jsonify({'status':'shared'})

# ─── MARKET DATA ──────────────────────────────────────────

WATCHLIST = {
    'XAUUSD': 'GC=F', 'XAGUSD': 'SI=F', 'BTCUSD': 'BTC-USD',
    'ETHUSD': 'ETH-USD', 'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X',
    'US500': 'ES=F', 'US30': 'YM=F', 'WTI': 'CL=F',
}

market_cache = {}
cache_lock = threading.Lock()

def fetch_prices():
    while True:
        try:
            symbols = list(WATCHLIST.values())
            tickers = yf.Tickers(' '.join(symbols))
            data = {}
            for display, yf_key in WATCHLIST.items():
                try:
                    t = tickers.tickers.get(yf_key)
                    info = t.info if t else {}
                    q = t.fast_info if t else None
                    price = q.last_price if q else info.get('regularMarketPrice', info.get('previousClose'))
                    data[display] = {
                        'price': round(price, 2) if price else None,
                        'bid': round(info.get('bid') or 0, 2),
                        'ask': round(info.get('ask') or 0, 2),
                        'change': round(info.get('regularMarketChange') or 0, 2),
                        'change_pct': round(info.get('regularMarketChangePercent') or 0, 2),
                        'high': round(info.get('regularMarketDayHigh') or 0, 2),
                        'low': round(info.get('regularMarketDayLow') or 0, 2),
                        'volume': info.get('regularMarketVolume'),
                    }
                except:
                    data[display] = {'price': None, 'change': 0, 'change_pct': 0}
            with cache_lock:
                market_cache.clear()
                market_cache.update(data)
        except:
            pass
        time.sleep(30)

threading.Thread(target=fetch_prices, daemon=True).start()

@app.route('/api/market')
def api_market():
    with cache_lock:
        return jsonify(dict(market_cache))

@app.route('/api/stats')
@login_required
def api_stats():
    q = Trade.query.filter_by(user_id=current_user.id)
    wins = q.filter_by(result='WIN').count()
    losses = q.filter_by(result='LOSS').count()
    pnl = db.session.query(func.sum(Trade.pnl)).filter_by(user_id=current_user.id).scalar() or 0
    return jsonify({'total': q.count(), 'wins': wins, 'losses': losses, 'pnl': round(pnl, 2)})

@app.route('/api/live_pnl')
@login_required
def api_live_pnl():
    trades = Trade.query.filter_by(user_id=current_user.id, result='OPEN').all()
    with cache_lock:
        prices = dict(market_cache)
    results = []
    for t in trades:
        m = prices.get(t.symbol)
        price = m.get('price') if m else None
        if price:
            if t.direction == 'LONG':
                pnl = (price - t.entry_price) * t.quantity - t.fees
            else:
                pnl = (t.entry_price - price) * t.quantity - t.fees
        else:
            pnl = None
        results.append({'symbol': t.symbol, 'direction': t.direction,
                        'entry_price': t.entry_price, 'live_price': price,
                        'live_pnl': round(pnl, 2) if pnl else None,
                        'trade_id': t.id})
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
