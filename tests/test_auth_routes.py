"""
tests/test_auth_routes.py — Unit tests for auth session management routes.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


@pytest.mark.unit
class TestAuthRefresh:
    def test_refresh_requires_cookie(self) -> None:
        response = client.post("/auth/refresh")
        assert response.status_code == 401
        assert response.json()["detail"] == "Session expired. Sign in again."

    def test_refresh_returns_new_session_and_sets_cookies(self) -> None:
        mock_session = SimpleNamespace(access_token="new-access", refresh_token="new-refresh")
        mock_user = SimpleNamespace(id="user-123", email="user@example.com")
        mock_auth_response = SimpleNamespace(session=mock_session, user=mock_user)

        mock_supabase = MagicMock()
        mock_supabase.auth.refresh_session.return_value = mock_auth_response

        with patch("src.api.routes.auth.create_client", return_value=mock_supabase):
            client.cookies.set("session_refresh", "stale-refresh")
            response = client.post("/auth/refresh")
            client.cookies.clear()

        assert response.status_code == 200
        assert response.json() == {"user_id": "user-123", "email": "user@example.com"}
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any("session=new-access" in header for header in set_cookie_headers)
        assert any("session_refresh=new-refresh" in header for header in set_cookie_headers)

    def test_refresh_failure_clears_cookies(self) -> None:
        mock_supabase = MagicMock()
        mock_supabase.auth.refresh_session.side_effect = RuntimeError("expired")

        with patch("src.api.routes.auth.create_client", return_value=mock_supabase):
            client.cookies.set("session_refresh", "stale-refresh")
            response = client.post("/auth/refresh")
            client.cookies.clear()

        assert response.status_code == 401
        set_cookie_headers = response.headers.get_list("set-cookie")
        assert any(
            'session=""' in header or ("session=" in header and "Max-Age=0" in header)
            for header in set_cookie_headers
        )
        assert any(
            'session_refresh=""' in header
            or ("session_refresh=" in header and "Max-Age=0" in header)
            for header in set_cookie_headers
        )
