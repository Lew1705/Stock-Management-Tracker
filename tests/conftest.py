import sys
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture()
def isolated_db(monkeypatch):
    from stock import db

    temp_root = Path(tempfile.gettempdir()) / f"stock-tests-{uuid.uuid4()}"
    temp_root.mkdir(parents=True, exist_ok=True)
    db_path = temp_root / "test-stock.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.seed_locations()
    try:
        yield db_path
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.fixture()
def app(isolated_db):
    from stock.web import app as flask_app

    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
    )
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
