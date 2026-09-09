"""Ordinary pytest is SQLite-only. Live READ validation uses a separate command."""
import os
import socket
import sys
import mariadb

os.environ["VOXERP_USE_REAL_DB"] = "False"
os.environ["VOXERP_ALLOW_REAL_WRITES"] = "False"
os.environ["VOXERP_INITIALIZE_DATABASE"] = "False"
os.environ["VOXERP_ENV"] = "development"
os.environ["VOXERP_OFFLINE_MODE"] = "True"
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

def pytest_sessionfinish(session, exitstatus):
    if _attempts or any(name in sys.modules for name in ("transaction_test", "transaction_engine_test")):
        session.exitstatus = 1
    print("\nNetwork/MariaDB attempts:", len(_attempts))
    mariadb.connect = _original_connect
    socket.socket.connect = _original_socket_connect
