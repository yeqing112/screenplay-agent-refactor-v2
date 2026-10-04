# MiniMax H3 Compiler V1

The compiler accepts only `VideoIntentIR` and declared `VideoModelCapabilities`. It emits deterministic `CompiledVideoRequestIR` with the provider prompt, duration projection, aspect ratio, reference mode, audio mode, fingerprints, and complexity audit.

`AUTHORITATIVE` dialogue preserves the exact source text, assigns stable speaker IDs in semantic character order, and emits timed `<d>[Language] exact text</d>` blocks. `NONE` dialogue emits no dialogue markup, requests a closed relaxed mouth state, disables music and extra voices, and retains source facts unchanged.

Duration is owned by `core.shot_readiness.project_provider_duration`; terminal hold padding is recorded explicitly. The provider adapter owns the API model name, HTTP method, retry, poll, reconcile, and credential handling. The compiler has no credentials or transport fields.

Gate A is zero-call. No real IMAGE or VIDEO provider was called while producing this specification or its golden fixtures.
