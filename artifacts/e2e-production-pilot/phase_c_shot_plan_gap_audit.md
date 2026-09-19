# Phase C ShotPlan Gap Audit

- Production input path: current ScriptIR + current DirectorTreatment + current SceneBlocking.
- Current-pointer binding: existing ShotPlan authority path is retained; no latest fallback is introduced.
- Canonical truth: structured `shots`, coverage contracts, spatial binding, camera state, continuity contract.
- Derived projection: coverage results, compiled continuity, runtime estimate, Markdown.
- Legacy compatibility: existing `shot_plan_v1/v2` rows remain readable and are not Phase C ready.
- Provider boundary: provider proposals remain candidates; this pilot uses the deterministic builder with zero provider calls.
- Hidden cuts: represented structurally by one camera segment per canonical shot.
- Beat order: follows current Treatment beat order.
- Storyboard/PromptIR/visual generation: untouched.
