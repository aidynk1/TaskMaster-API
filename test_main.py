from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_openapi_document_is_available():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "TaskMaster API"


def test_tasks_require_authentication():
    response = client.get("/tasks")

    assert response.status_code == 401
