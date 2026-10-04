from core.asset_provider_router import (
    AssetOperation,
    AssetProviderRouter,
    ProviderFailureClassification,
    ProviderHealthSnapshot,
    can_failover,
    classify_provider_failure,
    PostSubmissionState,
)


def _profile(profile_id, provider, model, *, reference=False, modes=None, default=False):
    return {
        "id": profile_id,
        "capability": "image",
        "provider": provider,
        "model_name": model,
        "enabled": True,
        "api_key": "secret",
        "default_params": {
            "supports_reference_images": reference,
            "task_modes": modes or ["text_to_image"],
        },
        "is_default": default,
    }


def test_reference_capable_providers_are_eligible_for_master_and_derivation():
    profiles = [
        _profile("75", "75api-image", "gpt-image-2-1k", reference=True),
        _profile("shapi", "shapi-gemini-image", "nano-banana-2", reference=True),
    ]
    router = AssetProviderRouter(profiles, default_image_profile_id="75")
    master = router.candidates("IMAGE", AssetOperation.TEXT_TO_IMAGE)
    assert [row.profile_id for row in master] == ["75", "shapi"]
    derived = router.candidates("IMAGE", AssetOperation.REFERENCE_IMAGE_DERIVATION)
    assert [row.profile_id for row in derived] == ["75", "shapi"]


def test_health_cache_is_session_scoped_and_skips_unhealthy_provider():
    health = ProviderHealthSnapshot()
    health.mark("shapi", ProviderFailureClassification.CREDITS_INSUFFICIENT)
    router = AssetProviderRouter(
        [_profile("shapi", "shapi-gemini-image", "nano-banana-2", reference=True), _profile("other", "75api-image", "gpt-image-2-1k")],
        health=health,
    )
    rows = router.rank("IMAGE", AssetOperation.TEXT_TO_IMAGE)
    assert rows[0].profile_id == "shapi"
    assert not router.candidates("IMAGE", AssetOperation.TEXT_TO_IMAGE)[0].profile_id == "shapi"
    assert health.is_healthy("shapi") is False


def test_failure_classification_and_failover_policy_are_fail_closed():
    assert classify_provider_failure("Your credits are insufficient") == ProviderFailureClassification.CREDITS_INSUFFICIENT
    assert classify_provider_failure("submitted but request id is unknown") == ProviderFailureClassification.SUBMISSION_AMBIGUOUS
    assert classify_provider_failure("invalid payload: missing prompt") == ProviderFailureClassification.PAYLOAD_INVALID
    assert can_failover(ProviderFailureClassification.CREDITS_INSUFFICIENT)
    assert not can_failover(ProviderFailureClassification.SUBMISSION_AMBIGUOUS)
    assert not can_failover(ProviderFailureClassification.PAYLOAD_INVALID)
    assert not can_failover(ProviderFailureClassification.CREDITS_INSUFFICIENT, task_created=True)


def test_timeout_before_send_can_failover():
    assert classify_provider_failure("timeout", post_submission_state=PostSubmissionState.NOT_SENT) == ProviderFailureClassification.NETWORK_TRANSIENT
    assert can_failover(ProviderFailureClassification.NETWORK_TRANSIENT, post_submission_state=PostSubmissionState.NOT_SENT)


def test_timeout_after_send_is_submission_ambiguous():
    assert classify_provider_failure("request timed out", post_submission_state=PostSubmissionState.AMBIGUOUS_AFTER_SEND) == ProviderFailureClassification.SUBMISSION_AMBIGUOUS
    assert not can_failover(ProviderFailureClassification.SUBMISSION_AMBIGUOUS, post_submission_state=PostSubmissionState.AMBIGUOUS_AFTER_SEND)


def test_unknown_task_after_post_does_not_blind_failover():
    state = PostSubmissionState.TASK_NOT_CONFIRMED
    classification = classify_provider_failure("unknown task id after POST", post_submission_state=state)
    assert classification == ProviderFailureClassification.SUBMISSION_AMBIGUOUS
    assert not can_failover(classification, post_submission_state=state)
    assert can_failover(classification, post_submission_state=state, reconciled_no_task=True)


def test_confirmed_provider_task_never_fails_over():
    assert not can_failover(ProviderFailureClassification.CREDITS_INSUFFICIENT, task_created=True, post_submission_state=PostSubmissionState.TASK_CONFIRMED)
