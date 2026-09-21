"""Focused Phase E revision and VisualAssetPointer integrity contracts."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.prompt_ir_phase_e import classify_prompt_ir_compile_transition, compare_prompt_ir_lineage_to_current, compile_storyboard_snapshot_to_prompt_ir
from core.visual_asset_authority import VisualAssetAuthorityError, resolve_current_visual_asset_authority


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **filters):
        return _Query([row for row in self.rows if all(getattr(row, key, None) == value for key, value in filters.items())])

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, pointers, versions):
        self.pointers = pointers
        self.versions = versions

    def query(self, model):
        return _Query(self.pointers if model.__name__ == "VisualAssetPointer" else self.versions)


def _chain(*, pointer_stale="FRESH", version_stale="FRESH", pointer_hash="hash", version_key="book:1:prop:P1", pointer_key="book:1:prop:P1", pointer_asset_type="prop", pointer_scope_key=None, pointer_version_id=7):
    pointer = SimpleNamespace(book_id=1, asset_key=pointer_key, asset_type=pointer_asset_type, scope_key=pointer_scope_key or pointer_key + "@canonical", current_version_id=pointer_version_id, payload_hash=pointer_hash, authority_status="SPEC_APPROVED", stale_status=pointer_stale)
    version = SimpleNamespace(id=7, book_id=1, asset_key=version_key, asset_type="prop", scope_json="{}", payload_hash="hash", authority_status="SPEC_APPROVED", stale_status=version_stale)
    return _Session([pointer], [version])


def test_transition_classifier_distinguishes_reuse_and_revision():
    current = {"payload_hash": "same"}
    assert classify_prompt_ir_compile_transition(current_payload=current, expected_payload={"payload_hash": "same"}) == "REUSE"
    assert classify_prompt_ir_compile_transition(current_payload=current, expected_payload={"payload_hash": "new"}) == "REVISION"


def test_lineage_validator_separates_currentness_from_stored_tamper():
    from tests.test_prompt_ir_phase_e_semantic_closure import _snapshots

    snapshot = _snapshots()[0]
    policy = {"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}
    stored = compile_storyboard_snapshot_to_prompt_ir(snapshot, generation_policy=policy, allow_default_policy=False)[0]
    current = compare_prompt_ir_lineage_to_current(stored_payload=stored, current_snapshot=snapshot, asset_authority={"bindings": []})
    assert current["current_lineage_valid"] is True
    tampered = json.loads(json.dumps(stored))
    tampered["camera"]["movement"] = "TAMPERED"
    result = compare_prompt_ir_lineage_to_current(stored_payload=tampered, current_snapshot=snapshot, asset_authority={"bindings": []})
    # Currentness intentionally does not infer semantic tamper.  The stored
    # object must be checked by the historical-integrity validator first.
    assert result["tampered"] is False
    assert result["obsolete_due_to_upstream_change"] is False


def test_visual_asset_pointer_current_chain_passes():
    result = resolve_current_visual_asset_authority(_chain(), book_id=1, asset_key="book:1:prop:P1", expected_asset_type="prop")
    assert result["integrity_valid"] is True
    assert result["version"].id == 7


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stale", "VISUAL_ASSET_POINTER_STALE"),
        ("hash", "VISUAL_ASSET_POINTER_TAMPERED"),
        ("missing", "VISUAL_ASSET_POINTER_INVALID"),
        ("wrong", "VISUAL_ASSET_POINTER_TAMPERED"),
        ("wrong_type", "VISUAL_ASSET_POINTER_TAMPERED"),
        ("wrong_scope", "VISUAL_ASSET_POINTER_TAMPERED"),
    ],
)
def test_visual_asset_pointer_integrity_fail_closed(case, expected):
    if case == "stale":
        session = _chain(pointer_stale="STALE")
    elif case == "hash":
        session = _chain(pointer_hash="tampered")
    elif case == "missing":
        session = _chain(pointer_version_id=999)
    elif case == "wrong_type":
        session = _chain(pointer_asset_type="character")
    elif case == "wrong_scope":
        session = _chain(pointer_scope_key="book:1:prop:P1@wrong")
    else:
        session = _chain(version_key="book:1:character:C1")
    with pytest.raises(VisualAssetAuthorityError) as error:
        resolve_current_visual_asset_authority(session, book_id=1, asset_key="book:1:prop:P1", expected_asset_type="prop")
    assert error.value.code == expected


def test_visual_asset_pointer_scope_ambiguity_fails_closed():
    session = _chain()
    session.pointers.append(SimpleNamespace(book_id=1, asset_key="book:1:prop:P1", asset_type="prop", scope_key="book:1:prop:P1@scene", current_version_id=7, payload_hash="hash", authority_status="SPEC_APPROVED", stale_status="FRESH"))
    with pytest.raises(VisualAssetAuthorityError, match="AMBIGUOUS") as error:
        resolve_current_visual_asset_authority(session, book_id=1, asset_key="book:1:prop:P1", expected_asset_type="prop")
    assert error.value.code == "VISUAL_ASSET_POINTER_AMBIGUOUS"


def test_real_phase_e_revision_artifact_records_asset_revision_and_adapter_gate():
    root = Path(__file__).resolve().parents[1] / "artifacts" / "e2e-production-pilot"
    trace = json.loads((root / "episode_01_phase_e_trace.json").read_text(encoding="utf-8"))
    audit = json.loads((root / "phase_e_prompt_ir_revision_asset_pointer_audit.json").read_text(encoding="utf-8"))
    assert trace["asset_revision"]["status"] == "PASS"
    assert trace["asset_revision"]["old_asset_version_id"] != trace["asset_revision"]["new_asset_version_id"]
    assert trace["asset_revision"]["changed_shot_ids"]
    assert trace["adapter_pointer_tamper"]["status_code"] == 409
    assert audit["prompt_ir_revision"] == {
        "create": "PASS",
        "reuse": "PASS",
        "policy_revision": "PASS",
        "revision_then_reuse": "PASS",
        "tamper_then_revision": "FAIL_CLOSED",
    }
    assert audit["visual_asset_pointer"]["legitimate_asset_revision"] == "PASS"
    assert audit["visual_asset_pointer"]["adapter_pointer_tamper"] == "FAIL_CLOSED"
