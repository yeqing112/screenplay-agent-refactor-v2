# 2026-08-14 Script Skill Sync Note

## Why this note exists

Core blueprint and staged-plan documents currently show encoding-risk symptoms in the local terminal path.
To avoid writing new rules into a possibly contaminated file, this note temporarily acts as the clean synchronization layer.

It supplements:

- `docs/产品重构蓝图.md`
- `docs/产品重构阶段任务与验收标准.md`
- `AGENT.MD`

## Synchronized Decision

From 2026-08-14 onward, script-quality remediation follows this rule:

> Do not repair scripts with local heuristic patching only.
> All repairs must first be expressed as general Production Skill capability.

## Effective Supplement

The following document is now the active supplement for script remediation work:

- `docs/2026-08-14-script-skill-general-remediation-plan.md`

## What this changes in blueprint terms

### Blueprint supplement

The product blueprint gains one more execution constraint:

- script quality is not improved by ad hoc copyediting alone
- script quality must be produced by structured skill rules, intermediate script objects, compiler stages, and QA backpressure

### Staged-task supplement

The staged-task plan gains one more task cluster:

- `Script Skill General Remediation`

Its delivery order is:

1. general rule system
2. intermediate structure system
3. compiler wiring
4. QA rule binding
5. current project validation

### Agent-rule supplement

All future script fixes must obey:

- general capability first
- project-specific repair second
- browser acceptance plus text acceptance together

## Immediate Next Tasks

1. implement the rule schema for script skill
2. define intermediate script structures
3. bind QA issues back to broken rule classes
4. re-run `book 14` as the validation sample

## Progress Update

As of 2026-08-14:

- the script foundation structure has been added to backend production-skill code
- script generation and rewrite now inject:
  - production skill runtime
  - script foundation
  - script execution plan
  - latest script QA issues
- QA workbench issue serialization now exposes:
  - `rule_family`
  - `repair_goal`
- frontend QA parsing now preserves these fields for workbench issues
- automated tests for backend and frontend coverage of this data path are passing

This means the system now has a shared rule-family vocabulary from:

- script QA result
- to workbench issue payload
- to frontend issue state

Additional progress now completed:

- QA fix generation now consumes a shared `Script Repair Focus` block
- fix options now persist `rule_family` and `repair_goal`
- applied script fix versions now persist repair-focus metadata for later audit
- `logic_gap` classification has been narrowed for reusable repair routing
- script foundation can now prefer real script scene structure over stale outline-only scene lists

Validation on the current sample shows:

- the `book 14` script foundation now recognizes the real 8-scene structure
- the latest `book 14` QA priorities now surface `prop_evidence_continuity` first instead of a vague generic bucket

The next step remains:

- use this shared vocabulary to drive general script repair flow on the validation sample

## Merge-back Rule

After encoding health is confirmed for the core documents, the contents of this sync note and the remediation plan must be merged back into:

- the blueprint
- the staged task document
- AGENT rules

Until then, these two ASCII-named documents are the authoritative clean supplement for script-quality remediation.
