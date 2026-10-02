const assert = require('node:assert/strict');
const { reviewableRawCandidate } = require('./e2e-production-ui-v3-user-journey');

function lane({ executionCandidateId = 'C1', executionState = 'SUCCEEDED', candidates = [], latest = candidates.at(-1) || null, official = { current: false, version: null }, validationStatus = 'TECHNICALLY_VALID' } = {}) {
  const items = candidates.map((candidate) => ({
    id: candidate,
    state: 'MEDIA_CANDIDATE',
    preview_url: `/media/${candidate}.jpg`,
    technical_validation: { status: candidate === 'PENDING' ? 'VALIDATION_PENDING' : candidate === 'FAILED' ? 'INVALID' : validationStatus },
  }));
  return {
    latest_execution: { id: `execution-${executionCandidateId}`, state: executionState, candidate_id: executionCandidateId },
    candidates: { items, latest: latest ? items.find((item) => item.id === latest) || null : null },
    official,
    next_action: { key: 'REVIEW_IMAGE_CANDIDATE' },
  };
}

{
  const result = reviewableRawCandidate(lane({ candidates: ['C1'], latest: 'C1' }));
  assert.equal(result.reviewable, true);
  assert.equal(result.candidateId, 'C1');
  assert.equal(result.validationStatus, 'TECHNICALLY_VALID');
  assert.equal(result.previewUrl, '/media/C1.jpg');
}

{
  const result = reviewableRawCandidate(lane({ executionCandidateId: 'C2', candidates: ['C1', 'C2'], latest: 'C2', official: { current: true, version: { candidate_id: 'C1' } } }));
  assert.equal(result.reviewable, true);
  assert.equal(result.candidateId, 'C2');
}

{
  const result = reviewableRawCandidate(lane({ candidates: ['C1'], latest: 'C1', official: { current: true, version: { candidate_id: 'C1' } } }));
  assert.equal(result.reviewable, false);
}

{
  assert.equal(reviewableRawCandidate(lane({ candidates: ['PENDING'], latest: 'PENDING' })).reviewable, false);
  assert.equal(reviewableRawCandidate(lane({ candidates: ['FAILED'], latest: 'FAILED' })).reviewable, false);
  assert.equal(reviewableRawCandidate(lane({ executionState: 'RUNNING', candidates: ['C1'], latest: 'C1' })).reviewable, false);
}

console.log('raw V2 candidate helper tests passed');
