# Director Quality V3 — Narrative Unit Incomplete Input Forensic

## Baseline Audit

The historical preview exposed `12` indexed anchors while declaring `full_anchor_count=347`.

## Root Cause

`PREVIEW_INPUT_TRUNCATED`: only the first twelve anchors were passed to the preview materializer. The deterministic `build_narrative_unit_index()` implementation was not the truncation source.

## Guard

The historical preview is preserved and cannot qualify full-source coverage. This round rebuilds from the immutable raw source and canonical evidence index.
