"""Production boundary checks for the permanent Django architecture."""
from unittest import mock
import pytest
import db_adapter
from api.services import Identity, VoxERPService

@pytest.mark.parametrize("offline,real", [("False", "False"), ("True", "True")])
def test_production_never_uses_fixture_or_initializes_schema(monkeypatch, offline, real):
    monkeypatch.setenv("VOXERP_ENV", "production")
    monkeypatch.setenv("VOXERP_INITIALIZE_DATABASE", "True")
    monkeypatch.setenv("VOXERP_USE_REAL_DB", real)
    monkeypatch.setenv("VOXERP_OFFLINE_MODE", offline)
    with mock.patch.object(db_adapter, "initialize_database") as initialize, mock.patch.object(db_adapter, "_get_connection") as connect:
        service = VoxERPService(engine=mock.Mock())
        assert service.query(Identity("917", "student"), "my marks")["status"] == 503
        assert service.confirm(Identity("917", "student"), {}, "yes")["status"] == 503
        initialize.assert_not_called()
        connect.assert_not_called()

@pytest.mark.django_db
def test_proxy_headers_and_body_cannot_authenticate(client):
    response = client.post("/api/query/", data={"text": "my marks", "user_id": "917", "role": "teacher"}, content_type="application/json", HTTP_X_FORWARDED_USER="917", HTTP_X_FORWARDED_GROUPS="teacher")
    assert response.status_code == 302

@pytest.mark.django_db
def test_login_and_csrf(django_user_model):
    from django.test import Client
    django_user_model.objects.create_user(username="917", password="test-password")
    client = Client(enforce_csrf_checks=True)
    client.get("/login/")
    token = client.cookies["csrftoken"].value
    response = client.post("/login/", {"username": "917", "password": "test-password", "csrfmiddlewaretoken": token})
    assert response.status_code == 302
    assert response.url == "/"
    assert client.get("/users").status_code == 200
    assert client.post("/api/query/", data={"text": "my marks"}, content_type="application/json").status_code == 403

@pytest.mark.django_db
def test_errors_are_generic(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="917"))
    with mock.patch("api.views.service.query", side_effect=RuntimeError("secret-database-password")):
        response = client.post("/api/query/", data={"text": "my marks"}, content_type="application/json")
    assert response.status_code == 500
    assert "secret-database-password" not in response.content.decode()
