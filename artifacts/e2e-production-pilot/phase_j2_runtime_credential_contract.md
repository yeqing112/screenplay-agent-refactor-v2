# Phase J2 Runtime Credential Contract

## Current evidence

The Model Registry accepts `api_key`, persists it in KV JSON, returns it to sensitive internal callers, and adapters read `profile["api_key"]` directly. `core/provider_execution_profile.py` keeps only `credential.configured` and `credential.source_identity`, so the canonical execution boundary has no runtime resolver or validation result. `config.py` exposes deployment environment values such as `OPENAI_API_KEY`, but one variable is not a provider credential contract.

This phase does not delete, migrate, rotate, or validate any credential and makes no Provider call.

## Target secret-free reference

The design introduces a conceptual reference without fixing an implementation-specific serialization format yet:

```json
{
  "credential_ref": "opaque-provider-scoped-reference",
  "credential_source_type": "deployment_secret_binding|environment_binding|secret_store_binding",
  "configured": true,
  "reference_revision": "rotation-or-binding-revision"
}
```

The reference identifies a provider-scoped secret binding. It is not the secret, an Authorization header, a URL query token, or a derivation of a model name.

## Resolver contract

```text
resolve_credential(
  credential_ref,
  credential_source_type,
  provider_identity,
  model_profile_id
) -> {
  configured: bool,
  resolved: bool,
  validated: bool,
  validation_fingerprint: string | null,
  expires_at: timestamp | null,
  runtime_secret: transient-only
}
```

Rules:

1. `configured` means only that a reference is declared.
2. `resolved` means the runtime binding returned a secret for the selected provider/profile.
3. `validated` requires explicit provider-specific validation evidence; it is never inferred from configured or resolved.
4. `runtime_secret` exists only in memory between resolver and Provider transport and is never returned or persisted.
5. Resolver failures fail closed before an execution enters `RUNNING`.
6. Validation is scoped to the selected production profile. Unselected backup profiles may remain unconfigured without blocking production.

The existing environment/config loader can be an interim resolver backend through a provider-scoped deployment binding. A legacy `OPENAI_API_KEY` mapping may be read during the compatibility window, but the canonical contract must not special-case that variable or treat it as universal authorization.

## Secret boundary

These surfaces may contain references, non-secret status, or one-way fingerprints only:

```text
Model Registry serialized profile
GenerationPolicy
ProductionGenerationSelection
GenerationPayload
ProviderExecutionProfile
GenerationExecutionRecord
MediaCandidateRecord
provider_request_fingerprint
request_snapshot_json
logs
artifacts
```

No raw key, bearer token, URL credential, response header, or secret-derived reversible value may enter those surfaces.

## Existing raw-key exit strategy

### 1. Freeze new raw writes

Once the new contract is implemented, Model Management writes only the reference, source type, configured status, and revision. New production profiles cannot be saved with a raw `api_key` field.

### 2. Backward-compatible dual-read window

For a bounded release window, a migration-aware resolver may read an existing legacy KV key only for the selected profile, immediately place it into the deployment secret binding, and return a transient resolution. It must never echo or copy the value into another persisted JSON field. Ambiguous or failed conversion remains non-executable.

### 3. Rotation and redaction

After successful binding, rotate the credential where supported, replace the legacy KV value with a redacted marker/reference, and record only migration status and reference revision. Backups and exports containing the old plaintext are handled by the deployment secret-retention process.

### 4. Fail-closed cutoff

After the window, raw-only profiles fail `credential_resolved=false` and cannot pass the production gate. Connectivity tests may explain migration requirements without generating media.

### 5. Recovery

A failed or expired binding requires operator reconfiguration/rotation. The system never falls back to another profile's key, a Registry default, or an environment variable selected by model name.

## Independent human authorization

The credential gate is separate from the human Provider authorization gate:

```text
PHASE_J_PROVIDER_AUTHORIZED=true
AND production_model_selected=true
AND model_profile_current=true
AND adapter_resolved=true
AND credential_resolved=true
AND credential_validated=true
```

The authorization flag is an explicit human decision to incur real Provider cost. Credential validation is a runtime property of the selected profile. Neither implies the other.

## Validation and connectivity separation

The existing Model Connectivity Test can report reachability/catalog/structural evidence. It must not promote that evidence to `validated=true` for a different execution, and it must not create `GenerationExecutionRecord`, `MediaCandidateRecord`, or OfficialMedia rows. A production execution consumes a resolver result bound to its frozen selection/profile fingerprint.
