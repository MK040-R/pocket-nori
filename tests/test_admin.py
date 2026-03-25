"""Unit tests for maintenance admin routes."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-admin-test",
    "email": "admin@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
class TestAdminJobStatus:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_returns_pending_job_status(self) -> None:
        fake_result = MagicMock()
        fake_result.state = "PENDING"
        fake_result.info = None
        fake_result.result = None
        with patch("src.api.routes.admin.AsyncResult", return_value=fake_result):
            response = client.get("/admin/jobs/job-123")

        assert response.status_code == 200
        assert response.json() == {"job_id": "job-123", "status": "pending", "detail": None, "result": None}

    def test_returns_progress_job_status(self) -> None:
        fake_result = MagicMock()
        fake_result.state = "PROGRESS"
        fake_result.info = {"status": "rebuilding_nodes_lexical", "user_id": "user-admin-test"}
        fake_result.result = None
        with patch("src.api.routes.admin.AsyncResult", return_value=fake_result):
            response = client.get("/admin/jobs/job-123")

        assert response.status_code == 200
        assert response.json()["status"] == "progress"
        assert response.json()["detail"] == "rebuilding_nodes_lexical"

    def test_rejects_progress_job_from_another_user(self) -> None:
        fake_result = MagicMock()
        fake_result.state = "PROGRESS"
        fake_result.info = {"status": "rebuilding_nodes_lexical", "user_id": "other-user"}
        fake_result.result = None
        with patch("src.api.routes.admin.AsyncResult", return_value=fake_result):
            response = client.get("/admin/jobs/job-123")

        assert response.status_code == 403

    def test_returns_success_job_status(self) -> None:
        fake_result = MagicMock()
        fake_result.state = "SUCCESS"
        fake_result.info = None
        fake_result.result = {"user_id": "user-admin-test", "topic_count": 3}
        with patch("src.api.routes.admin.AsyncResult", return_value=fake_result):
            response = client.get("/admin/jobs/job-123")

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["result"] == {"user_id": "user-admin-test", "topic_count": 3}

    def test_returns_failure_job_status(self) -> None:
        fake_result = MagicMock()
        fake_result.state = "FAILURE"
        fake_result.info = None
        fake_result.result = RuntimeError("boom")
        with patch("src.api.routes.admin.AsyncResult", return_value=fake_result):
            response = client.get("/admin/jobs/job-123")

        assert response.status_code == 200
        assert response.json()["status"] == "failure"
        assert "boom" in response.json()["detail"]
