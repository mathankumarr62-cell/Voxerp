"""Safety boundaries of the local restore/run helper; no live connections."""
import json

import pytest

from scripts import local_demo


def test_demo_environment_overrides_unsafe_inherited_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(local_demo, 'STATE', tmp_path)
    (tmp_path / 'environment.json').write_text(json.dumps({
        'DB_HOST': '127.0.0.1', 'DB_PORT': '3307', 'DB_USER': 'voxerp_demo'}))
    for key, value in {'DB_HOST': 'remote', 'VOXERP_ALLOW_REAL_WRITES': 'True',
                       'VOXERP_USE_REAL_DB': 'False', 'VOXERP_OFFLINE_MODE': 'True'}.items():
        monkeypatch.setenv(key, value)
    env = local_demo.environment()
    assert env['DB_HOST'] == '127.0.0.1'
    assert env['VOXERP_USE_REAL_DB'] == 'True'
    assert env['VOXERP_ALLOW_REAL_WRITES'] == 'False'
    assert env['VOXERP_OFFLINE_MODE'] == 'False'
    assert env['VOXERP_APP_DB'] == str(tmp_path / 'auth.sqlite3')


def test_demo_rejects_nonlocal_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(local_demo, 'STATE', tmp_path)
    (tmp_path / 'environment.json').write_text(json.dumps({'DB_HOST': 'remote', 'DB_PORT': '3307'}))
    with pytest.raises(RuntimeError, match='nonlocal'):
        local_demo.environment()


def test_initialization_preserves_existing_state(tmp_path, monkeypatch):
    dump = tmp_path / 'authorized.sql'
    dump.write_text('-- dump')
    state = tmp_path / 'existing'
    state.mkdir()
    marker = state / 'keep'
    marker.write_text('untouched')
    monkeypatch.setattr(local_demo, 'STATE', state)
    with pytest.raises(RuntimeError, match='overwrite'):
        local_demo.initialize(dump)
    assert marker.read_text() == 'untouched'
