from fastapi.testclient import TestClient
from src.api.server import app


def test_admin_invitation_validation_does_not_leak_exception_text(monkeypatch):
    client = TestClient(app)
    response = client.get("/api/v1/admin-invitations/validate/invalid-token")
    body = response.json()

    # Adjust path key if wrapped in {"data": ...}
    text = str(body)
    assert "Traceback" not in text
    assert "NotImplementedError" not in text
    assert "sqlalchemy" not in text.lower()