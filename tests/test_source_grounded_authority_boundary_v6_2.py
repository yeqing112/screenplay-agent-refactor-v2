"""V6.2 red/green contract tests for the dual-source authority boundary."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.script_ir_preparation_api import _snapshot_records, _source_anchor_bindings
from core.script_ir_authority import validate_source_anchor_bindings
from core.source_authority import (
    SourceLineageContext,
    canonical_json_bytes,
    canonical_json_sha256,
    resolve_origin_source,
)
from core.fact_snapshot import build_fact_snapshot
from core.script_ir import resolve_script_payload, script_ir_hash
from core.script_ir_authority import activate_script_ir
from core.script_ir_authority import validate_authority_envelope_v2
from core.script_ir_production_preparation import build_production_candidate
from core.script_ir_source_requirements import compile_script_ir_source_requirements
from core.source_evidence_index import build_source_evidence_index
from core.source_structuring_v3 import SCHEMA_VERSION_V3_1, canonical_script_payload_v3, ground_candidate_v3
from scripts.source_structuring_scanner import scan_source_text
from models import Base, Book, Chapter, FactRecord, FactSnapshot, Script, ScriptIRVersion


def test_canonical_json_hash_is_not_python_repr_hash() -> None:
    value = {"b": 2, "a": "文本"}
    expected = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert canonical_json_bytes(value) == expected
    assert canonical_json_sha256(value) == hashlib.sha256(expected).hexdigest()


def test_source_lineage_context_requires_origin_and_canonical_layers() -> None:
    context = SourceLineageContext(
        origin_source_kind="BOOK_CHAPTER",
        origin_source_package_id="book:fixture",
        origin_source_version_id="chapter:1:v1",
        origin_source_locator={"book_id": 77, "episode": 2},
        origin_source_raw_hash="a" * 64,
        structuring_response_fingerprint="b" * 64,
        reconciliation_policy_version="reconciliation_v1",
        reconciliation_fingerprint="c" * 64,
        migration_fingerprint="d" * 64,
        canonical_projection_version="source_grounded_script_payload_v3_1",
    )
    assert context.origin_source_raw_hash != context.canonical_script_content_hash


def test_origin_resolver_fails_closed_for_missing_source() -> None:
    context = SourceLineageContext(
        origin_source_kind="BOOK_CHAPTER",
        origin_source_package_id="book:missing",
        origin_source_version_id="chapter:404",
        origin_source_locator={"book_id": 404, "episode": 404},
        origin_source_raw_hash="a" * 64,
    )
    with pytest.raises(ValueError, match="ORIGIN_SOURCE_NOT_FOUND"):
        resolve_origin_source(SimpleNamespace(query=lambda *_: None), context)


def test_v3_1_authority_envelope_has_dual_source_contract() -> None:
    from core.script_ir_authority import build_authority_envelope_v2

    envelope = build_authority_envelope_v2(
        book_id=77,
        episode=2,
        script_ir_payload={"schema_version": "script_ir_v1", "scenes": []},
        lineage=SourceLineageContext(
            origin_source_kind="BOOK_CHAPTER", origin_source_package_id="book:fixture", origin_source_version_id="chapter:1:v1",
            origin_source_locator={"book_id": 77, "episode": 2}, origin_source_raw_hash="a" * 64,
            structuring_response_fingerprint="b" * 64, reconciliation_policy_version="reconciliation_v1",
            reconciliation_fingerprint="c" * 64, migration_fingerprint="d" * 64,
            canonical_projection_version="source_grounded_script_payload_v3_1",
            canonical_script_payload_fingerprint="h" * 64,
        ),
        fact_snapshot={"id": 1, "revision": 1, "payload_hash": "e" * 64},
        source_evidence_index={"evidence_index_fingerprint": "f" * 64},
        requirement_set={"fingerprint": "1" * 64}, coverage_result={"fingerprint": "2" * 64},
        source_anchor_bindings={"scene|E01_SC001|scene_identity_evidence|scene": ["E0001"]},
        canonical_script_content_hash="g" * 64,
    )
    assert envelope["schema_version"] == "script_ir_authority_envelope_v2"
    assert envelope["origin_source_raw_hash"] == "a" * 64
    assert envelope["canonical_script_content_hash"]


def test_v2_authority_validation_detects_canonical_origin_and_lineage_tamper() -> None:
    from core.script_ir_authority import build_authority_envelope_v2
    lineage = SourceLineageContext(origin_source_kind="BOOK_CHAPTER", origin_source_package_id="p", origin_source_version_id="v", origin_source_locator={"book_id": 1, "chapter_seq": 1}, origin_source_raw_hash="a" * 64, structuring_response_fingerprint="b" * 64, reconciliation_policy_version="r", reconciliation_fingerprint="c" * 64, migration_fingerprint="d" * 64, canonical_projection_version="source_grounded_script_payload_v3_1", canonical_script_payload_fingerprint="h" * 64)
    envelope = build_authority_envelope_v2(book_id=1, episode=1, script_ir_payload={"schema_version": "script_ir_v1", "scenes": []}, lineage=lineage, fact_snapshot={"id": 1, "revision": 1, "payload_hash": "e" * 64}, source_evidence_index={"evidence_index_fingerprint": "f" * 64}, requirement_set={"fingerprint": "1" * 64}, coverage_result={"fingerprint": "2" * 64}, source_anchor_bindings={}, canonical_script_content_hash="g" * 64)
    envelope["canonical_script_content_hash"] = "x" * 64
    report = validate_authority_envelope_v2(envelope, payload={"schema_version": "script_ir_v1", "scenes": []}, lineage=lineage, source_evidence_index={"evidence_index_fingerprint": "f" * 64}, canonical_script_content_hash="g" * 64, origin_raw_hash="a" * 64)
    assert report["status"] == "FAIL"
    assert any(item["code"] == "CANONICAL_SCRIPT_CHANGED" for item in report["errors"])


def test_v6_2_authority_modules_have_zero_strict_canary_hits() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    paths = [root / "core" / "source_authority.py", root / "core" / "script_ir_authority.py", root / "api" / "script_ir_preparation_api.py", root / "core" / "script_ir_production_preparation.py"]
    forbidden = ("990402", "CH03", "林晚", "顾沉", "也许是你自己", "第三章 没有底片的暗房")
    assert [hit for path in paths for hit in scan_source_text(path.read_text(encoding="utf-8"), forbidden=forbidden)] == []


def test_scene_identity_evidence_requires_all_origin_anchors() -> None:
    requirement_set = {"requirements": [{
        "requirement_id": "scene|S1|scene_identity_evidence|scene",
        "contract_requirement_id": "SIR_SCENE_IDENTITY_EVIDENCE", "blocking": True,
        "source_value": [{"text": "first"}, {"text": "second"}],
    }]}
    index = {"source_package_id": "p", "source_version_id": "v", "source_raw_hash": "h", "anchors": [
        {"anchor_ref": "E0001", "exact_text": "first", "source_package_id": "p", "source_version_id": "v", "source_raw_hash": "h"},
        {"anchor_ref": "E0002", "exact_text": "second", "source_package_id": "p", "source_version_id": "v", "source_raw_hash": "h"},
    ]}
    result = validate_source_anchor_bindings(requirement_set=requirement_set, source_evidence_index=index, bindings={"scene|S1|scene_identity_evidence|scene": ["E0001"]})
    assert result["status"] == "FAIL"
    assert any(item["code"] == "SOURCE_ANCHOR_SCENE_IDENTITY_MISMATCH" for item in result["errors"])


def test_snapshot_records_cannot_fabricate_e_index_fallback() -> None:
    requirement_set = {"requirements": [{"blocking": True, "contract_requirement_id": "SIR_SCENE_IDENTITY_EVIDENCE", "source_value": [{"text": "scene"}], "subject_type": "scene", "subject_id": "S1", "predicate": "scene_identity_evidence", "scope": "scene"}]}
    with pytest.raises(ValueError, match="FACT_SOURCE_ANCHOR_REQUIRED"):
        _snapshot_records(requirement_set, source_anchor_bindings={})


def test_snapshot_records_use_validated_anchor_refs_and_keep_exact_text_in_value() -> None:
    requirement_set = {"requirements": [{"blocking": True, "contract_requirement_id": "SIR_SCENE_IDENTITY_EVIDENCE", "source_value": [{"text": "scene"}], "subject_type": "scene", "subject_id": "S1", "predicate": "scene_identity_evidence", "scope": "scene", "requirement_id": "scene|S1|scene_identity_evidence|scene"}]}
    records = _snapshot_records(requirement_set, source_anchor_bindings={"scene|S1|scene_identity_evidence|scene": ["E0002"]})
    assert records[0]["evidence"] == ["E0002"]
    assert records[0]["value"] == [{"text": "scene"}]


def test_v3_1_temporary_full_persistence_and_resolve_with_generic_source() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    raw = "A different chapter source.\nMAYA: Wait here."
    scene = {"scene_id": "E02_SC001", "scene_evidence": [raw], "participants": [{"name": "MAYA", "evidence": [raw]}], "actions": [{"text": "A different chapter source.", "source_evidence": "A different chapter source.\nMAYA: Wait here."}], "dialogues": [{"speaker": "MAYA", "text": "Wait here.", "source_form": "SPEAKER_LABELED", "utterance_evidence": [raw], "speaker_identity_evidence": [raw], "binding_type": "SOURCE_LITERAL"}]}
    grounded = ground_candidate_v3(raw, {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [scene], "unknowns": []})
    assert grounded["status"] == "PASS", grounded
    origin_hash = hashlib.sha256(raw.encode()).hexdigest()
    lineage = SourceLineageContext(origin_source_kind="BOOK_CHAPTER", origin_source_package_id="book:generic", origin_source_version_id="chapter:2:v1", origin_source_locator={"book_id": 1, "chapter_seq": 2}, origin_source_raw_hash=origin_hash, structuring_response_fingerprint="1" * 64, reconciliation_policy_version="reconciliation_v1", reconciliation_fingerprint="2" * 64, migration_fingerprint="3" * 64, canonical_projection_version="source_grounded_script_payload_v3_1")
    canonical = canonical_script_payload_v3(grounded["grounded_candidate"], source_lineage=lineage)
    canonical["scenes"][0]["beats"] = [{"beat_id": "E02_SC001_B01", "type": "HOOK", "beat_type": "HOOK", "event": "A different chapter source.", "importance": "critical", "requires_reaction": True}]
    canonical["scenes"][0]["script_blocks"].append({"order": 30, "type": "ACTION", "ref": "E02_SC001_B01"})
    content = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical_hash = hashlib.sha256(content.encode()).hexdigest()
    candidate = build_production_candidate(canonical, book_id=1, episode=2)
    with SessionLocal() as session:
        book = Book(title="generic", filename="generic.txt")
        session.add(book); session.flush()
        chapter = Chapter(book_id=book.id, seq=2, content=raw)
        script = Script(book_id=book.id, episode=2, content=content)
        session.add_all([chapter, script]); session.flush()
        index = build_source_evidence_index(raw.encode(), source_package_id=lineage.origin_source_package_id, source_version_id=lineage.origin_source_version_id, source_raw_hash=origin_hash)
        requirements = compile_script_ir_source_requirements(source_structure=candidate)
        anchors = {}
        for row in requirements["requirements"]:
            if not row.get("blocking"):
                continue
            source_value = row.get("source_value")
            expected_texts = [str(v.get("text") or "") for v in source_value if isinstance(v, dict)] if isinstance(source_value, list) else ([str(source_value)] if isinstance(source_value, str) else [])
            refs = [anchor["anchor_ref"] for anchor in index["anchors"] if any(text and text in anchor["exact_text"] for text in expected_texts)]
            anchors[str(row["requirement_id"])] = refs
        if "episode|scenes|scene_existence|episode" in [str(r.get("requirement_id")) for r in requirements["requirements"]]:
            anchors["episode|scenes|scene_existence|episode"] = ["E0001"]
        records = [{"fact_id": f"F{i}", "subject_type": row["subject_type"], "subject_id": row["subject_id"], "predicate": row["predicate"], "value": row.get("source_value") if row.get("source_value") is not None else row.get("expected_value"), "scope": row["scope"], "authority": "source_text", "status": "confirmed", "evidence": anchors[str(row["requirement_id"])]} for i, row in enumerate(requirements["requirements"], 1) if row.get("blocking")]
        fact = build_fact_snapshot(records, book_id=book.id, episode=2, source_fingerprint=origin_hash)
        snapshot = FactSnapshot(book_id=book.id, episode=2, revision=1, status="confirmed", source_fingerprint=origin_hash, payload_hash=fact["payload_hash"], records_json=json.dumps(fact["records"], ensure_ascii=False), validation_report=json.dumps({**fact["validation"], "fact_coverage": {"status": "FACT_COVERAGE_SUFFICIENT"}}))
        session.add(snapshot); session.flush()
        for record in fact["records"]:
            session.add(FactRecord(snapshot_id=snapshot.id, fact_id=record["fact_id"], subject_type=record["subject_type"], subject_id=record["subject_id"], predicate=record["predicate"], value_json=json.dumps(record["value"], ensure_ascii=False), scope=record["scope"], authority=record["authority"], status=record["status"], confidence=1.0, evidence_json=json.dumps(record["evidence"])))
        draft = ScriptIRVersion(book_id=book.id, episode=2, revision=1, status="draft", schema_version="script_ir_v1", source_fact_snapshot_id=str(snapshot.id), source_fingerprint=canonical_hash, payload_json=json.dumps(candidate, ensure_ascii=False, sort_keys=True), payload_hash=script_ir_hash(candidate), validation_status="qualified")
        session.add(draft); session.flush()
        result = activate_script_ir(session=session, script_row=script, draft_row=draft, source_structure=candidate, source_package_id=lineage.origin_source_package_id, source_version_id=lineage.origin_source_version_id, immutable_source_raw_hash=origin_hash, source_evidence_index=index, source_anchor_bindings=anchors, fact_snapshot_row=snapshot, origin_raw_bytes=raw.encode(), canonical_script_content_hash=canonical_hash, source_lineage=lineage)
        assert result["authority_envelope"]["schema_version"] == "script_ir_authority_envelope_v2"
        session.refresh(script)
        assert resolve_script_payload(session, script, workflow_profile="production")["source_grounded_schema_version"] == "source_grounded_script_payload_v3_1"


def test_prepare_production_route_uses_origin_chapter_and_writes_only_isolated_db(monkeypatch) -> None:
    import api.script_ir_preparation_api as preparation_api
    from api.script_ir_preparation_api import PrepareProductionRequest, prepare_script_ir_production
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    raw = "Generic route chapter.\nMAYA: Hold."
    grounded = ground_candidate_v3(raw, {"schema_version": SCHEMA_VERSION_V3_1, "scenes": [{"scene_id": "E03_SC001", "scene_evidence": [raw], "participants": [{"name": "MAYA", "evidence": [raw]}], "actions": [{"text": "Generic route chapter.", "source_evidence": raw}], "dialogues": [{"speaker": "MAYA", "text": "Hold.", "source_form": "SPEAKER_LABELED", "utterance_evidence": [raw], "speaker_identity_evidence": [raw], "binding_type": "SOURCE_LITERAL"}]}], "unknowns": []})
    lineage = SourceLineageContext(origin_source_kind="BOOK_CHAPTER", origin_source_package_id="book:route", origin_source_version_id="chapter:3:v1", origin_source_locator={"book_id": 1, "chapter_seq": 3}, origin_source_raw_hash=hashlib.sha256(raw.encode()).hexdigest(), structuring_response_fingerprint="4" * 64, reconciliation_policy_version="reconciliation_v1", reconciliation_fingerprint="5" * 64, migration_fingerprint="6" * 64, canonical_projection_version="source_grounded_script_payload_v3_1")
    canonical = canonical_script_payload_v3(grounded["grounded_candidate"], source_lineage=lineage)
    canonical["scenes"][0]["beats"] = [{"beat_id": "E03_SC001_B01", "type": "HOOK", "beat_type": "HOOK", "event": "Generic route chapter.", "importance": "critical", "requires_reaction": True}]
    canonical["scenes"][0]["script_blocks"].append({"order": 30, "type": "ACTION", "ref": "E03_SC001_B01"})
    content = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with SessionLocal() as session:
        book = Book(title="route", filename="route.txt"); session.add(book); session.flush()
        session.add(Chapter(book_id=book.id, seq=3, content=raw))
        session.add(Script(book_id=book.id, episode=3, content=content)); session.commit(); book_id = book.id
    monkeypatch.setattr(preparation_api, "Session", SessionLocal)
    result = prepare_script_ir_production(book_id, 3, PrepareProductionRequest(confirmed=True))
    assert result["activation"]["authority_envelope"]["schema_version"] == "script_ir_authority_envelope_v2"
    with SessionLocal() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=3).one()
        assert resolve_script_payload(session, script, workflow_profile="production")["source_grounded_schema_version"] == "source_grounded_script_payload_v3_1"
        script.content = content + "x"; session.commit()
        with pytest.raises(Exception) as canonical_exc:
            resolve_script_payload(session, script, workflow_profile="production")
        assert "CANONICAL" in str(canonical_exc.value) or "STALE" in str(canonical_exc.value)
        script.content = content
        chapter = session.query(Chapter).filter_by(book_id=book_id, seq=3).one(); chapter.content = raw + "x"; session.commit()
        with pytest.raises(Exception) as origin_exc:
            resolve_script_payload(session, script, workflow_profile="production")
        assert "ORIGIN" in str(origin_exc.value)
