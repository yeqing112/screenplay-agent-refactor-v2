# V7.5 Post-Canary Remediation Audit

The previous real canary was closed after one Provider call and was not retried. This evidence records code-only remediation; Provider calls remain `0`.

- The API now performs the formal ProposalIR Schema gate immediately after parsing.
- The compact provider field `character_directions[].direction` is part of the flat v1 contract and is preserved by the deterministic compiler.
- Source-grounded prompt identity freezes `ADVISORY_ASSET_CONTEXT=[]`, preventing mutable advisory assets from changing the request fingerprint.
- Dry-run request fingerprint matches the frozen value: `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93`.
- 42 directed tests passed; compileall and diff check passed.

A new explicit authorization is required before a subsequent real Provider POST.
