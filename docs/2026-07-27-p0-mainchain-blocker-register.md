# 2026-07-27 P0 Main-Chain Blocker Register

## Scope
- Project used for real-browser inspection: `三个和尚`
- Frontend: `http://127.0.0.1:5175`
- Backend proxy target shown by UI: `http://127.0.0.1:18765`

## Current conclusion
The new product workspace is structurally usable, but the main chain is still not production-ready. The current blockers are now clearer and can be divided into two buckets:

1. System/product blockers
2. Project-content completeness blockers

We should keep fixing system blockers first when they improve operator efficiency across all projects. We should not mistake incomplete project content for a generic platform bug.

## A. Confirmed system/product blockers

### A1. Delivery center used to stop at aggregate blockers
- Status: partially fixed on 2026-07-27
- Change:
  - delivery blockers now carry `episode` and first blocking `shotId`
  - delivery CTA can jump into the exact downstream section instead of only switching tabs
- Acceptance evidence:
  - real browser: `导出中心 -> 定位镜头 3 -> 镜头工作台 -> 已选中镜头 3`
- Remaining gap:
  - history repair actions still route by episode only, not exact shot

### A2. Export readiness still lacks “first blocking path” summarization
- Status: open
- User impact:
  - the user can now jump from each blocker card
  - but the top summary still does not clearly say “先修哪一个镜头、为什么”
- Recommended next change:
  - add a primary “首个阻塞入口” card in `导出中心`
  - include section, episode, shot, blocker reason, and one-click action

### A3. Storyboard workspace still exposes large-scale incomplete outputs without staged guidance
- Status: open
- User impact:
  - the project contains many shots with missing adopted image/video
  - the UI shows `待补齐`, but production sequencing is still operator-driven
- Recommended next change:
  - add stronger queue-like guidance for:
    - first shot missing frame
    - first shot missing adopted video
    - first shot with unresolved prompt diagnosis

### A4. QA and export are linked semantically, but still not enough operationally
- Status: open
- User impact:
  - export can read QA blockers
  - but the user still needs faster drill-down from QA issue -> shot -> repair action -> recheck result
- Recommended next change:
  - tighten `导出中心 -> QA 修复` routing with episode context
  - show open issue count and latest recheck result inline in export blocker summary

### A5. Delivery readiness has a real-data synchronization window
- Status: open
- Real-browser observation:
  - immediately after entering `导出中心`, the page may briefly show:
    - `正在同步项目数据`
    - `当前还没有可评估交付的分集`
  - after a few seconds, the real readiness data appears correctly
- Why it matters:
  - this can be mistaken for an empty-state bug
  - it also hides newly added primary blocker guidance until data settles
- Recommended next change:
  - show a dedicated loading skeleton or “syncing delivery readiness” state
  - avoid rendering the empty-state copy until readiness fetch truly resolves empty

## B. Confirmed project-content completeness blockers

### B1. Episode 1 has many shots without adopted storyboard frames
- Status: open
- Observed in browser:
  - multiple shots show `图片 0 / 视频 0`
  - shot 3 was routed correctly and still had `分镜图版本 0 / 视频版本 0`
- This is not itself a platform bug.

### B2. Many shots also lack adopted video versions
- Status: open
- This is expected given the current project state.

### B3. Export readiness remains blocked by actual project incompleteness
- Status: open
- This is a true delivery blocker for the project, but not necessarily a software defect.

## C. Priority recommendation

### Immediate next P0 target
Improve “what should I fix first” guidance in `导出中心` and `镜头工作台`, using the newly available blocker routing metadata.

### Why this is next
- it improves the real production chain without paid generation
- it reduces operator confusion across all projects
- it complements the routing fix already landed today

## D. Acceptance baseline for the next step
1. `导出中心` must show a single primary first-blocker action.
2. Clicking that action must land in the exact section and exact shot when shot context exists.
3. Real-browser validation must confirm the routed shot matches the blocker summary.
4. Focused frontend tests and `npm run build` in `web/` must pass.
