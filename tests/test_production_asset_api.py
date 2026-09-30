"""Hermetic HTTP contract tests for the canonical Production Asset bridge."""
from __future__ import annotations

import io
import json
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from api.server import app
from models import Session, StoryboardShot, init_db


def _png(color=(32, 64, 96)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(output, format="PNG")
    return output.getvalue()


def _shot(book_id: int) -> StoryboardShot:
    return _shot_with_entities(book_id, "CHARACTER_CANONICAL", "SCENE_CANONICAL")


def _shot_with_entities(book_id: int, character_id: str, scene_id: str) -> StoryboardShot:
    with Session() as session:
        row = StoryboardShot(
            book_id=book_id,
            episode=1,
            scene_name="Canonical scene",
            scene_id=scene_id,
            shot_id=1,
            asset_links=json.dumps({"production_asset_requirements": [{"asset_type": "CHARACTER", "entity_id": character_id}, {"asset_type": "SCENE", "entity_id": scene_id}]}),
        )
        session.add(row)
        session.commit()
        return int(row.id)


def _ingest(client: TestClient, book_id: int, asset_type: str, entity_id: str, data: bytes | None = None):
    return client.post(
        f"/api/books/{book_id}/production-assets/ingest",
        data={"assetType": asset_type, "entityId": entity_id, "metadata": "{}"},
        files={"file": (f"{entity_id}.png", data or _png(), "image/png")},
    )


def _approve_activate(client: TestClient, book_id: int, review_id: str):
    assert client.post(f"/api/books/{book_id}/production-assets/reviews/{review_id}/decision", json={"decision": "APPROVE", "reviewer_type": "DIRECTOR"}).status_code == 200
    return client.post(f"/api/books/{book_id}/production-assets/reviews/{review_id}/activate")


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


def test_production_asset_bridge_state_recovers_pending_activation_and_bind_current():
    init_db()
    book_id = 881000 + (uuid.uuid4().int % 10000)
    character_id = f"CHARACTER_BRIDGE_{uuid.uuid4().hex[:8]}"
    scene_id = f"SCENE_BRIDGE_{uuid.uuid4().hex[:8]}"
    shot = _shot_with_entities(book_id, character_id, scene_id)
    client = TestClient(app)
    character = _ingest(client, book_id, "CHARACTER", character_id)
    scene = _ingest(client, book_id, "SCENE", scene_id)
    assert character.status_code == scene.status_code == 201
    state = client.get(f"/api/books/{book_id}/production-assets/shots/{shot}/bridge-state")
    assert state.status_code == 200
    by_type = {item["asset_type"]: item for item in state.json()["requirements"]}
    assert by_type["CHARACTER"]["requirement_status"] == "REVIEW_PENDING"
    assert by_type["CHARACTER"]["pending_review_id"]

    character_review = character.json()["review"]["review_id"]
    assert client.post(f"/api/books/{book_id}/production-assets/reviews/{character_review}/decision", json={"decision": "APPROVE", "reviewer_type": "DIRECTOR"}).status_code == 200
    state = client.get(f"/api/books/{book_id}/production-assets/shots/{shot}/bridge-state").json()
    assert next(item for item in state["requirements"] if item["asset_type"] == "CHARACTER")["requirement_status"] == "HUMAN_APPROVED_NOT_ACTIVATED"
    assert client.post(f"/api/books/{book_id}/production-assets/reviews/{character_review}/activate").status_code == 200
    state = client.get(f"/api/books/{book_id}/production-assets/shots/{shot}/bridge-state").json()
    assert next(item for item in state["requirements"] if item["asset_type"] == "CHARACTER")["requirement_status"] == "CURRENT_NOT_BOUND"
    assert client.post(f"/api/books/{book_id}/production-assets/shots/{shot}/bind-current").status_code == 409

    _approve_activate(client, book_id, scene.json()["review"]["review_id"])
    bound = client.post(f"/api/books/{book_id}/production-assets/shots/{shot}/bind-current")
    assert bound.status_code == 200
    assert bound.json()["asset_readiness"]["current"] is True
    workspace = client.get(f"/api/books/{book_id}/production-workspace-v2")
    assert workspace.status_code == 200
    assert workspace.json()["provider_calls"] == 0
    state = client.get(f"/api/books/{book_id}/production-assets/shots/{shot}/bridge-state").json()
    assert state["binding_current"] is True
    assert {item["requirement_status"] for item in state["requirements"]} == {"BOUND_CURRENT"}

    replacement = _ingest(client, book_id, "CHARACTER", character_id, _png((120, 20, 30)))
    assert replacement.status_code == 201
    _approve_activate(client, book_id, replacement.json()["review"]["review_id"])
    stale = client.get(f"/api/books/{book_id}/production-assets/shots/{shot}/bridge-state").json()
    character_state = next(item for item in stale["requirements"] if item["asset_type"] == "CHARACTER")
    assert character_state["requirement_status"] == "BINDING_STALE"
    assert character_state["can_bind"] is True
    rebound = client.post(f"/api/books/{book_id}/production-assets/shots/{shot}/bind-current")
    assert rebound.status_code == 200
    assert rebound.json()["asset_readiness"]["current"] is True


def test_production_asset_http_scope_and_server_path_boundary():
    init_db()
    book_a = 882000 + (uuid.uuid4().int % 10000)
    book_b = book_a + 1
    character_id = f"CHARACTER_SCOPE_{uuid.uuid4().hex[:8]}"
    shot = _shot_with_entities(book_a, character_id, f"SCENE_SCOPE_{uuid.uuid4().hex[:8]}")
    client = TestClient(app)
    created = _ingest(client, book_a, "CHARACTER", character_id)
    assert created.status_code == 201
    payload = created.json()
    review_id = payload["review"]["review_id"]
    version_id = payload["version"]["version_id"]
    for path, method, body in [
        (f"/api/books/{book_b}/production-assets/reviews/{review_id}", "get", None),
        (f"/api/books/{book_b}/production-assets/reviews/{review_id}/history", "get", None),
        (f"/api/books/{book_b}/production-assets/reviews/{review_id}/validate", "post", None),
        (f"/api/books/{book_b}/production-assets/reviews/{review_id}/decision", "post", {"decision": "APPROVE", "reviewer_type": "DIRECTOR"}),
        (f"/api/books/{book_b}/production-assets/reviews/{review_id}/activate", "post", None),
        (f"/api/books/{book_b}/production-assets/versions/{version_id}/media", "get", None),
    ]:
        response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert response.status_code in {404, 409}, (path, response.status_code, response.text)

    before = client.get(f"/api/books/{book_a}/production-assets/shots/{shot}/bridge-state").json()
    no_file = client.post(
        f"/api/books/{book_a}/production-assets/ingest",
        data={"assetType": "CHARACTER", "entityId": character_id, "storageIdentity": "C:\\Windows\\win.ini", "metadata": "{}"},
    )
    assert no_file.status_code == 422
    after = client.get(f"/api/books/{book_a}/production-assets/shots/{shot}/bridge-state").json()
    assert len(after["requirements"]) == len(before["requirements"])
    assert after["requirements"][0]["latest_version"]["version_id"] == before["requirements"][0]["latest_version"]["version_id"]
