"""Hermetic HTTP contract tests for the canonical Production Asset bridge."""
from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from api.server import app
from models import Session, StoryboardShot, init_db


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), (32, 64, 96)).save(output, format="PNG")
    return output.getvalue()


def _shot(book_id: int) -> StoryboardShot:
    with Session() as session:
        row = StoryboardShot(
            book_id=book_id,
            episode=1,
            scene_name="Canonical scene",
            scene_id="SCENE_CANONICAL",
            shot_id=1,
            asset_links='{"production_asset_requirements":[{"asset_type":"CHARACTER","entity_id":"CHARACTER_CANONICAL"},{"asset_type":"SCENE","entity_id":"SCENE_CANONICAL"}]}',
        )
        session.add(row)
        session.commit()
        return int(row.id)


def _ingest(client: TestClient, book_id: int, asset_type: str, entity_id: str):
    return client.post(
        f"/api/books/{book_id}/production-assets/ingest",
        data={"assetType": asset_type, "entityId": entity_id, "metadata": "{}"},
        files={"file": (f"{entity_id}.png", _png(), "image/png")},
    )


def test_production_asset_ingestion_review_activation_and_binding_are_explicit():
    init_db()
    book_id = 880000 + (uuid.uuid4().int % 10000)
    shot = _shot(book_id)
    client = TestClient(app)

    invalid = client.post(
        f"/api/books/{book_id}/production-assets/ingest",
        data={"assetType": "CHARACTER", "entityId": "UNKNOWN", "metadata": "{}"},
        files={"file": ("x.png", _png(), "image/png")},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "CANONICAL_ENTITY_REQUIREMENT_NOT_FOUND"

    character = _ingest(client, book_id, "CHARACTER", "CHARACTER_CANONICAL")
    scene = _ingest(client, book_id, "SCENE", "SCENE_CANONICAL")
    assert character.status_code == scene.status_code == 201
    character_payload = character.json()
    assert character_payload["pointer_activated"] is False
    assert character_payload["version"]["pointer_activated"] is False
    assert character_payload["review_state"] == "HUMAN_REVIEW_PENDING"
    assert [item["to"] for item in character_payload["history"]] == ["GENERATED", "NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING"]
    assert character_payload["provider_calls"] == character_payload["llm_calls"] == 0

    review_id = character_payload["review"]["review_id"]
    blocked = client.post(f"/api/books/{book_id}/production-assets/reviews/{review_id}/activate")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PRODUCTION_REVIEW_REQUIRED"

    rejected = client.post(
        f"/api/books/{book_id}/production-assets/reviews/{review_id}/decision",
        json={"decision": "REJECT", "reviewer_type": "DIRECTOR", "comment": "needs another take"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["pointer_activated"] is False

    # A new version can be reviewed independently; approval is the only path
    # that may move the pointer.
    replacement = _ingest(client, book_id, "CHARACTER", "CHARACTER_CANONICAL")
    assert replacement.status_code == 201
    approved_review = replacement.json()["review"]["review_id"]
    approved = client.post(
        f"/api/books/{book_id}/production-assets/reviews/{approved_review}/decision",
        json={"decision": "APPROVE", "reviewer_type": "DIRECTOR"},
    )
    assert approved.status_code == 200
    activated = client.post(f"/api/books/{book_id}/production-assets/reviews/{approved_review}/activate")
    assert activated.status_code == 200
    assert activated.json()["pointer_activated"] is True

    scene_payload = scene.json()
    scene_review = scene_payload["review"]["review_id"]
    assert client.post(
        f"/api/books/{book_id}/production-assets/reviews/{scene_review}/decision",
        json={"decision": "APPROVE", "reviewer_type": "ART_DIRECTOR"},
    ).status_code == 200
    assert client.post(f"/api/books/{book_id}/production-assets/reviews/{scene_review}/activate").status_code == 200

    binding = client.post(
        f"/api/books/{book_id}/production-assets/bindings",
        json={
            "storyboardShotId": shot,
            "characters": [{"authority_id": replacement.json()["version"]["authority_id"], "version_id": replacement.json()["version"]["version_id"]}],
            "scene": {"authority_id": scene_payload["version"]["authority_id"], "version_id": scene_payload["version"]["version_id"]},
            "props": [],
        },
    )
    assert binding.status_code == 200
    assert binding.json()["current"] is True
