# Old to Production Mapping

| Existing Module | Current Responsibility | Future Production Role |
|---|---|---|
| Storyboard / StoryboardShot | shot structure、legacy prompt、visual bindings | editorial source and compatibility projection；执行使用 qualified PromptIR pointer |
| StoryboardPromptVersion | static/motion/negative prompt versions | legacy read/rollback；作为 compiler 输入，不直接作为 provider truth |
| PromptIRVersion / Pointer | structured payload、authority、media-scoped pointer | canonical executable prompt |
| ProductionPromptVersion | append-only prompt lineage | creative source lineage and immutable audit |
| Model Registry | KV profiles、defaults、credential/config | configuration and explicit profile selection |
| ProviderExecutionProfile | typed allowlist、secret-free projection | canonical adapter input |
| generation_adapters.py | provider image/video submit/poll | implementations behind ModelAdapter/transport |
| GenerationExecutionRecord | execution fingerprint、provider ids、status | single durable execution identity |
| MediaCandidateRecord | storage/checksum/provenance below authority | canonical candidate ingestion |
| MediaValidationRecord | technical validation | promotion prerequisite |
| OfficialMediaVersion/Pointer/Authority | official media current pointer | production output/read authority |
| Visual Asset Authority | identity/version/pointer/reference/human decisions | canonical asset governance |
| TaskRun/pipeline endpoints | script/visual/storyboard jobs | upper-level orchestration status |
| Production Workspace projections | joined frontend read model | single frontend production read contract |
| Legacy generate-frame/generate-video | direct storyboard generation | compatibility adapter to canonical execution |

## Migration order

Freeze PromptIR/profile/payload fingerprint；route legacy generation through canonical orchestrator；candidate and validation precede official pointer；workspace reads production projection v2；确认 parity 后再减少 legacy writes。
