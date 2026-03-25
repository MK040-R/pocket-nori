"""Unit tests for the entities directory route."""

from types import SimpleNamespace
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


def _make_db() -> MagicMock:
    return MagicMock()


@pytest.mark.unit
class TestEntitiesList:
    def setup_method(self) -> None:
        _override_auth()

    def teardown_method(self) -> None:
        _clear_auth()

    def test_groups_duplicate_entities(self) -> None:
        db = _make_db()
        with (
            patch("src.api.routes.entities.get_client", return_value=db),
            patch(
                "src.api.routes.entities.load_entity_nodes",
                return_value=[
                    SimpleNamespace(
                        name="OpenAI",
                        entity_type="company",
                        mention_count=5,
                        conversation_ids=["conv-1", "conv-2"],
                    ),
                    SimpleNamespace(
                        name="Murali Krishna Yamsani",
                        entity_type="person",
                        mention_count=4,
                        conversation_ids=["conv-2"],
                    ),
                ],
            ),
        ):
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
        db = _make_db()
        with (
            patch("src.api.routes.entities.get_client", return_value=db),
            patch(
                "src.api.routes.entities.load_entity_nodes",
                return_value=[
                    SimpleNamespace(
                        name="Opus",
                        entity_type="company",
                        mention_count=7,
                        conversation_ids=["conv-1", "conv-2"],
                    ),
                    SimpleNamespace(
                        name="N8N",
                        entity_type="product",
                        mention_count=3,
                        conversation_ids=["conv-1", "conv-3"],
                    ),
                ],
            ),
        ):
            response = client.get("/entities")

        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "Opus",
                "type": "company",
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
        db = _make_db()
        with (
            patch("src.api.routes.entities.get_client", return_value=db),
            patch(
                "src.api.routes.entities.load_entity_nodes",
                return_value=[
                    SimpleNamespace(
                        name="Nabil Mansouri",
                        entity_type="person",
                        mention_count=5,
                        conversation_ids=["conv-1", "conv-2"],
                    ),
                    SimpleNamespace(
                        name="Murali Krishna Yamsani",
                        entity_type="person",
                        mention_count=2,
                        conversation_ids=["conv-3"],
                    ),
                ],
            ),
        ):
            response = client.get("/entities")

        assert response.status_code == 200
        assert response.json()[0] == {
            "name": "Nabil Mansouri",
            "type": "person",
            "mentions": 5,
            "conversation_count": 2,
        }

    def test_applies_limit_and_offset(self) -> None:
        db = _make_db()
        with (
            patch("src.api.routes.entities.get_client", return_value=db),
            patch(
                "src.api.routes.entities.load_entity_nodes",
                return_value=[
                    SimpleNamespace(
                        name="B",
                        entity_type="company",
                        mention_count=4,
                        conversation_ids=["conv-1"],
                    )
                ],
            ),
        ):
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
