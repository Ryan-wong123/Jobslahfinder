from fastapi.testclient import TestClient

from app.main import app


def test_backend_validation_errors_return_generic_message() -> None:
    with TestClient(app) as client:
        response = client.get("/jobs", params={"page": 0})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}


def test_backend_invalid_path_parameters_return_generic_message() -> None:
    with TestClient(app) as client:
        response = client.get("/jobs/0")

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}


def test_backend_register_rejects_unknown_fields_without_schema_leakage() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "new-user@example.com",
                "password": "StrongPass123",
                "role": "ADMIN",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
