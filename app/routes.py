import math
import secrets
import uuid
from functools import wraps
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from . import owner_key
from .models import db, Admin, Audit, Report
from .services import geoapify
from .services.demo_service import analyze_demo_route
from .services.lighting_ml import recommend_routes, score_route_lighting

api = Blueprint('api', __name__, url_prefix='/api')
main = Blueprint('main', __name__)
admin = Blueprint('admin', __name__, url_prefix='/admin')
CATEGORIES = ('poor_lighting', 'harassment', 'road_obstruction', 'other')

def coordinates(lat, lng):
    try:
        if isinstance(lat, bool) or isinstance(lng, bool):
            raise ValueError
        lat, lng = float(lat), float(lng)
        if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise ValueError
    except (TypeError, ValueError):
        abort(400, 'Provide valid latitude and longitude.')
    return lat, lng

def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, 'Expected a JSON object.')
    return data

@api.errorhandler(geoapify.ProviderError)
def provider_error(error):
    return jsonify(error=str(error)), error.status

@main.get('/')
def home():
    return render_template('home.html')

@main.get('/health')
def health():
    return jsonify(status='ok', safety_scoring=False)

@api.get('/search')
def search():
    query = request.args.get('q', '').strip()
    if not 3 <= len(query) <= 160:
        abort(400, 'Search text must be 3â€“160 characters.')
    result = geoapify.fetch('v1/geocode/autocomplete', dict(text=query, filter='countrycode:in', limit=5))
    return jsonify(places=[dict(label=f['properties'].get('formatted', ''),
        lat=f['properties']['lat'], lng=f['properties']['lon']) for f in result.get('features', [])])

@api.get('/reverse')
def reverse():
    lat, lng = coordinates(request.args.get('lat'), request.args.get('lng'))
    result = geoapify.fetch('v1/geocode/reverse', dict(lat=lat, lon=lng, limit=1))
    features = result.get('features', [])
    return jsonify(label=features[0]['properties'].get('formatted', 'Current location') if features else 'Current location')

@api.post('/routes')
def routes():
    data = body()
    if data.get('mode') not in ('walk', 'bicycle', 'motorcycle', 'drive'):
        abort(400, 'Choose a supported travel mode.')
    start, end = data.get('start'), data.get('end')
    if not isinstance(start, list) or not isinstance(end, list) or len(start) != 2 or len(end) != 2:
        abort(400, 'Choose both locations from the suggestions.')
    start, end = coordinates(*start), coordinates(*end)
    if geoapify.distance(start[::-1], end[::-1]) < 20:
        abort(400, 'Choose a destination at least 20 metres from the start.')
    result = geoapify.routes(start, end, data["mode"])
    for candidate in result["routes"]:
        try:
            candidate["demo"] = analyze_demo_route(
                candidate["geometry"]
            )
        except ValueError as error:
            candidate["demo"] = {
                "is_demo": True,
                "label": "Synthetic demo â€” not verified safety information",
                "status": "DEMO_DATA_UNAVAILABLE",
                "message": str(error),
                "demo_safety_score": None,
                "demo_crime_index": None,
                "safety_score": None,
                "recommendation": None,
            }
        candidate["lighting"] = score_route_lighting(candidate)

    recommend_routes(result["routes"])

    return jsonify(result)

@api.get('/help')
def nearby():
    lat, lng = coordinates(request.args.get('lat'), request.args.get('lng'))
    supported = ('service.police', 'healthcare.hospital', 'healthcare.pharmacy')
    category = request.args.get('category')
    if category and category not in supported:
        abort(400, 'Choose a supported facility category.')
    return jsonify(places=geoapify.nearby_places(lat, lng, category))

@api.route('/reports', methods=['GET', 'POST'])
def reports():
    if request.method == 'GET':
        rows = db.session.execute(db.select(Report).filter_by(owner=owner_key()).order_by(Report.created_at.desc()).limit(100)).scalars()
        return jsonify(reports=[row.public() for row in rows])
    data = body()
    category = data.get('category')
    description = data.get('description')
    if category not in CATEGORIES or not isinstance(description, str) or not 10 <= len(description.strip()) <= 1000:
        abort(400, 'Choose a category and enter a description of 10â€“1000 characters.')
    lat, lng = coordinates(data.get('lat'), data.get('lng'))
    report = Report(id=str(uuid.uuid4()), owner=owner_key(), category=category,
                    description=description.strip(), lat=lat, lng=lng)
    db.session.add(report)
    db.session.commit()
    return jsonify(report=report.public()), 201

@api.delete('/reports/<report_id>')
def delete_report(report_id):
    row = db.session.get(Report, report_id)
    if row is None or row.owner != owner_key():
        abort(404)
    db.session.delete(row)
    db.session.commit()
    return jsonify(deleted=True)

def admin_only(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not session.get('admin_id') or db.session.get(Admin, session['admin_id']) is None:
            return redirect(url_for('admin.login'))
        return function(*args, **kwargs)
    return wrapped

@admin.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username, password = request.form.get('username', '')[:80], request.form.get('password', '')[:256]
        user = db.session.execute(db.select(Admin).filter_by(username=username)).scalar_one_or_none()
        # A dummy hash avoids skipping password-hash work for unknown users.
        stored = user.password_hash if user else 'scrypt:32768:8:1$dummy$' + '0'*128
        valid = check_password_hash(stored, password)
        if user and valid:
            visitor = session['visitor']
            session.clear()
            session.update(admin_id=user.id, visitor=visitor, csrf=secrets.token_hex(32))
            session.permanent = True
            return redirect(url_for('admin.dashboard'))
        error = 'Username or password is incorrect.'
    return render_template('login.html', error=error)

@admin.get('/')
@admin_only
def dashboard():
    rows = db.session.execute(db.select(Report).order_by(Report.created_at.desc()).limit(200)).scalars().all()
    audits = db.session.execute(db.select(Audit).order_by(Audit.created_at.desc()).limit(20)).scalars().all()
    return render_template('admin.html', reports=rows, audits=audits)

@admin.post('/reports/<report_id>')
@admin_only
def moderate(report_id):
    row = db.session.get(Report, report_id)
    if row is None:
        abort(404)
    status, reason = request.form.get('status'), request.form.get('reason', '').strip()
    if status not in ('pending', 'reviewed', 'dismissed') or not 5 <= len(reason) <= 300:
        abort(400, 'Choose a status and enter a reason of 5â€“300 characters.')
    actor = db.session.get(Admin, session['admin_id'])
    db.session.add(Audit(admin=actor.username, report_id=row.id, old_status=row.status, new_status=status, reason=reason))
    row.status = status
    db.session.commit()
    return redirect(url_for('admin.dashboard'))

@admin.post('/logout')
def logout():
    session.pop('admin_id', None)
    session['csrf'] = secrets.token_hex(32)
    return redirect(url_for('main.home'))
