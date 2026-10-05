# Current Production Source Ingest Path

1. Create a new Book with `POST /api/books` (`core.book_lifecycle.create_book`).
2. Persist only authoritative screenplay/source content with `POST /api/books/{book_id}/scripts`, using `workflow_profile=production`. The source payload must already carry structured `scenes[].participants` and `scenes[].dialogues[]`; the endpoint does not call an LLM.
3. Run `POST /api/books/{book_id}/episodes/{episode}/script-ir/prepare-production` with confirmation. This deterministically builds FactSnapshot and ScriptIR from the new Script, binds immutable source evidence, and activates production authority.
4. Confirm DirectorTreatment, SceneBlocking, and ShotPlan through their current production confirmation gates. SceneBlocking must use `initial_state_from_participants()`.
5. Materialize the current Storyboard set through the production materializer, then audit PromptIR readiness without compiling or calling a provider in this phase.

The current path does not transform imported prose into speaker-bound structured dialogue. `legacy_markdown_to_script_ir()` recovers authored participant labels as a read-only compatibility projection but does not create dialogue objects. Reusing 990402 Script/ScriptIR would violate provenance separation, so a new structured screenplay source or an authorized LLM/human structuring step is required before creation.
