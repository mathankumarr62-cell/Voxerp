"""Ordinary pytest is SQLite-only. Live READ validation uses a separate command."""
import os
import socket
import sys
import mariadb

os.environ["VOXERP_USE_REAL_DB"] = "False"
os.environ["VOXERP_ALLOW_REAL_WRITES"] = "False"
os.environ["VOXERP_INITIALIZE_DATABASE"] = "False"
os.environ["VOXERP_ENV"] = "development"
os.environ["VOXERP_OFFLINE_MODE"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_attempts = []
_original_connect = mariadb.connect
_original_socket_connect = socket.socket.connect

def _blocked(*args, **kwargs):
    _attempts.append(True)
    raise AssertionError("Network/MariaDB access is forbidden in ordinary pytest")

mariadb.connect = _blocked
socket.socket.connect = _blocked

import pytest


@pytest.fixture(autouse=True)
def isolated_academic_database(tmp_path, monkeypatch, request):
    if request.cls and hasattr(request.cls, "_test_db_file"):
        return  # This adapter test class owns its own database lifecycle.
    import db_adapter
    monkeypatch.setattr(db_adapter, "_DB_FILE", str(tmp_path / "academic.sqlite3"))
    db_adapter.initialize_database()

def pytest_sessionfinish(session, exitstatus):
    if _attempts or any(name in sys.modules for name in ("transaction_test", "transaction_engine_test")):
        session.exitstatus = 1
    print("\nNetwork/MariaDB attempts:", len(_attempts))
    mariadb.connect = _original_connect
    socket.socket.connect = _original_socket_connect
