import { describe, expect, it } from 'vitest'

import type {
  GenerationExecutionProjection,
  MediaCandidateProjection,
  ProductionMediaLane,
  ProductionShotV2,
} from './productionWorkspace'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import {
  PRODUCTION_UI_REASON_CODES,
  isCanonicalOfficialMedia,
  toMediaLaneViewModel,
  toShotStudioViewModel,
} from './productionUiV3'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const canonicalOfficial = {
  current: true,
  currentness: 'current',
  version: {
    id: 'official-image-1',
    revision: 1,
    media_type: 'IMAGE',
    storage_identity: 'https://cdn.example/official.png',
    checksum: 'sha',
    mime: 'image/png',
    width: 1024,
    height: 576,
    duration_ms: null,
    candidate_id: 'candidate-promoted',
    validation_id: 'validation-1',
  },
  authority: {
    id: 'authority-1',
    status: 'CURRENT',
    payload_hash: 'payload',
    lineage_hash: 'lineage',
  },
  pointer: {
    id: 1,
    authority_id: 'authority-1',
    fingerprint: 'pointer',
  },
  preview: 'https://cdn.example/official.png',
} as const

const validCandidate: MediaCandidateProjection = {
  id: 'candidate-review',
  state: 'MEDIA_CANDIDATE',
  preview: 'https://cdn.example/candidate.png',
  created_at: '2026-09-29T00:00:00Z',
  model_profile_id: 'image-profile',
  technical_validation: {
    status: 'TECHNICALLY_VALID',
    validation_id: 'validation-review',
    mime: 'image/png',
    width: 1024,
    height: 576,
    duration_ms: null,
    details: {},
  },
  checksum: 'candidate-sha',
  storage_identity: 'https://cdn.example/candidate.png',
}

function readyLane(overrides: Partial<ProductionMediaLane> = {}): ProductionMediaLane {
  const base = clone(productionWorkspaceV2Fixture.shots[0].IMAGE)
  return {
    ...base,
    prompt_ir: { current: true, version: 1, stale: false, state: 'complete', reason_codes: [] },
    model: { selected_profile_id: 'image-profile', provider: 'mock', model_name: 'fixture-image' },
    candidates: { count: 0, latest: null, items: [] },
    official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null },
    generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] },
    ...overrides,
  }
}

function readyShot(overrides: Partial<ProductionShotV2> = {}): ProductionShotV2 {
  const base = clone(productionWorkspaceV2Fixture.shots[0])
  return {
    ...base,
    asset_readiness: { state: 'ready', required: {}, missing: [], stale: [], current: true },
    IMAGE: readyLane(),
    VIDEO: readyLane({
      generation_mode: 'TEXT_TO_VIDEO',
      model: { selected_profile_id: 'video-profile', provider: 'mock', model_name: 'fixture-video' },
    }),
    blockers: [],
    ...overrides,
  }
}

function execution(state: string, overrides: Partial<GenerationExecutionProjection> = {}): GenerationExecutionProjection {
  return {
    id: `exec-${state.toLowerCase()}`,
    state,
    target_media: 'IMAGE',
    model_profile_id: 'image-profile',
    provider: 'mock',
    model: 'fixture',
    adapter: 'mock',
    adapter_version: '1',
    transport_retry_count: 0,
    provider_task_id: '',
    provider_request_id: '',
    request_fingerprint: 'fp',
    candidate_id: null,
    failure_code: null,
    created_at: null,
    completed_at: null,
    ...overrides,
  }
}

describe('productionUiV3 canonical state adapters', () => {
  it('requires current pointer, matching authority, version and currentness for official media', () => {
    expect(isCanonicalOfficialMedia(canonicalOfficial).isCanonicalOfficial).toBe(true)
    const missingPointer = { ...clone(canonicalOfficial), pointer: null }
    const result = isCanonicalOfficialMedia(missingPointer)
    expect(result.isCanonicalOfficial).toBe(false)
    expect(result.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISSING)
  })

  it('never upgrades a candidate or legacy adopted flag to official', () => {
    const shot = readyShot({
      legacy: { adopted: true },
      IMAGE: readyLane({ candidates: { count: 1, latest: validCandidate, items: [validCandidate] } }),
    })
    const view = toShotStudioViewModel(shot)
    expect(view.image.candidate.reviewEligibility).toBe(true)
    expect(view.image.state).toBe('review')
    expect(view.image.official.isCanonicalOfficial).toBe(false)
    expect(view.state).toBe('review')
  })

  it('maps active execution states to running or waiting and disables generation', () => {
    const running = toMediaLaneViewModel('IMAGE', readyLane({
      latest_execution: {
        id: 'exec-running',
        state: 'RUNNING',
        target_media: 'IMAGE',
        model_profile_id: 'image-profile',
        provider: 'mock',
        model: 'fixture',
        adapter: 'mock',
        adapter_version: '1',
        transport_retry_count: 0,
        provider_task_id: 'task',
        provider_request_id: '',
        request_fingerprint: 'fp',
        candidate_id: null,
        failure_code: null,
        created_at: null,
        completed_at: null,
      },
    }))
    expect(running.state).toBe('running')
    expect(running.primaryAction.kind).toBe('wait')
    expect(running.primaryAction.enabled).toBe(true)
    expect(running.primaryAction.kind).not.toMatch(/^generate/)

    const queued = toMediaLaneViewModel('IMAGE', readyLane({
      latest_execution: { ...running.execution.raw!, state: 'QUEUED' },
    }))
    expect(queued.state).toBe('waiting')
    expect(queued.primaryAction.enabled).toBe(false)
  })

  it('maps failed execution conservatively and only enables retry when readiness is true', () => {
    const failed = toMediaLaneViewModel('IMAGE', readyLane({
      latest_execution: { ...({
        id: 'exec-failed',
        state: 'FAILED',
        target_media: 'IMAGE',
        model_profile_id: 'image-profile',
        provider: 'mock',
        model: 'fixture',
        adapter: 'mock',
        adapter_version: '1',
        transport_retry_count: 0,
        provider_task_id: '',
        provider_request_id: '',
        request_fingerprint: 'fp',
        candidate_id: null,
        failure_code: 'MODEL_ADAPTER_RESULT_FAILED',
        created_at: null,
        completed_at: null,
      }), state: 'FAILED' },
    }))
    expect(failed.state).toBe('failed')
    expect(failed.primaryAction.kind).toBe('retry_generation')
    expect(failed.primaryAction.enabled).toBe(false)

    const notReady = toMediaLaneViewModel('IMAGE', readyLane({
      generation_readiness: { ready: false, reason_codes: ['ASSET_MEDIA_NOT_READY'], primary_blocker: { code: 'ASSET_MEDIA_NOT_READY', message: 'asset' }, blockers: [{ code: 'ASSET_MEDIA_NOT_READY', message: 'asset' }] },
      latest_execution: { ...failed.execution.raw! },
    }))
    expect(notReady.state).toBe('failed')
    expect(notReady.primaryAction.enabled).toBe(false)
  })

  it('maps unknown execution state to a blocked conservative result', () => {
    const view = toMediaLaneViewModel('IMAGE', readyLane({
      latest_execution: { ...({
        id: 'exec-unknown',
        state: 'SOMETHING_NEW',
        target_media: 'IMAGE',
        model_profile_id: 'image-profile',
        provider: 'mock',
        model: 'fixture',
        adapter: 'mock',
        adapter_version: '1',
        transport_retry_count: 0,
        provider_task_id: '',
        provider_request_id: '',
        request_fingerprint: 'fp',
        candidate_id: null,
        failure_code: null,
        created_at: null,
        completed_at: null,
      }) },
    }))
    expect(view.state).toBe('blocked')
    expect(view.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.UNKNOWN_EXECUTION_STATE)
    expect(view.primaryAction.kind).toBe('resolve_blocker')
  })

  it('prioritizes prompt stale over candidate review', () => {
    const view = toMediaLaneViewModel('IMAGE', readyLane({
      prompt_ir: { current: false, version: 2, stale: true, state: 'stale', reason_codes: ['PROMPT_IR_STALE'] },
      candidates: { count: 1, latest: validCandidate, items: [validCandidate] },
    }))
    expect(view.state).toBe('stale')
    expect(view.primaryAction.kind).toBe('refresh_stale_source')
  })

  it('maps asset missing to blocked and keeps blocked separate from waiting', () => {
    const shot = readyShot({
      asset_readiness: { state: 'blocked', required: {}, missing: ['CHARACTER:LIN_WAN'], stale: [], current: false },
    })
    const view = toShotStudioViewModel(shot)
    expect(view.state).toBe('blocked')
    expect(view.primaryAction.kind).toBe('resolve_blocker')

    const waiting = readyShot({
      VIDEO: readyLane({
        generation_mode: 'IMAGE_TO_VIDEO',
        generation_readiness: { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }] },
      }),
    })
    const waitingView = toShotStudioViewModel(waiting)
    expect(waitingView.video.state).toBe('waiting')
    expect(waitingView.state).toBe('ready')
    expect(waitingView.primaryAction.kind).toBe('generate_image')
    expect(waitingView.primaryAction.lane).toBe('IMAGE')
  })

  it('requires canonical official image for IMAGE_TO_VIDEO and accepts it when valid', () => {
    const withoutSource = toMediaLaneViewModel('VIDEO', readyLane({
      generation_mode: 'IMAGE_TO_VIDEO',
      generation_readiness: { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }] },
      source_official_image: null,
    }))
    expect(withoutSource.state).toBe('waiting')
    expect(withoutSource.generationAllowed).toBe(false)

    const withSource = toMediaLaneViewModel('VIDEO', readyLane({
      generation_mode: 'IMAGE_TO_VIDEO',
      generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] },
      source_official_image: canonicalOfficial,
    }))
    expect(withSource.state).toBe('ready')
    expect(withSource.generationAllowed).toBe(true)
  })

  it('treats a technically validated candidate as review until it is promoted', () => {
    const review = toMediaLaneViewModel('IMAGE', readyLane({
      candidates: { count: 1, latest: validCandidate, items: [validCandidate] },
    }))
    expect(review.state).toBe('review')
    expect(review.primaryAction.kind).toBe('review_candidate')

    const officialCandidate = { ...validCandidate, id: 'candidate-promoted' }
    const official = toMediaLaneViewModel('IMAGE', readyLane({
      official: canonicalOfficial,
      candidates: { count: 1, latest: officialCandidate, items: [officialCandidate] },
    }))
    expect(official.state).toBe('official')
    expect(official.official.isCanonicalOfficial).toBe(true)
  })

  it('exposes one and only one shot primary action and does not mutate input', () => {
    const shot = readyShot({ IMAGE: readyLane({ candidates: { count: 1, latest: validCandidate, items: [validCandidate] } }) })
    const before = clone(shot)
    const view = toShotStudioViewModel(shot)
    expect(view.primaryAction).toBeTruthy()
    expect(shot).toEqual(before)
    expect(view.primaryAction.requiresProviderCall).toBe(false)
  })

  it('allows generation only from an explicit readiness contract', () => {
    const missingContract = toMediaLaneViewModel('IMAGE', { ...readyLane(), generation_readiness: undefined })
    expect(missingContract.state).toBe('blocked')
    expect(missingContract.generationAllowed).toBe(false)
    expect(missingContract.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.READINESS_CONTRACT_MISSING)

    const ready = toMediaLaneViewModel('IMAGE', readyLane())
    expect(ready.state).toBe('ready')
    expect(ready.generationAllowed).toBe(true)
    expect(ready.primaryAction.kind).toBe('generate_image')
    expect(ready.primaryAction.requiresProviderCall).toBe(true)
  })

  it('does not claim official when current is true but pointer authority differs', () => {
    const inconsistent = { ...clone(canonicalOfficial), pointer: { ...canonicalOfficial.pointer, authority_id: 'other-authority' } }
    const result = isCanonicalOfficialMedia(inconsistent)
    expect(result.isCanonicalOfficial).toBe(false)
    expect(result.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISMATCH)
  })

  it('resolves IMAGE_TO_VIDEO dependency waits from the actionable IMAGE lane', () => {
    const dependentVideo = readyLane({
      generation_mode: 'IMAGE_TO_VIDEO',
      generation_readiness: { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'image' }] },
      source_official_image: null,
    })

    const ready = toShotStudioViewModel(readyShot({ VIDEO: dependentVideo }))
    expect(ready.state).toBe('ready')
    expect(ready.primaryAction.kind).toBe('generate_image')
    expect(ready.primaryAction.lane).toBe('IMAGE')

    const review = toShotStudioViewModel(readyShot({
      IMAGE: readyLane({ candidates: { count: 1, latest: validCandidate, items: [validCandidate] } }),
      VIDEO: dependentVideo,
    }))
    expect(review.state).toBe('review')
    expect(review.primaryAction.kind).toBe('review_candidate')
    expect(review.primaryAction.lane).toBe('IMAGE')

    const running = toShotStudioViewModel(readyShot({
      IMAGE: readyLane({ latest_execution: execution('RUNNING') }),
      VIDEO: dependentVideo,
    }))
    expect(running.state).toBe('running')
    expect(running.primaryAction.kind).toBe('wait')
    expect(running.primaryAction.lane).toBe('IMAGE')

    const failed = toShotStudioViewModel(readyShot({
      IMAGE: readyLane({ latest_execution: execution('FAILED', { failure_code: 'MODEL_ADAPTER_RESULT_FAILED' }) }),
      VIDEO: dependentVideo,
    }))
    expect(failed.state).toBe('failed')
    expect(failed.primaryAction.kind).toBe('retry_generation')
    expect(failed.primaryAction.lane).toBe('IMAGE')

    const blocked = toShotStudioViewModel(readyShot({
      IMAGE: readyLane({ generation_readiness: { ready: false, reason_codes: ['ASSET_MEDIA_NOT_READY'], primary_blocker: { code: 'ASSET_MEDIA_NOT_READY', message: 'asset' }, blockers: [{ code: 'ASSET_MEDIA_NOT_READY', message: 'asset' }] } }),
      VIDEO: dependentVideo,
    }))
    expect(blocked.state).toBe('blocked')
    expect(blocked.primaryAction.kind).toBe('resolve_blocker')
    expect(blocked.primaryAction.lane).toBe('IMAGE')

    const stale = toShotStudioViewModel(readyShot({
      IMAGE: readyLane({ prompt_ir: { current: false, version: 2, stale: true, state: 'stale', reason_codes: ['PROMPT_IR_STALE'] } }),
      VIDEO: dependentVideo,
    }))
    expect(stale.state).toBe('stale')
    expect(stale.primaryAction.kind).toBe('refresh_stale_source')
    expect(stale.primaryAction.lane).toBe('IMAGE')

    const independentTextVideo = toShotStudioViewModel(readyShot({
      VIDEO: readyLane({
        generation_mode: 'TEXT_TO_VIDEO',
        generation_readiness: { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'unexpected text video dependency' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'unexpected text video dependency' }] },
      }),
    }))
    expect(independentTextVideo.state).toBe('waiting')
    expect(independentTextVideo.primaryAction.kind).toBe('wait')
    expect(independentTextVideo.primaryAction.lane).toBe('VIDEO')
  })

  it('continues to VIDEO after canonical IMAGE official evidence is established', () => {
    const officialImage = readyLane({ official: canonicalOfficial })
    const videoReady = readyLane({ generation_mode: 'IMAGE_TO_VIDEO', source_official_image: canonicalOfficial })
    const ready = toShotStudioViewModel(readyShot({ IMAGE: officialImage, VIDEO: videoReady }))
    expect(ready.state).toBe('ready')
    expect(ready.primaryAction.kind).toBe('generate_video')
    expect(ready.primaryAction.lane).toBe('VIDEO')

    const videoReview = toShotStudioViewModel(readyShot({
      IMAGE: officialImage,
      VIDEO: readyLane({ generation_mode: 'IMAGE_TO_VIDEO', source_official_image: canonicalOfficial, candidates: { count: 1, latest: validCandidate, items: [validCandidate] } }),
    }))
    expect(videoReview.state).toBe('review')
    expect(videoReview.primaryAction.kind).toBe('review_candidate')
    expect(videoReview.primaryAction.lane).toBe('VIDEO')

    const videoOfficial = toShotStudioViewModel(readyShot({ IMAGE: officialImage, VIDEO: readyLane({ generation_mode: 'IMAGE_TO_VIDEO', source_official_image: canonicalOfficial, official: canonicalOfficial }) }))
    expect(videoOfficial.state).toBe('official')
    expect(videoOfficial.primaryAction.kind).toBe('view_official')
  })

  it('keeps canonical official state when generation readiness is unavailable', () => {
    const view = toMediaLaneViewModel('IMAGE', readyLane({ official: canonicalOfficial, generation_readiness: undefined }))
    expect(view.state).toBe('official')
    expect(view.official.isCanonicalOfficial).toBe(true)
    expect(view.generationAllowed).toBe(false)
    expect(view.primaryAction.kind).toBe('view_official')
  })

  it('waits for a successful execution candidate to appear before allowing another generation', () => {
    const projectionLag = toMediaLaneViewModel('IMAGE', readyLane({
      latest_execution: execution('SUCCESS', { candidate_id: 'candidate-not-visible' }),
    }))
    expect(projectionLag.state).toBe('waiting')
    expect(projectionLag.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.EXECUTION_CANDIDATE_NOT_VISIBLE)
    expect(projectionLag.generationAllowed).toBe(false)
    expect(projectionLag.primaryAction.kind).toBe('wait')

    const anomalousSuccess = toMediaLaneViewModel('IMAGE', readyLane({ latest_execution: execution('SUCCESS') }))
    expect(anomalousSuccess.state).toBe('failed')
    expect(anomalousSuccess.reasonCodes).toContain(PRODUCTION_UI_REASON_CODES.EXECUTION_CANDIDATE_MISSING)
  })
})
