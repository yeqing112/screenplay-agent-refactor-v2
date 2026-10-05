"""Deterministic external runtime used by the browser user journey.

The mock runtime is deliberately opt in through ``E2E_EXTERNAL_RUNTIME=mock``
and is rejected in production by the callers.  It records bounded, secret-free
ledger entries so an E2E report can prove that the normal adapter boundary was
crossed without contacting a real vendor.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def enabled() -> bool:
    value = str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").strip().lower()
    deployment = str(os.environ.get("DEPLOYMENT_ENV") or os.environ.get("APP_ENV") or "development").strip().lower()
    return value == "mock" and deployment != "production"


def _ledger_path() -> Path:
    configured = str(os.environ.get("E2E_MOCK_LEDGER_PATH") or "").strip()
    return Path(configured) if configured else Path("work") / "e2e-mock-ledger.json"


def _read() -> dict[str, Any]:
    path = _ledger_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"entries": []}
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return {"entries": []}


def reset() -> None:
    path = _ledger_path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"entries": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def record(kind: str, operation: str, *, execution_id: str | None = None, result: str = "success", **metadata: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": str(kind),
        "operation": str(operation),
        "result": str(result),
        "execution_id": str(execution_id or ""),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            entry[str(key)] = value
    with _LOCK:
        payload = _read()
        entries = payload.setdefault("entries", [])
        if not isinstance(entries, list):
            entries = []
            payload["entries"] = entries
        entries.append(entry)
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def snapshot() -> dict[str, Any]:
    with _LOCK:
        payload = _read()
    entries = payload.get("entries") if isinstance(payload, dict) else []
    entries = entries if isinstance(entries, list) else []
    return {
        "entries": entries,
        "mock_llm_calls": sum(1 for item in entries if isinstance(item, dict) and item.get("kind") == "llm"),
        "mock_image_calls": sum(1 for item in entries if isinstance(item, dict) and item.get("kind") == "image"),
        "mock_video_calls": sum(1 for item in entries if isinstance(item, dict) and item.get("kind") == "video"),
    }


def _first_scene(prompt: str) -> str:
    match = re.search(r"(?:场景|地点|location|scene)[^\n：:]{0,30}[：:]\s*([^\n，。,。]{2,40})", prompt, re.IGNORECASE)
    return match.group(1).strip() if match else "雨夜便利店"


def response(prompt: str, *, json_mode: bool = False) -> str:
    """Return a compact response that is valid for the common agent contracts."""

    text = str(prompt or "")
    lowered = text.lower()
    scene = _first_scene(text)
    if "scene_split" in lowered or "start_line" in lowered or "场景列表" in text:
        scene = "雨夜旧港"
    # Director Treatment proposals must stay inside the frozen candidate
    # whitelist. Echo the baseline with one deterministic human-review note so
    # the adapter can validate and persist a proposal without a vendor call.
    if "RETURN_FIELDS" in text or "DirectorTreatment" in text or "导演方案" in text:
        match = re.search(r"BASE_TREATMENT=(\{.*\})\s*RETURN_FIELDS=", text, re.DOTALL)
        baseline = {}
        if match:
            try:
                parsed = json.loads(match.group(1))
                baseline = parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                baseline = {}
        candidate = {key: baseline.get(key) for key in ("dramatic_objective", "audience_question", "character_intents", "beat_map", "relationship_power_shift", "audience_emotion", "information_strategy", "performance_direction", "visual_strategy", "coverage_strategy", "sound_strategy", "edit_rhythm", "constraints", "unknowns")}
        candidate["note"] = "deterministic mock proposal; requires human confirmation"
        candidate["decision"] = "ready_for_review"
        candidate["confidence"] = 0.91
        candidate["human_confirmation_required"] = True
        return json.dumps(candidate, ensure_ascii=False)
    # Scriptwriter scene prompts contain a state extraction contract.  Keep
    # this branch ahead of the generic outline/script heuristics so a prompt
    # that quotes upstream JSON keys still yields a real, parseable screenplay
    # with canonical scene headings.
    if "状态提取块格式" in text or "场景必须以【场景结束】" in text:
        return (
            "## 场景一：雨夜旧港 — 旧港便利店 — 夜\n\n"
            "雨声砸在玻璃上。\u6797\u665a推门进入便利店，手里攥着一段录音和被雨水打湿的照片。\n\n"
            "\u6797\u665a：你见过这个人吗？\n\n"
            "店员抬眼看向照片，沉默两秒后指向后门。\u6797\u665a顺着视线转身，门缝外掠过一道黑影。她立即追出门外，录音在掌心继续播放。\n\n"
            "【场景结束】\n"
        )
    if "scene_split" in lowered or "start_line" in lowered or "场景列表" in text:
        return json.dumps({
            "scenes": [{"scene_name": scene, "start_line": 1, "end_line": 999, "description": f"{scene}内的连续动作"}],
            "schema_version": "mock-scene-split-v1",
            "status": "ok",
            "source": "deterministic-runtime",
            "summary": "单场景用户旅程样本",
        }, ensure_ascii=False)
    if "scene_shots" in lowered or "visual_prompt_static" in lowered or "镜头生成规则" in text or ("action_process" in lowered and "shot" in lowered):
        shots = [
            {"shot_id": "S1", "shot_purpose": "建立空间", "action_process": "林夏推门进入便利店，雨水沿着外套滴落。", "camera_angle": "中景固定", "duration": 3, "start_state": "便利店门口安静，雨声持续", "end_state": "林夏站到柜台前"},
            {"shot_id": "S2", "shot_purpose": "交付线索", "action_process": "林夏把被雨水打湿的照片放在柜台上，店员低头查看。", "camera_angle": "近景缓慢推近", "duration": 3, "start_state": "照片仍在林夏手中", "end_state": "店员神情变得紧张"},
            {"shot_id": "S3", "shot_purpose": "发现出口", "action_process": "店员沉默两秒后指向后门，林夏顺着手势转身。", "camera_angle": "过肩镜头轻移", "duration": 3, "start_state": "两人隔着柜台对视", "end_state": "后门进入画面"},
            {"shot_id": "S4", "shot_purpose": "结尾钩子", "action_process": "后门外黑色人影一闪而过，林夏立刻追出去。", "camera_angle": "手持跟拍", "duration": 3, "start_state": "后门半开，冷风进入", "end_state": "人影消失在雨幕中"},
        ]
        return json.dumps({"shots": shots}, ensure_ascii=False)
    if "outline" in lowered or "episode_count" in lowered or "分集大纲" in text:
        return json.dumps([{"episode": 1, "title": "雨夜照片", "core_event": "林夏追查照片来源并发现后门人影", "opening_hook": "雨夜有人推门而入", "core_conflict": "店员不愿回答照片问题", "climax": "店员指向后门", "ending_hook": "黑色人影一闪而过", "characters": ["林夏", "店员"], "scenes": [scene]}], ensure_ascii=False)
    if "qa" in lowered or '"issues"' in lowered or "质量检查" in text:
        return json.dumps({"issues": [], "errors": [], "overall_score": 9, "suggestions": [], "summary": "结构清晰，可进入人工确认"}, ensure_ascii=False)
    if "portrait" in lowered or "人物画像" in text or "face_shape" in lowered:
        return json.dumps({"gender": "女", "age_range": "26-30", "role": "主角", "identity": "调查记者", "face_shape": "鹅蛋脸", "facial_features": "清晰眉眼", "body_type": "匀称", "skin_tone": "自然肤色", "distinguishing_marks": "无", "signature_outfit": "深色雨衣", "accessories": "黑色斜挎包", "hairstyle": "黑色短发", "temperament": "冷静敏锐", "vibe": "克制紧张", "color_palette": "深蓝与灰", "personality": "果断", "speech_style": "短句直接", "body_language": "警觉", "visual_prompt_zh": "年轻女性调查记者，深色雨衣，雨夜便利店，电影写实风格"}, ensure_ascii=False)
    if "script" in lowered or "剧本" in text or "场景结束" in text:
        return """## 场景1：雨夜，便利店内\n\n雨声密集。林夏推门进来，深色雨衣上挂着水珠。\n\n林夏把一张被雨水打湿的照片放在柜台上。\n\n林夏：这个人今晚来过吗？\n\n店员看了一眼照片，神情突然紧张，沉默两秒后指向后门。\n\n林夏转身看去。后门外，一个黑色人影一闪而过。她立刻追出去。\n\n【场景结束】\n"""
    if json_mode:
        return json.dumps({"summary": "雨夜便利店发生了一次关键线索交接。", "characters": [{"name": "林夏", "aliases": [], "personality": "冷静敏锐", "relationships": {}}], "events": [{"seq": 1, "description": "林夏发现后门人影", "importance": "high", "characters_involved": ["林夏"]}], "scenes": [{"location": scene, "time": "雨夜", "mood": "紧张", "description": "便利店内外连续追踪"}], "foreshadowing": ["后门人影"]}, ensure_ascii=False)
    return "模拟外部模型已返回结构化建议：围绕雨夜便利店、照片线索和后门人影推进悬念，并保留人工确认。"


__all__ = ["enabled", "record", "reset", "snapshot", "response"]



