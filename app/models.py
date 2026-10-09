import importlib.abc
import importlib.machinery
import importlib.util
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path


class _PythonOnlySQLAlchemyCythonFinder(importlib.abc.MetaPathFinder):
    """Use the Python fallback modules when Windows blocks SQLAlchemy .pyd files."""

    _MODULES = {
        'sqlalchemy.engine._util_cy': '_util_cy.py',
        'sqlalchemy.engine._processors_cy': '_processors_cy.py',
        'sqlalchemy.engine._result_cy': '_result_cy.py',
        'sqlalchemy.engine._row_cy': '_row_cy.py',
    }

    @staticmethod
    def _engine_dir():
        for name in ('purelib', 'platlib'):
            value = sysconfig.get_paths().get(name)
            if value:
                candidate = Path(value) / 'sqlalchemy' / 'engine'
                if candidate.exists():
                    return candidate
        return None

    def find_spec(self, fullname, path=None, target=None):
        source = self._MODULES.get(fullname)
        if source is None:
            return None
        engine_dir = self._engine_dir()
        if engine_dir is None:
            return None
        module_path = engine_dir / source
        if not module_path.exists():
            return None
        return importlib.util.spec_from_file_location(
            fullname,
            str(module_path),
            loader=importlib.machinery.SourceFileLoader(fullname, str(module_path)),
        )


if not any(isinstance(finder, _PythonOnlySQLAlchemyCythonFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _PythonOnlySQLAlchemyCythonFinder())

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
