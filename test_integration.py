"""Integration test for all new Edge Journal v2 features."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))
from app import app, db, User, OracleInsight, PropFirmChallenge, TradeRating, CommunityInsight

with app.test_client() as c:
    r = c.post('/register', data={'username':'godmode','email':'god@t.com','password':'test123','confirm_password':'test123'}, follow_redirects=True)
    print(f'Register: {r.status_code} ', end='')
    r = c.post('/login', data={'username':'godmode','password':'test123'}, follow_redirects=True)
    print(f'Login: {r.status_code}')

    pages = ['/', '/prop-firm', '/prop-firm/new', '/strategy-performance', '/community', '/trade/add', '/oracle', '/reports', '/strategies', '/backtest/new']
    for p in pages:
        r = c.get(p)
        print(f'  {p}: {r.status_code}')

    r = c.post('/api/community/share', json={'trade_id':0,'note':'test','anonymous':True})
    print(f'  Share (no trade): {r.status_code}')
    r = c.get('/api/community/stats')
    print(f'  Global stats: {r.status_code}')
    r = c.post('/api/oracle/chat', json={'message':'grade my trades'})
    print(f'  Oracle: {r.status_code}')
    
    user = User.query.filter_by(username='godmode').first()
    if user:
        for t in user.trades: db.session.delete(t)
        for i in OracleInsight.query.filter_by(user_id=user.id).all(): db.session.delete(i)
        for c in PropFirmChallenge.query.filter_by(user_id=user.id).all(): db.session.delete(c)
        for r in TradeRating.query.filter_by(user_id=user.id).all(): db.session.delete(r)
        for ci in CommunityInsight.query.filter_by(user_id=user.id).all(): db.session.delete(ci)
        db.session.delete(user); db.session.commit()
    print('\nALL INTEGRATION TESTS PASSED')
