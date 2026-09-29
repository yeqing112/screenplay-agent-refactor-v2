(function () {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  function setScreen(name) {
    $$('[data-screen]').forEach((el) => el.classList.toggle('is-active', el.dataset.screen === name));
    $$('[data-nav]').forEach((el) => el.classList.toggle('is-active', el.dataset.nav === name));
    document.body.dataset.screen = name;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function showToast(message, tone = 'positive') {
    const toast = $('[data-toast]');
    if (!toast) return;
    toast.textContent = message;
    toast.dataset.tone = tone;
    toast.classList.add('is-visible');
    window.clearTimeout(window.__toastTimer);
    window.__toastTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 2400);
  }
  function selectShot(id) {
    $$('[data-shot]').forEach((el) => el.classList.toggle('is-selected', el.dataset.shot === id));
    $$('[data-current-shot]').forEach((el) => { el.textContent = `镜头 ${id}`; });
    showToast(`已切换到镜头 ${id}`);
  }
  function selectReview(id) {
    $$('[data-review]').forEach((el) => el.classList.toggle('is-selected', el.dataset.review === id));
    const item = UI_V3_FIXTURE.reviews.find((review) => review.id === id);
    if (item) {
      $$('[data-review-type]').forEach((el) => { el.textContent = item.type; });
      $$('[data-review-shot]').forEach((el) => { el.textContent = `镜头 ${item.shot} · ${item.scene}`; });
      $$('[data-review-reason]').forEach((el) => { el.textContent = item.reason; });
      $$('[data-review-recommendation]').forEach((el) => { el.textContent = item.recommendation; });
      $$('[data-review-version]').forEach((el) => { el.textContent = item.version; });
    }
  }
  function init() {
    $$('[data-nav]').forEach((el) => el.addEventListener('click', () => setScreen(el.dataset.nav)));
    $$('[data-shot]').forEach((el) => el.addEventListener('click', () => selectShot(el.dataset.shot)));
    $$('[data-review]').forEach((el) => el.addEventListener('click', () => selectReview(el.dataset.review)));
    $$('[data-stage-tab]').forEach((el) => el.addEventListener('click', () => {
      $$('[data-stage-tab]').forEach((tab) => tab.classList.remove('is-active'));
      el.classList.add('is-active');
      $$('[data-stage-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.stagePanel === el.dataset.stageTab));
    }));
    $$('[data-details]').forEach((el) => el.addEventListener('click', () => $('[data-details-drawer]')?.classList.add('is-open')));
    $$('[data-close-details]').forEach((el) => el.addEventListener('click', () => $('[data-details-drawer]')?.classList.remove('is-open')));
    $$('[data-approve]').forEach((el) => el.addEventListener('click', () => { el.classList.add('is-done'); el.textContent = '已批准 · 下一步已解锁'; showToast('已记录审核决定，正在刷新生产状态'); }));
    $$('[data-revise]').forEach((el) => el.addEventListener('click', () => showToast('已创建修改建议，保留当前版本', 'neutral')));
    $$('[data-start-production]').forEach((el) => el.addEventListener('click', () => showToast('视觉原型：已打开批量制作确认', 'neutral')));
    $$('[data-open-review]').forEach((el) => el.addEventListener('click', () => { setScreen('review'); selectReview(el.dataset.openReview || 'r1'); }));
    $$('[data-shortcut]').forEach((el) => el.addEventListener('click', () => showToast(el.dataset.shortcut)));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'a' || event.key === 'A') showToast('快捷键 A：批准当前审核', 'neutral');
      if (event.key === 'r' || event.key === 'R') showToast('快捷键 R：要求修改', 'neutral');
      if (event.key === ' ') { event.preventDefault(); showToast('Space：预览当前媒体', 'neutral'); }
    });
    setScreen('dashboard');
    selectShot('214');
    selectReview('r1');
  }
  window.addEventListener('DOMContentLoaded', init);
})();
