const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const WEB_URL = process.env.E2E_WEB_URL || 'http://127.0.0.1:5175/'
// Callers may pin a fixture, otherwise select a currently available project
// with storyboard data at runtime.  This keeps the test valid after old
// disposable books are cleaned up.
let BOOK_ID = Number(process.env.E2E_AGENT_BOOK_ID || 0)
const OUTPUT_DIR = path.join(process.cwd(), 'artifacts')

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const consoleErrors = []
  const conflictResponses = []
  let expectedResourceConflictCount = 0
  let expectedStaleConflict = false
  let expectedStaleConflictCount = 0
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    if (expectedStaleConflict && /status of a status of 409|status of 409/i.test(message.text())) {
      expectedStaleConflictCount += 1
      expectedResourceConflictCount = Math.max(0, expectedResourceConflictCount - 1)
      return
    }
    if (expectedResourceConflictCount > 0 && /status of a status of 409|status of 409/i.test(message.text())) {
      // Read-only stale-draft diagnostics and the deliberately simulated
      // stale handoff are expected conflict responses, not browser errors.
      expectedResourceConflictCount -= 1
      return
    }
    consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => consoleErrors.push(String(error)))
  page.on('response', (response) => {
    if (response.status() === 409) {
      conflictResponses.push(response.url())
      if (/\/prompt-drafts\/\d+\/diagnostics|\/api\/agent\/audit\/\d+\/handoff-confirm/i.test(response.url())) {
        expectedResourceConflictCount += 1
      }
    }
  })

  // Keep this browser test free of provider charges. The real backend chat
  // and handoff contracts are covered by API tests; this verifies the
  // production UI path, including the confirmation card and navigation event.
  let chatCalls = 0
  const actionAudits = new Map()
  // Resolve an actual asset from the selected fixture at runtime.  The
  // browser flow must remain reusable after historical fixtures are cleaned
  // up; it must never depend on a book-specific asset name or id.
  let assetHandoffTarget = null
  let projectUpdateStatus = 'unread'
  const projectUpdate = {
    id: 910001, book_id: BOOK_ID, type: 'issue', severity: 'warning',
    title: '有一项 QA 需要关注', message: '这是浏览器回归使用的可审计项目动态。',
    source_refs: [], evidence_fingerprint: 'browser-fixture', action_proposal: {},
    requires_confirmation: false, status: projectUpdateStatus, dedupe_key: 'browser-fixture',
    created_at: null, updated_at: null,
  }
  await page.route('**/api/agent/updates/reconcile', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ updates: [{ ...projectUpdate, status: projectUpdateStatus }], created_count: 0, reused_count: 1, summary: {}, evidence_fingerprint: 'browser-fixture', mutated: false }),
  }))
  await page.route('**/api/agent/updates?*', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ book_id: BOOK_ID, updates: [{ ...projectUpdate, status: projectUpdateStatus }], mutated: false }),
  }))
  await page.route('**/api/agent/updates/*/state', async (route) => {
    let payload = {}
    try { payload = JSON.parse(route.request().postData() || '{}') } catch { /* keep default */ }
    projectUpdateStatus = String(payload.status || 'acknowledged')
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ update: { ...projectUpdate, status: projectUpdateStatus }, mutated: true }) })
  })
  await page.route('**/api/agent/updates/stream*', async (route) => route.fulfill({
    status: 200, contentType: 'text/event-stream', body: ': heartbeat\nevent: heartbeat\ndata: {}\n\n',
  }))
  await page.route('**/api/agent/chat', async (route) => {
    chatCalls += 1
    const request = route.request()
    let message = ''
    try { message = String(JSON.parse(request.postData() || '{}').message || '') } catch { /* keep default */ }
    const isAssetRequest = /资产|参考图|人物|场景|道具/.test(message)
    const isQaRequest = /QA|问题|审核|修复/.test(message)
    const isStaleRequest = /过期|变化|重新读取/.test(message)
    const isActionRequest = isAssetRequest || isQaRequest || isStaleRequest || /生成视频|提交视频|帮我生成/.test(message)
    const auditId = isAssetRequest ? 900003 : isQaRequest ? 900004 : isStaleRequest ? 900005 : 900002
    const operation = isAssetRequest ? 'write_asset_governance' : isQaRequest ? 'draft_repair' : 'video_generation'
    actionAudits.set(auditId, { operation, stale: isStaleRequest })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(isActionRequest ? {
        session_id: auditId,
        audit_id: auditId,
        message: { role: 'assistant', content: isAssetRequest ? '可以打开资产中心继续审核，但涉及资产修改前需要你确认。' : isQaRequest ? '可以打开 QA 工作台审阅修复，但写回前仍需确认。' : '可以准备这个镜头的视频生成，但提交前需要你确认。', attachment_ids: [] },
        intent: 'action_proposal',
        requires_confirmation: true,
        action_proposal: {
          operation,
          summary: isAssetRequest ? '在资产中心审核当前资产治理建议。' : isQaRequest ? '在 QA 工作台审阅当前问题的候选修复。' : '在镜头工作台准备当前镜头的视频生成。',
          impact: isAssetRequest ? '不会自动写入资产，最终修改仍需在资产中心确认。' : isQaRequest ? '不会自动写回剧本，最终修复仍需在 QA 工作台确认。' : '会进入原有视频生成确认流程，可能产生外部模型费用。',
        },
        updates: [],
        llm_called: false,
        mutated: false,
      } : {
        session_id: 900001,
        message: { role: 'assistant', content: '当前项目已读取，下一步建议先处理 QA 阻塞。', attachment_ids: [] },
        intent: 'progress', requires_confirmation: false, action_proposal: {}, updates: [],
        llm_called: false, mutated: false,
      }),
    })
  })

  await page.route('**/api/agent/audit/*/handoff-confirm', async (route) => {
    const auditId = Number(route.request().url().match(/audit\/(\d+)\/handoff-confirm/)?.[1] || 0)
    const action = actionAudits.get(auditId)
    if (action?.stale) {
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: '动作提案已过期：项目事实发生变化，请重新发起请求' }) })
      return
    }
    const handoff = action?.operation === 'write_asset_governance'
      ? { section: 'assets', episode: 1, shot_id: '3', asset_id: assetHandoffTarget?.id || '', asset_label: assetHandoffTarget?.name || '', label: '前往资产中心审核资产治理', guard: '只承接到资产中心，最终写入仍需原有门禁。' }
      : action?.operation === 'draft_repair'
        ? { section: 'qa', episode: 1, shot_id: '3', label: '前往 QA 工作台审阅候选修复', guard: '只承接到 QA 工作台，最终写回仍需原有门禁。' }
        : { section: 'storyboard', episode: 1, shot_id: '3', label: '回到镜头工作台继续处理镜头 3', guard: '只承接到正式工作台，最终生成仍需原有门禁。' }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ audit_id: auditId, status: 'handoff_confirmed', handoff }) })
  })

  await page.goto(WEB_URL, { waitUntil: 'networkidle' })
  const origin = new URL(WEB_URL).origin
  const assetCollections = ['characters', 'locations', 'props']
  let assetsPayload = null
  if (!BOOK_ID) {
    const booksResponse = await page.request.get(`${origin}/api/books`)
    if (!booksResponse.ok()) throw new Error(`无法读取浏览器回归样本项目：HTTP ${booksResponse.status()}`)
    const books = await booksResponse.json()
    const candidates = Array.isArray(books)
      ? books.filter((book) => Number(book?.storyboard_shots || 0) > 0).concat(books.filter((book) => Number(book?.storyboard_shots || 0) <= 0))
      : []
    for (const candidate of candidates) {
      const candidateId = Number(candidate?.id || 0)
      if (!candidateId) continue
      const response = await page.request.get(`${origin}/api/books/${candidateId}/visual-assets`)
      if (!response.ok()) continue
      const payload = await response.json()
      if (assetCollections.some((collection) => Array.isArray(payload?.[collection]) && payload[collection].length > 0)) {
        BOOK_ID = candidateId
        assetsPayload = payload
        break
      }
    }
  }
  if (!BOOK_ID) throw new Error('没有可用于 Agent 浏览器回归的项目样本')
  projectUpdate.book_id = BOOK_ID
  if (!assetsPayload) {
    const assetsResponse = await page.request.get(`${origin}/api/books/${BOOK_ID}/visual-assets`)
    if (!assetsResponse.ok()) throw new Error(`无法读取浏览器回归样本资产：HTTP ${assetsResponse.status()}`)
    assetsPayload = await assetsResponse.json()
  }
  for (const collection of assetCollections) {
    const candidate = Array.isArray(assetsPayload?.[collection]) ? assetsPayload[collection][0] : null
    if (candidate) {
      assetHandoffTarget = {
        id: String(candidate.id ?? candidate.asset_id ?? ''),
        name: String(candidate.name ?? candidate.asset_name ?? candidate.character_name ?? ''),
      }
      break
    }
  }
  if (!assetHandoffTarget?.id || !assetHandoffTarget?.name) throw new Error(`样本 book ${BOOK_ID} 没有可用于承接验收的资产`)
  const projectCard = page.getByText(new RegExp(`#${BOOK_ID}\\s*$`)).first()
  await projectCard.waitFor({ state: 'visible', timeoutMs: 10000 })
  await projectCard.click()
  await page.getByText('正式产品工作台', { exact: true }).waitFor({ state: 'visible' })
  await page.getByRole('button', { name: '打开智能导演台' }).click()
  const drawer = page.getByRole('dialog', { name: '智能导演台对话' })
  await drawer.waitFor({ state: 'visible' })
  await page.waitForTimeout(1500)
  const initialFocus = await page.evaluate(() => document.activeElement?.id || '')
  if (initialFocus !== 'agent-objective') throw new Error(`打开抽屉后焦点未进入输入框（当前：${initialFocus || '无'}）`)
  const drawerText = await drawer.innerText()
  const triggerText = await page.getByRole('button', { name: '打开智能导演台' }).innerText()
  if (!drawerText.includes('项目动态')) throw new Error('智能导演台未显示项目动态')
  if (!/\d+/.test(triggerText)) throw new Error('智能导演台未显示未读动态数量')
  await drawer.getByRole('button', { name: /已知悉：有一项 QA 需要关注/ }).click()
  await drawer.getByRole('button', { name: /稍后提醒：有一项 QA 需要关注/ }).click()
  await drawer.getByRole('button', { name: /标记已解决：有一项 QA 需要关注/ }).click()
  await drawer.getByText('已解决', { exact: true }).waitFor({ state: 'visible', timeoutMs: 5000 })
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'real-browser-agent-drawer.png') })

  const input = drawer.locator('#agent-objective')
  await input.fill('请告诉我现在下一步做什么')
  await drawer.getByRole('button', { name: '发送' }).first().click()
  await drawer.getByText('当前项目已读取，下一步建议先处理 QA 阻塞。', { exact: true }).waitFor({ state: 'visible', timeoutMs: 5000 })

  await input.fill('请帮我生成这个镜头的视频')
  await drawer.getByRole('button', { name: '发送' }).first().click()
  await drawer.getByRole('region', { name: '待确认操作' }).waitFor({ state: 'visible', timeoutMs: 5000 })
  const proposalText = await drawer.getByRole('region', { name: '待确认操作' }).innerText()
  if (!proposalText.includes('这一步需要你的确认')) throw new Error('动作提案未显示确认门槛')
  await drawer.getByRole('button', { name: '确认并打开工作台' }).click()
  await drawer.waitFor({ state: 'hidden', timeoutMs: 5000 })
  await page.getByText('镜头工作台', { exact: true }).first().waitFor({ state: 'visible', timeoutMs: 5000 })
  const routedShot = page.locator('[data-episode="1"][data-shot-id="3"]')
  await routedShot.waitFor({ state: 'visible', timeoutMs: 15000 })
  // The fixture may already have a locked adaptation direction.  In that
  // case the original-workbench guard is intentionally absent; the invariant
  // we need to verify here is that the handoff lands in the real storyboard
  // surface and keeps its own production gates.  Record the guard when it is
  // present, but do not make the browser test depend on mutable project data.
  const gateCopy = page.getByText(/项目改编方向尚未正式锁定/).first()
  const originalWorkbenchGateVisible = await gateCopy.count() > 0 && await gateCopy.isVisible().catch(() => false)
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'real-browser-agent-handoff-storyboard.png') })
  if (!(await routedShot.count())) {
    fs.writeFileSync(path.join(OUTPUT_DIR, 'real-browser-agent-handoff-storyboard.txt'), await page.locator('body').innerText())
    throw new Error('确认承接后未定位到目标镜头 3')
  }

  // Asset-center handoff: the Agent may route the user to an exact asset, but
  // must not mutate it.  This validates the user-visible handoff context.
  await page.getByRole('button', { name: '打开智能导演台' }).click()
  await drawer.waitFor({ state: 'visible' })
  const assetInput = drawer.locator('#agent-objective')
  await assetInput.fill('请帮我审核这个资产的参考图')
  await drawer.getByRole('button', { name: '发送' }).first().click()
  await drawer.getByRole('region', { name: '待确认操作' }).waitFor({ state: 'visible', timeoutMs: 5000 })
  await drawer.getByRole('button', { name: '确认并打开工作台' }).click()
  await drawer.waitFor({ state: 'hidden', timeoutMs: 5000 })
  await page.getByText('资产列表', { exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 })
  await page.getByText(assetHandoffTarget.name, { exact: true }).first().waitFor({ state: 'visible', timeoutMs: 10000 })
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'real-browser-agent-handoff-assets.png') })

  // QA handoff: route to the real QA workbench and preserve its own review
  // workflow rather than silently applying an Agent suggestion.
  await page.getByRole('button', { name: '打开智能导演台' }).click()
  await drawer.waitFor({ state: 'visible' })
  const qaInput = drawer.locator('#agent-objective')
  await qaInput.fill('请帮我检查并修复 QA 问题')
  await drawer.getByRole('button', { name: '发送' }).first().click()
  await drawer.getByRole('region', { name: '待确认操作' }).waitFor({ state: 'visible', timeoutMs: 5000 })
  await drawer.getByRole('button', { name: '确认并打开工作台' }).click()
  await drawer.waitFor({ state: 'hidden', timeoutMs: 5000 })
  await page.getByText('QA 问题列表', { exact: true }).waitFor({ state: 'visible', timeoutMs: 10000 })
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'real-browser-agent-handoff-qa.png') })

  // Stale-evidence failure: a changed project snapshot keeps the drawer open
  // and surfaces an actionable error instead of navigating on an old proposal.
  await page.getByRole('button', { name: '打开智能导演台' }).click()
  await drawer.waitFor({ state: 'visible' })
  const staleInput = drawer.locator('#agent-objective')
  await staleInput.fill('请重新读取后确认这个过期动作')
  await drawer.getByRole('button', { name: '发送' }).first().click()
  await drawer.getByRole('region', { name: '待确认操作' }).waitFor({ state: 'visible', timeoutMs: 5000 })
  expectedStaleConflict = true
  await drawer.getByRole('button', { name: '确认并打开工作台' }).click()
  await drawer.getByText(/动作提案已过期：项目事实发生变化/).waitFor({ state: 'visible', timeoutMs: 5000 })
  await page.waitForTimeout(100)
  if (!(await drawer.isVisible())) throw new Error('过期动作提案失败后不应关闭智能导演台')
  await page.setViewportSize({ width: 390, height: 844 })
  const narrowDrawerWidth = await drawer.evaluate((node) => Math.round(node.getBoundingClientRect().width))
  if (narrowDrawerWidth > 390) throw new Error(`窄屏抽屉超出视口：${narrowDrawerWidth}px`)
  if (consoleErrors.length) throw new Error(`浏览器控制台存在未分类错误：${consoleErrors.join(' | ')}`)

  console.log(JSON.stringify({
    ok: true,
    bookId: BOOK_ID,
    drawerVisible: true,
    projectUpdatesVisible: true,
    unreadBadgeVisible: true,
    freeChatReplyVisible: true,
    actionProposalVisible: true,
    handoffConfirmed: true,
    routedSection: 'storyboard',
    routedShotId: '3',
    originalWorkbenchGateVisible,
    assetHandoffConfirmed: true,
    assetHandoffTargetVisible: true,
    qaHandoffConfirmed: true,
    qaWorkbenchVisible: true,
    staleEvidenceErrorVisible: true,
    projectUpdateActionsVisible: true,
    focusManaged: true,
    narrowDrawerFitsViewport: true,
    expectedStaleConflictCount,
    chatCalls,
    consoleErrors,
    conflictResponses,
    screenshots: [
      path.join('artifacts', 'real-browser-agent-drawer.png'),
      path.join('artifacts', 'real-browser-agent-handoff-storyboard.png'),
      path.join('artifacts', 'real-browser-agent-handoff-assets.png'),
      path.join('artifacts', 'real-browser-agent-handoff-qa.png'),
    ],
  }, null, 2))
  await browser.close()
}

main().catch((error) => { console.error(error.stack || error); process.exitCode = 1 })
