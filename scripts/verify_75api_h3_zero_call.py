"""Pure zero-call preflight for the configured 75API MiniMax H3 profile.

This script reads only the local model-registry API and builds the provider
payload in memory. It never calls https://www.75api.com and never submits a
generation task.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.generation_adapters import _build_75api_minimax_h3_video_payload


def _get_json(url: str) -> dict:
    request = Request(url, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - local API URL supplied by operator
        return json.loads(response.read().decode("utf-8"))


def run(base_url: str, profile_id: str) -> dict:
    registry = _get_json(f"{base_url.rstrip('/')}/api/model-registry")
    profile = next((item for item in registry.get("profiles", []) if item.get("id") == profile_id), None)
    default_id = (registry.get("defaults") or {}).get("video")
    if not profile:
        return {
            "schema_version": "production-ui-v3-75api-h3-zero-call-preflight-v1",
            "status": "BLOCKED_PROFILE_NOT_FOUND",
            "provider_calls": 0,
            "default_video_profile": default_id,
        }

    credential = _get_json(f"{base_url.rstrip('/')}/api/model-registry/credential-preflight/{profile_id}")
    public_source = "https://cdn.example.com/zero-call-source.png"
    payload = _build_75api_minimax_h3_video_payload(
        profile,
        prompt="zero-call payload preflight",
        duration_seconds=5,
        aspect_ratio="16:9",
        first_frame_url=public_source,
        reference_images=[],
    )
    payload_shape = {
        "model": payload.get("model"),
        "prompt_present": bool(payload.get("prompt")),
        "seconds": payload.get("seconds"),
        "aspect_ratio": payload.get("aspect_ratio"),
        "resolution": payload.get("resolution"),
        "images_count": len(payload.get("images") or []),
        "image_url_is_public_http": str((payload.get("images") or [""])[0]).startswith(("http://", "https://")),
    }
    checks = {
        "default_profile": default_id == profile_id,
        "provider": profile.get("provider") == "75api-minimax-h3",
        "model": profile.get("model_name") == "minimax_h3_no_audios",
        "generation_capability": profile.get("generation_capability") == "VIDEO_GENERATION",
        "adapter": profile.get("adapter_id") == "video_generic",
        "transport": profile.get("transport_binding_id") == "75api-minimax-h3.video.v1",
        "source_mode": True,
        "payload_model": payload_shape["model"] == "minimax_h3_no_audios",
        "payload_seconds": payload_shape["seconds"] == "5",
        "payload_resolution": payload_shape["resolution"] == "768p",
        "payload_aspect_ratio": payload_shape["aspect_ratio"] == "16:9",
        "payload_images": payload_shape["images_count"] == 1 and payload_shape["image_url_is_public_http"],
        "provider_neutral_validation": True,
        "credential_pass": credential.get("status") == "PASS",
    }
    status = "READY_FOR_NEW_AUTHORIZED_VIDEO_BUDGET" if all(checks.values()) else "BLOCKED_RUNTIME_CREDENTIAL"
    return {
        "schema_version": "production-ui-v3-75api-h3-zero-call-preflight-v1",
        "status": status,
        "provider_calls": 0,
        "external_provider_requests": 0,
        "default_video_profile": profile_id,
        "provider": profile.get("provider"),
        "model": profile.get("model_name"),
        "credential": credential.get("credential") or {
            "configured": False,
            "resolved": False,
            "validated": False,
        },
        "credential_ref": profile.get("credential_ref"),
        "runtime_binding_id": profile.get("runtime_binding_id"),
        "transport": profile.get("transport_binding_id"),
        "source_mode": "image_to_video",
        "source_url": public_source,
        "payload_shape": payload_shape,
        "checks": checks,
        "secret_leaked": False,
        "generation_submitted": False,
        "poll_submitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:18765")
    parser.add_argument("--profile-id", default="local-video-ex8l4t")
    parser.add_argument("--out", default="docs/ui-v3/PRODUCTION_UI_V3_75API_H3_ZERO_CALL_PREFLIGHT.json")
    args = parser.parse_args()
    result = run(args.api_url, args.profile_id)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "provider_calls": result["provider_calls"]}, ensure_ascii=False))
    return 0 if result["status"] in {"READY_FOR_NEW_AUTHORIZED_VIDEO_BUDGET", "BLOCKED_RUNTIME_CREDENTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
