import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.models import db, Admin, Audit, Report
from app.services import geoapify

@pytest.fixture
def app():
    return create_app(dict(TESTING=True, SECRET_KEY='test-only-secret-'*4,
                           SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', GEOAPIFY_API_KEY=''))

@pytest.fixture
def client(app):
    return app.test_client()

def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return {'X-CSRF-Token': session['csrf']}

def report_data():
    return dict(category='poor_lighting', description='Street light not working near crossing.', lat=17.4, lng=78.4)

def feature(coords=None):
    return dict(type='Feature', geometry=dict(type='MultiLineString', coordinates=[coords or [[78.4,17.4],[78.41,17.41],[78.42,17.42]]]),
        properties=dict(distance=3075, time=1800, legs=[dict(steps=[
            dict(from_index=0, to_index=1, instruction=dict(text='Head north'), distance=1500),
            dict(from_index=1, to_index=2, instruction=dict(text='Turn right'), distance=1500)])]))

def test_home_and_health(client):
    assert client.get('/').status_code == 200
    assert b'Find routes' in client.get('/').data
    assert client.get('/health').json['safety_scoring'] is False

def test_secret_required():
    with pytest.raises(RuntimeError):
        create_app(dict(SECRET_KEY='replace-this', TESTING=True))

def test_csrf_required(client):
    client.get('/')
    assert client.post('/api/reports', json=report_data()).status_code == 400

@pytest.mark.parametrize('coordinate', ['NaN','Infinity',91,None,True])
def test_invalid_coordinates(client, coordinate):
    data=report_data(); data['lat']=coordinate
    assert client.post('/api/reports', json=data, headers=csrf(client)).status_code == 400

def test_report_ownership_and_deletion(app, client):
    response=client.post('/api/reports',json=report_data(),headers=csrf(client))
    assert response.status_code == 201
    report_id=response.json['report']['id']
    assert client.get('/api/reports').json['reports'][0]['status']=='pending'
    stranger=app.test_client()
    assert stranger.get('/api/reports').json['reports']==[]
    assert stranger.delete('/api/reports/'+report_id,headers=csrf(stranger)).status_code==404
    assert client.delete('/api/reports/'+report_id,headers=csrf(client)).status_code==200
    assert client.get('/api/reports').json['reports']==[]

def test_report_content_is_escaped(app, client):
    data=report_data();data['description']='<script>alert("unsafe")</script>'
    client.post('/api/reports',json=data,headers=csrf(client))
    with app.app_context():
        db.session.add(Admin(username='admin',password_hash=generate_password_hash('secure-test-password')));db.session.commit()
    with client.session_transaction() as session: session['admin_id']=1
    assert b'&lt;script&gt;' in client.get('/admin/').data
    assert b'<script>alert' not in client.get('/admin/').data

def test_admin_auth_moderation_and_audit(app,client):
    assert client.get('/admin/').status_code==302
    report=client.post('/api/reports',json=report_data(),headers=csrf(client)).json['report']
    with app.app_context():
        db.session.add(Admin(username='admin',password_hash=generate_password_hash('secure-test-password')));db.session.commit()
    with client.session_transaction() as session: token=session['csrf']
    wrong=client.post('/admin/login',data=dict(username='admin',password='wrong',csrf=token))
    assert b'incorrect' in wrong.data
    assert client.post('/admin/login',data=dict(username='admin',password='secure-test-password',csrf=token)).status_code==302
    with client.session_transaction() as session: token=session['csrf']
    assert client.post('/admin/reports/'+report['id'],data=dict(status='verified',reason='not permitted',csrf=token)).status_code==400
    assert client.post('/admin/reports/'+report['id'],data=dict(status='reviewed',reason='Submission reviewed; evidence unverified.',csrf=token)).status_code==302
    with app.app_context():
        assert db.session.get(Report,report['id']).status=='reviewed'
        assert db.session.execute(db.select(Audit)).scalar_one().old_status=='pending'
    assert client.get('/api/reports').json['reports'][0]['status']=='reviewed'
    assert client.post('/admin/logout',data=dict(csrf=token)).status_code==302
    assert client.get('/admin/').status_code==302

def test_unknown_admin(client):
    csrf(client)
    with client.session_transaction() as session: token=session['csrf']
    assert b'incorrect' in client.post('/admin/login',data=dict(username='missing',password='wrong',csrf=token)).data

def test_missing_api_key(client):
    response=client.get('/api/search?q=Hyderabad')
    assert response.status_code==503
    assert 'Geoapify' in response.json['error']

def test_search_normalization(client,monkeypatch):
    monkeypatch.setattr(geoapify,'fetch',lambda *a,**k:dict(features=[dict(properties=dict(formatted='Hyderabad, India',lat=17.4,lon=78.4))]))
    assert client.get('/api/search?q=Hyderabad').json['places']==[dict(label='Hyderabad, India',lat=17.4,lng=78.4)]
    assert client.get('/api/search?q=Hi').status_code==400

def test_distinct_routes_and_steps(client,monkeypatch):
    def fetch(path, params):
        coords=[[78.4,17.4],[78.41,17.41],[78.42,17.42]] if params['type']=='balanced' else [[78.4,17.4],[78.43,17.4],[78.42,17.42]]
        return dict(features=[feature(coords)])
    monkeypatch.setattr(geoapify,'fetch',fetch)
    response=client.post('/api/routes',json=dict(start=[17.4,78.4],end=[17.42,78.42],mode='walk'),headers=csrf(client))
    assert response.status_code==200
    assert len(response.json['routes'])==2
    assert response.json['routes'][0]['steps'][1]['point']==[78.41,17.41]
    assert response.json['routes'][0]['steps'][1]['text']=='Turn right'

def test_duplicate_routes_suppressed(app,monkeypatch):
    monkeypatch.setattr(geoapify,'fetch',lambda *a,**k:dict(features=[feature()]))
    with app.app_context():assert len(geoapify.routes([17.4,78.4],[17.42,78.42],'walk')['routes'])==1

@pytest.mark.parametrize('mode', ['walk', 'bicycle', 'motorcycle', 'drive'])
def test_three_route_options(client, monkeypatch, mode):
    calls = []
    def fetch(path, params):
        calls.append(params)
        if 'avoid' in params:
            assert params['type'] == 'balanced'
            assert params['avoid'].startswith('location:')
            coords = [[78.4,17.4],[78.39,17.43],[78.42,17.42]]
        elif params['type'] == 'short':
            coords = [[78.4,17.4],[78.43,17.4],[78.42,17.42]]
        else:
            coords = [[78.4,17.4],[78.41,17.41],[78.42,17.42]]
        return dict(features=[feature(coords)])
    monkeypatch.setattr(geoapify, 'fetch', fetch)
    response = client.post('/api/routes', json=dict(start=[17.4,78.4], end=[17.42,78.42], mode=mode), headers=csrf(client))
    assert response.status_code == 200
    assert len(calls) == 3
    assert [r['preference'] for r in response.json['routes']] == ['balanced', 'short', 'alternative']
    assert [r['id'] for r in response.json['routes']] == [0, 1, 2]
    assert response.json['warnings'] == []

def test_third_route_failure_retains_routes(app, monkeypatch):
    def fetch(path, params):
        if 'avoid' in params:
            raise geoapify.ProviderError('Unavailable')
        return dict(features=[feature()])
    monkeypatch.setattr(geoapify, 'fetch', fetch)
    with app.app_context():
        result = geoapify.routes([17.4,78.4], [17.42,78.42], 'walk')
        assert len(result['routes']) == 1
        assert any('alternative-route' in warning for warning in result['warnings'])

def test_duplicate_with_different_vertex_density():
    a=geoapify.normalize(feature([[78.4,17.4],[78.42,17.42]]),'balanced')
    b=geoapify.normalize(feature(),'short')
    assert geoapify.duplicate(a,b)

def test_optional_route_failure_retains_first(app,monkeypatch):
    def fetch(path,params):
        if params['type']=='short':raise geoapify.ProviderError('Unavailable')
        return dict(features=[feature()])
    monkeypatch.setattr(geoapify,'fetch',fetch)
    with app.app_context():
        result=geoapify.routes([17.4,78.4],[17.42,78.42],'walk')
        assert len(result['routes'])==1 and result['warnings']

@pytest.mark.parametrize('data', [dict(start=[0,0],end=[0,0],mode='walk'),dict(start=[0],end=[1,1],mode='walk'),dict(start=[0,0],end=[1,1],mode='flight')])
def test_route_validation(client,data):
    assert client.post('/api/routes',json=data,headers=csrf(client)).status_code==400

def test_nearby_help_normalization(client,monkeypatch):
    monkeypatch.setattr(geoapify,'fetch',lambda *a,**k:dict(features=[dict(properties=dict(name='Test hospital',categories=['healthcare.hospital']),geometry=dict(type='Point',coordinates=[78.41,17.41]))]))
    response=client.get('/api/help?lat=17.4&lng=78.4')
    assert response.status_code==200
    assert response.json['places'][0]['distance']>0
    assert 'safety_score' not in response.json

def test_security_headers(client):
    response=client.get('/api/reports')
    assert response.headers['Cache-Control']=='no-store'
    assert response.headers['X-Frame-Options']=='DENY'
    assert 'HttpOnly' in response.headers.get('Set-Cookie','')

@pytest.mark.parametrize('category', ['service.police', 'healthcare.hospital', 'healthcare.pharmacy'])
def test_facility_category_filter(client, monkeypatch, category):
    def fetch(path, params):
        assert path == 'v2/places'
        assert params['categories'] == category
        assert params['filter'] == 'circle:77.59,12.97,5000'
        return dict(features=[])
    monkeypatch.setattr(geoapify, 'fetch', fetch)
    response = client.get('/api/help', query_string=dict(lat=12.97, lng=77.59, category=category))
    assert response.status_code == 200
    assert response.json['places'] == []

def test_invalid_facility_category(client):
    assert client.get('/api/help?lat=12.97&lng=77.59&category=invalid').status_code == 400

def test_admin_bootstrap(app):
    runner=app.test_cli_runner()
    result=runner.invoke(args=['create-admin','--username','owner','--password','strong-test-password'])
    assert result.exit_code==0
    with app.app_context():
        account=db.session.execute(db.select(Admin)).scalar_one()
        assert check_hash(account.password_hash)

def check_hash(value):
    from werkzeug.security import check_password_hash
    return check_password_hash(value,'strong-test-password')


def test_route_recommendation_uses_time_then_distance(client, monkeypatch):
    from app import routes as route_module
    monkeypatch.setattr(route_module, 'analyze_demo_route', lambda geometry: dict(demo_safety_score=None, demo_crime_rate=None))
    candidates = [
        dict(duration=900, distance=1000, geometry=feature()['geometry']),
        dict(duration=600, distance=1500, geometry=feature()['geometry']),
        dict(duration=600, distance=1200, geometry=feature()['geometry']),
    ]
    monkeypatch.setattr(geoapify, 'routes', lambda *args: dict(routes=candidates, warnings=[]))
    response = client.post('/api/routes', json=dict(start=[17.4, 78.4], end=[17.42, 78.42], mode='walk'), headers=csrf(client))
    assert response.status_code == 200
    assert [route['recommended'] for route in response.json['routes']] == [False, False, True]
    assert 'Shortest estimated travel time' in response.json['routes'][2]['recommendation_reason']


def test_demo_recommendation_compares_all_routes(client, monkeypatch):
    candidates = [dict(duration=time, distance=distance, geometry={'index': index})
                  for index, (time, distance) in enumerate([(600, 1000), (700, 1200), (800, 1500)])]
    monkeypatch.setattr(geoapify, 'routes', lambda *args: dict(routes=candidates, warnings=[]))
    from app import routes as route_module
    monkeypatch.setattr(route_module, 'analyze_demo_route', lambda geometry: dict(
        demo_safety_score=[20, 90, 50][geometry['index']],
        demo_crime_rate=[80, 10, 50][geometry['index']]))
    response = client.post('/api/routes', json=dict(start=[17.4, 78.4], end=[17.42, 78.42], mode='walk'), headers=csrf(client))
    assert response.status_code == 200
    assert [route['recommended'] for route in response.json['routes']] == [False, True, False]
    assert response.json['routes'][1]['recommendation_basis'] == 'synthetic_demo'
