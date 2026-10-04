import httpx

from core.generation_timeout import GenerationTimeoutHierarchy, classify_timeout_layer, timeout_evidence


def test_outer_timeout_is_greater_than_provider_timeout():
    hierarchy = GenerationTimeoutHierarchy.from_profile({"default_params": {"timeout_seconds": 120}})
    assert hierarchy.provider_timeout_seconds == 120
    assert hierarchy.orchestration_read_timeout_seconds == 180
    assert hierarchy.orchestration_read_timeout_seconds > hierarchy.provider_timeout_seconds


def test_generation_timeout_uses_profile_timeout_and_granular_httpx_config():
    hierarchy = GenerationTimeoutHierarchy.from_profile({"default_params": {"timeout_seconds": 37}})
    timeout = hierarchy.httpx_timeout()
    assert hierarchy.provider_timeout_seconds == 37
    assert timeout.read == 97
    assert timeout.connect == 10
    assert timeout.write == 60
    assert timeout.pool == 30


def test_outer_timeout_before_provider_timeout_is_configuration_error():
    hierarchy = GenerationTimeoutHierarchy.from_profile({"default_params": {"timeout_seconds": 120}})
    layer, code = classify_timeout_layer(httpx.ReadTimeout("outer"), hierarchy=hierarchy, elapsed_seconds=60)
    assert layer == "ORCHESTRATION"
    assert code == "ORCHESTRATION_TIMEOUT_CONFIGURATION_ERROR"


def test_provider_timeout_after_post_remains_provider_layer():
    hierarchy = GenerationTimeoutHierarchy.from_profile({"default_params": {"timeout_seconds": 120}})
    layer, code = classify_timeout_layer(httpx.ReadTimeout("provider"), hierarchy=hierarchy, elapsed_seconds=120, provider_transport_timeout=True)
    assert (layer, code) == ("PROVIDER", None)
    evidence = timeout_evidence(hierarchy, request_started_at=1.0, request_finished_at=121.0, timeout_layer=layer)
    assert evidence["timeout_layer"] == "PROVIDER"
    assert evidence["elapsed_seconds"] == 120.0
