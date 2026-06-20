import os, threading, time, csv, io
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
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
    return render_template('add_trade.html', trade=None)

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
