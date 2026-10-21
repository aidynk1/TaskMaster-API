import io
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    database = tmp_path / "test.db"
    monkeypatch.setattr(main, "DATABASE", str(database))
    monkeypatch.setenv(
        "AUTH_TOKEN_SECRET",
        "test-secret-with-more-than-thirty-two-characters",
    )
    main.init_db()


def test_openapi_document_is_available():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "TaskMaster API"


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tasks_require_authentication(isolated_database):
    response = client.get("/tasks")

    assert response.status_code == 401


def test_login_returns_signed_token_and_username_is_not_a_token(
    isolated_database,
):
    username = "ci-user"
    password = "a-long-test-password"

    registration = client.post(
        "/register",
        json={"username": username, "password": password},
    )
    assert registration.status_code == 200

    login = client.post(
        "/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["token"]
    assert token != username

    task_list = client.get(
        "/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert task_list.status_code == 200

    forged_request = client.get(
        "/tasks",
        headers={"Authorization": f"Bearer {username}"},
    )
    assert forged_request.status_code == 401


def test_app_logger_writes_all_levels_to_console_and_file():
    logger = main.logger
    console_handler = next(
        handler
        for handler in logger.handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
    )
    file_handler = next(
        handler for handler in logger.handlers
        if isinstance(handler, logging.FileHandler)
    )
    console_output = io.StringIO()
    original_stream = console_handler.stream
    console_handler.setStream(console_output)

    try:
        logger.info("logging-test-info")
        logger.warning("logging-test-warning")
        logger.error("logging-test-error")
        console_handler.flush()
        file_handler.flush()

        console_logs = console_output.getvalue()
        file_logs = Path(file_handler.baseFilename).read_text(encoding="utf-8")
        for level, marker in (
            ("INFO", "logging-test-info"),
            ("WARNING", "logging-test-warning"),
            ("ERROR", "logging-test-error"),
        ):
            assert level in console_logs
            assert marker in console_logs
            assert level in file_logs
            assert marker in file_logs
    finally:
        console_handler.setStream(original_stream)
