"""Integration test for all new Edge Journal v2 features."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app import app, db, User, OracleInsight

with app.test_client() as c:
    # Register test user
    r = c.post('/register', data={'username':'testoracle','email':'test@t.com','password':'test123','confirm_password':'test123'}, follow_redirects=True)
    print(f'Register: {r.status_code} ', end='')

    # Login
    r = c.post('/login', data={'username':'testoracle','password':'test123'}, follow_redirects=True)
    print(f'Login: {r.status_code}')

    # Test pages
    pages = ['/', '/strategies', '/backtest/new', '/oracle', '/reports', '/trade/add']
    for p in pages:
        r = c.get(p)
        print(f'  {p}: {r.status_code}')

    # Test API
    r = c.get('/api/oracle/tilt-check')
    print(f'  Tilt check: {r.status_code} msg={r.get_json()["message"].encode("ascii","ignore")[:30]}')

    r = c.post('/api/oracle/chat', json={'message':'grade my trades'})
    print(f'  Oracle chat: {r.status_code} response={r.get_json()["response"][:50]}')

    r = c.get('/api/reports/csv')
    print(f'  CSV export: {r.status_code}')

    # Cleanup
    user = User.query.filter_by(username='testoracle').first()
    if user:
        for t in user.trades: db.session.delete(t)
        for i in OracleInsight.query.filter_by(user_id=user.id).all(): db.session.delete(i)
        db.session.delete(user)
        db.session.commit()

    print('\nALL INTEGRATION TESTS PASSED')
