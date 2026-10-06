from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def now():
    return datetime.now(timezone.utc)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Report(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    owner = db.Column(db.String(64), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)

    def public(self):
        return dict(id=self.id, category=self.category, description=self.description,
                    lat=self.lat, lng=self.lng, status=self.status,
                    created_at=self.created_at.isoformat())

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin = db.Column(db.String(80), nullable=False)
    report_id = db.Column(db.String(36), nullable=False)
    old_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)
