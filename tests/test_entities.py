"""Unit tests for the entities directory route."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app

client = TestClient(app)

_FAKE_USER_PAYLOAD: dict[str, Any] = {
    "sub": "user-entities-test",
    "email": "entities@example.com",
    "_raw_jwt": "fake.jwt.token",
}


def _override_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER_PAYLOAD


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _make_db(rows: list[dict[str, Any]]) -> MagicMock:
    entities_table = MagicMock()
    entities_table.select.return_value.eq.return_value.order.return_value.execute.return_value.data = rows

    db = MagicMock()
    db.table.return_value = entities_table
    return db


@pytest.mark.unit
class TestEntitiesList:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_groups_duplicate_entities(self) -> None:
        db = _make_db(
            [
                {
                    "name": "OpenAI",
                    "type": "company",
                    "mentions": 3,
                    "conversation_id": "conv-1",
                },
                {
                    "name": "openai",
                    "type": "company",
                    "mentions": 2,
                    "conversation_id": "conv-2",
                },
                {
                    "name": "Murali Krishna Yamsani",
                    "type": "person",
                    "mentions": 4,
                    "conversation_id": "conv-2",
                },
            ]
        )

        with patch("src.api.routes.entities.get_client", return_value=db):
            response = client.get("/entities")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0] == {
            "name": "OpenAI",
            "type": "company",
            "mentions": 5,
            "conversation_count": 2,
        }
        assert payload[1]["name"] == "Murali Krishna Yamsani"

    def test_merges_brand_aliases_and_company_product_variants(self) -> None:
        db = _make_db(
            [
                {
                    "name": "Opus",
                    "type": "product",
                    "mentions": 4,
                    "conversation_id": "conv-1",
                },
                {
                    "name": "Opus",
                    "type": "company",
                    "mentions": 3,
                    "conversation_id": "conv-2",
                },
                {
                    "name": "N8",
                    "type": "product",
                    "mentions": 2,
                    "conversation_id": "conv-1",
                },
                {
                    "name": "N8N",
                    "type": "product",
                    "mentions": 1,
                    "conversation_id": "conv-3",
                },
            ]
        )

        with patch("src.api.routes.entities.get_client", return_value=db):
            response = client.get("/entities")

        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "Opus",
                "type": "company/product",
                "mentions": 7,
                "conversation_count": 2,
            },
            {
                "name": "N8N",
                "type": "product",
                "mentions": 3,
                "conversation_count": 2,
            },
        ]

    def test_merges_unambiguous_short_form_people(self) -> None:
        db = _make_db(
            [
                {
                    "name": "Nabil Mansouri",
                    "type": "person",
                    "mentions": 4,
                    "conversation_id": "conv-1",
                },
                {
                    "name": "Nabil",
                    "type": "person",
                    "mentions": 1,
                    "conversation_id": "conv-2",
                },
                {
                    "name": "Murali Krishna Yamsani",
                    "type": "person",
                    "mentions": 2,
                    "conversation_id": "conv-3",
                },
            ]
        )

        with patch("src.api.routes.entities.get_client", return_value=db):
            response = client.get("/entities")

        assert response.status_code == 200
        assert response.json()[0] == {
            "name": "Nabil Mansouri",
            "type": "person",
            "mentions": 5,
            "conversation_count": 2,
        }

    def test_applies_limit_and_offset(self) -> None:
        db = _make_db(
            [
                {"name": "A", "type": "company", "mentions": 5, "conversation_id": "conv-1"},
                {"name": "B", "type": "company", "mentions": 4, "conversation_id": "conv-1"},
                {"name": "C", "type": "company", "mentions": 3, "conversation_id": "conv-1"},
            ]
        )

        with patch("src.api.routes.entities.get_client", return_value=db):
            response = client.get("/entities?limit=1&offset=1")

        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "B",
                "type": "company",
                "mentions": 4,
                "conversation_count": 1,
            }
        ]
