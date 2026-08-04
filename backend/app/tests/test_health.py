import pytest
from fastapi.testclient import TestClient

from app import main


app = main.app


def test_health_endpoint_returns_safe_json() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


def test_startup_prints_started_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(main, "init_risk_engine_storage", lambda: None)

    main.startup()

    assert capsys.readouterr().out == "Website just started\n"
