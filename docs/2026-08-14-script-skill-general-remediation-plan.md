# 2026-08-14 Script Skill General Remediation Plan

## Purpose

This document defines a general remediation plan for script quality after adopting `Production Skill`.
It is a supplement to the project blueprint and staged task documents.

It exists for one reason:

- fix the **general script production capability**
- not just patch the current `book 14 / 三个和尚` script case by case

The guiding rule is:

> Every fix must first become a reusable production rule, structure, compiler step, or QA rule.
> Current-project repair is only the validation sample of that general capability.

## Current Acceptance Conclusion

Based on the 2026-08-14 acceptance for `book 14`:

- `Production Skill` is already wired into the script chain
- the current script shows obvious short-drama and suspense characteristics
- but script quality is still **not accepted for production**

Main reasons:

1. character setup and script behavior are not stable enough
2. clue chain is denser, but not fully causal
3. suspense exists, but track mechanism is not fully grounded
4. current QA is still open, so the script cannot be considered released

## General Design Principle

Script remediation must be built on four reusable layers.

### Layer 1: Skill Rules Layer

Turn track knowledge into structured constraints instead of hidden prompt text.

Must include:

- `platform_rules`
- `track_rules`
- `character_consistency_rules`
- `clue_chain_rules`
- `hook_rules`
- `forbidden_patterns`
- `qa_checks`

This layer answers:

- what kind of script this project is allowed to become
- what must never drift

### Layer 2: Script Intermediate Structure Layer

Do not generate the final episode script directly from source material.

A script must first build these intermediate structures:

- `episode_goal_card`
- `character_state_cards`
- `scene_goal_cards`
- `clue_table`
- `evidence_chain_table`
- `key_prop_table`
- `hook_table`

This layer answers:

- why each scene exists
- how each clue enters, changes, and pays off
- which prop is decorative and which prop is causal

### Layer 3: Script Compilation Layer

Generate the final script in stable stages, not one freeform pass.

Recommended flow:

1. inject platform + track constraints
2. compile episode objective and conflict structure
3. compile character states and disguise strategy
4. compile clue/evidence/prop chain
5. compile scene sequence
6. compile ending hook
7. run structure QA before emitting final script text

This layer answers:

- how model freedom is bounded
- how style stays aligned across rewrite and repair

### Layer 4: QA Backpressure Layer

QA must not only report surface problems.
It must point back to the broken general structure.

Examples:

- `令牌突兀` -> broken `key_prop_first_exposure_rule`
- `人物前后割裂` -> broken `character_state_transition_rule`
- `结尾钩子不强` -> broken `episode_hook_rule`
- `线索很多但因果弱` -> broken `evidence_chain_rule`

This layer answers:

- what system rule failed
- which compiler stage should be re-run

## General Capability Tasks

## Task Group A: Skill Rule Normalization

### Goal

Make script quality depend on structured skill rules instead of scattered prompt habits.

### Tasks

- define a stable script-skill schema for:
  - platform rhythm
  - track mechanics
  - character consistency
  - clue and evidence logic
  - ending hook strength
- split `hard_constraints` from `soft_preferences`
- define `forbidden_patterns` for script generation
- make script QA consume the same rule source

### Acceptance Criteria

- script generation, rewrite, and QA all read the same script-skill rule object
- rule changes can affect multiple projects without per-project prompt editing
- QA output can point to a concrete broken rule, not only a prose complaint

## Task Group B: Character State System

### Goal

Stop character quality from depending on improvised text patches.

### Tasks

- define `character_base_state`
- define `episode_visible_state`
- define `hidden_state`
- define `state_transition_trigger`
- define `allowed_disguise_signals`
- define `forbidden_behavior_conflicts`

Required product meaning:

- a character may have public behavior and hidden intention
- but both must be declared before the final script is emitted

### Acceptance Criteria

- each major character has a base state and an episode state
- if a character is "pretending", the disguise strategy is visible in structure
- the script cannot jump from A to B without a defined transition trigger
- QA can detect "behavior inconsistent with state card"

## Task Group C: Clue / Evidence / Prop Causality System

### Goal

Turn suspense writing from "stacking mysteries" into causal production logic.

### Tasks

- define `clue introduction`
- define `clue interpretation`
- define `false lead`
- define `evidence confirmation`
- define `key prop exposure`
- define `payoff timing`
- define `cross-scene dependency`

Every key clue or prop must answer:

- where it first appears
- who notices it
- what meaning the audience assigns to it at that moment
- when that meaning is revised
- where it pays off

### Acceptance Criteria

- every key prop has first exposure, ownership, and payoff metadata
- every key clue has a scene-of-entry and scene-of-payoff
- QA can flag "introduced but not paid off" and "paid off without setup"
- the final script no longer relies on sudden prop arrival to force a twist

## Task Group D: Scene Purpose Compiler

### Goal

Ensure each scene exists for a clear production reason.

### Tasks

- define `scene_purpose`
- define `scene_conflict`
- define `scene_information_delta`
- define `scene_emotion_delta`
- define `scene_exit_hook`

Every scene must be at least one of:

- advancing conflict
- revealing information
- shifting power
- deepening misjudgment
- setting up payoff

### Acceptance Criteria

- each scene has a declared purpose before final writing
- scenes that only repeat mood or exposition are rejected
- QA can detect "scene has no effective change"
- script pacing becomes measurable instead of subjective

## Task Group E: Episode Hook Compiler

### Goal

Turn ending-hook quality into a reusable capability.

### Tasks

- define `open_hook`
- define `midpoint escalation`
- define `final hook`
- define `next-episode pull`
- define hook templates by track

For suspense tracks, hooks should prefer:

- identity reversal
- evidence reveal
- trust collapse
- hidden objective exposure
- danger escalation

### Acceptance Criteria

- each episode has explicit open/mid/final hook metadata
- ending hook must point to the next conflict, not only stop on a surprise image
- QA can rate hook strength with track-aware standards

## Task Group F: Skill QA Upgrade

### Goal

Make QA the enforcement layer of the script skill system.

### Tasks

- map QA issues back to script-skill rules
- split QA issue types into:
  - character consistency
  - clue logic
  - prop causality
  - scene effectiveness
  - hook strength
  - platform pacing
- return fix instructions that target compiler stages

### Acceptance Criteria

- QA issues are actionable and structured
- each failed issue identifies:
  - broken rule
  - broken scene or object
  - recommended repair path
- repair no longer depends on manually guessing where to edit

## Current Project Validation Tasks: book 14

These are **validation tasks**, not isolated one-off hacks.

## Validation A: Character Consistency

- make 和尚甲 a declared "surface-lazy / hidden-objective" character, if that is the chosen direction
- or rewrite him to truly remain lazy in a way that still supports the track
- unify 和尚乙 / 和尚丙 profile and behavior

### Acceptance Criteria

- character cards and final script no longer contradict each other
- hidden motives are signaled before late-episode reveal
- QA no longer reports major character consistency conflicts

## Validation B: Prop and Clue Chain

- rebuild the relation between:
  - 木匣
  - 纸条
  - 洗髓经
  - 方丈令
  - 井底经书
- define which object is setup, bait, proof, and payoff

### Acceptance Criteria

- no key prop appears without prior structural setup
- the audience can follow why the protagonist moves from clue A to B
- QA no longer reports sudden key-prop emergence or broken clue logic

## Validation C: Hook and Track Identity

- strengthen the episode opening hook
- strengthen the final hook
- make the chosen track identity explicit in structure, not only in tone

### Acceptance Criteria

- the episode reads as the chosen skill track, not generic suspense
- the final hook points clearly to the next conflict
- QA no longer reports weak or vague ending pull

## Execution Order

1. build script-skill structured rules
2. build script intermediate structures
3. wire compiler stages
4. upgrade QA backpressure
5. re-run `book 14` as the validation sample
6. perform browser acceptance and text acceptance together

## Final Acceptance Standard

This remediation plan is considered complete only if all three levels pass.

### Level 1: General Capability Acceptance

- rules are reusable across projects
- compiler stages are reusable across projects
- QA can diagnose structural failures across projects

### Level 2: Current Project Acceptance

- `book 14` script passes structure review
- major QA issues are closed or downgraded with clear rationale
- browser workbench no longer shows script as blocked by unresolved core logic issues

### Level 3: Production Readiness Acceptance

- script output is stable across regenerate / rewrite / repair paths
- style does not drift after QA repair
- downstream storyboard generation receives cleaner, more causal script input

## Status

Current status on 2026-08-14:

- general remediation plan: defined
- current project quality: not yet accepted
- next action: implement general capability tasks before re-validating `book 14`
