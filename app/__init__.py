import hashlib
import hmac
import os
import secrets
import time
from collections import OrderedDict, deque
from datetime import timedelta
from pathlib import Path
from threading import Lock

import click
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash
from .models import db, Admin

def create_app(test_config=None):
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY', ''),
        GEOAPIFY_API_KEY=os.getenv('GEOAPIFY_API_KEY', ''),
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///safewalk.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=16*1024,
    )
    if test_config:
        app.config.update(test_config)
    database_url = app.config['SQLALCHEMY_DATABASE_URI']
    if database_url.startswith(('postgres://', 'postgresql://')):
        database_url = 'postgresql+psycopg://' + database_url.split('://', 1)[1]
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    if os.getenv('VERCEL') == '1' and not app.testing:
        if not database_url.startswith('postgresql+psycopg://'):
            raise RuntimeError('On Vercel, set DATABASE_URL to a hosted PostgreSQL connection string.')
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    secret = app.config['SECRET_KEY']
    if not secret or len(secret) < 32 or secret.startswith('replace-'):
        raise RuntimeError('Set FLASK_SECRET_KEY in .env to at least 32 random characters. See README.md.')
    # Create the local instance directory only when running locally.
    if not os.getenv("VERCEL"):
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    if not os.getenv("VERCEL"):
        with app.app_context():
            db.create_all()
    buckets, lock = OrderedDict(), Lock()
    @app.before_request
    def guard():
        if 'visitor' not in session:
            session['visitor'] = secrets.token_hex(24)
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not hmac.compare_digest(supplied, session['csrf']):
                abort(400, 'Session expired or invalid form token. Reload the page.')
        limited = request.path.startswith('/api/') or (request.path == '/admin/login' and request.method == 'POST')
        if limited and not app.testing:
            # IP keys prevent cookie resetting from bypassing this single-process limiter.
            kind = 'login' if request.path == '/admin/login' else request.path
            key = (request.remote_addr, kind)
            window = 3600 if kind in ('login', '/api/routes', '/api/reports') else 60
            limit = 10 if kind == 'login' else (30 if kind in ('/api/routes', '/api/reports') else 60)
            tick = time.monotonic()
            with lock:
                queue = buckets.setdefault(key, deque())
                while queue and queue[0] <= tick-window:
                    queue.popleft()
                if len(queue) >= limit:
                    abort(429, 'Too many requests. Please try again later.')
                queue.append(tick)
                buckets.move_to_end(key)
                while len(buckets) > 4096:
                    buckets.popitem(last=False)

    @app.context_processor
    def template_tokens():
        static_folder = Path(app.static_folder)
        asset_version = max(
            (static_folder / filename).stat().st_mtime_ns
            for filename in ('app.js', 'style.css')
        )
        return dict(csrf=session.get('csrf', ''), asset_version=asset_version)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(self)'
        if request.path.startswith(('/api/', '/admin')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error=error.description), error.code
        return error

    @app.cli.command('create-admin')
    @click.option('--username', prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin(username, password):
        """Create an admin or reset an existing admin's password."""
        username = username.strip()
        if not 1 <= len(username) <= 80 or len(password) < 12:
            raise click.ClickException('Use a username of 1–80 characters and a password of at least 12 characters.')
        admin = db.session.execute(db.select(Admin).filter_by(username=username)).scalar_one_or_none()
        if admin is None:
            admin = Admin(username=username)
            db.session.add(admin)
        admin.password_hash = generate_password_hash(password)
        db.session.commit()
        click.echo('Admin account saved. Sign in at /admin/login.')

    from .routes import api, main, admin
    app.register_blueprint(api)
    app.register_blueprint(main)
    app.register_blueprint(admin)
    return app

def owner_key():
    # Database never contains the visitor's usable session token.
    return hashlib.sha256(session['visitor'].encode()).hexdigest()
