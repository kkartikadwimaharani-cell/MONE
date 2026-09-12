import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../templates/ai-video.html', import.meta.url), 'utf8');
function section(start, end) {
  const first = html.indexOf(start);
  assert.notEqual(first, -1, start);
  const last = html.indexOf(end, first + start.length);
  assert.notEqual(last, -1, end);
  return html.slice(first, last);
}

test('demo history and archive never attempt an API request', () => {
  const context = {
    DEMO_MODE: true,
    fetchWithTimeout() { throw Error('Demo attempted an API request'); },
  };
  vm.runInNewContext(
    section('function refreshArchiveFromServer(onDone)', '// History now also has a server-side home') +
    section('function refreshHistoryFromServer(onDone)', '// Pure text-to-video'), context);
  let archive, history;
  context.refreshArchiveFromServer(ok => { archive = ok; });
  context.refreshHistoryFromServer(ok => { history = ok; });
  assert.equal(archive, true);
  assert.equal(history, true);
});

test('demo frame input, archive actions and account actions never reach the API', async () => {
  const handlers = {};
  let notices = 0;
  const context = {
    DEMO_MODE: true,
    document: {
      getElementById(id) {
        return { addEventListener(event, handler) { handlers[id + ':' + event] = handler; } };
      },
    },
    showDemoNotice() { notices++; },
    fetch() { throw Error('Demo attempted an API request'); },
    fetchWithTimeout() { throw Error('Demo attempted an API request'); },
  };
  vm.runInNewContext(section("['first','last'].forEach(function(which)", '// ══════════ QTY'), context);
  for (const name of ['firstFrameInput:change', 'lastFrameInput:change']) {
    const input = { files: [{ name: 'frame.png' }], value: 'frame.png' };
    handlers[name]({ target: input });
    assert.equal(input.value, '');
  }
  vm.runInNewContext(
    section('function syncArchiveToServer(rec)', 'function dedupeHistoryRecords(list)') +
    section('function doLogout()', '// ══════════ HISTORY (client-side') +
    section('function downloadResult(url, suggestedName)', 'function showError(msg)'), context);
  assert.equal(await context.syncArchiveToServer({ id: 'test' }), false);
  assert.equal(await context.removeArchiveFromServer('test'), false);
  context.doLogout();
  context.downloadResult('https://storage.example/file.png', 'file.png');
  assert.equal(notices, 4);
});

test('a pending Generate submission blocks a second paid request until acknowledged', async () => {
  let requests = 0;
  const resolveRequests = [];
  const context = {
    DEMO_MODE: false,
    generationSubmitInFlight: false,
    promptInput: { value: 'City at dusk' },
    selectedFamily: { key: 'test-video', qualities: [{}] },
    selectedQualityIdx: 0,
    resolveEffectiveCapabilities() { return {}; },
    activeInputTab: 'elements',
    media: { image: [], video: [], audio: [] },
    frames: { first: null, last: null },
    isBackendConnected() { return true; },
    FAMILIES_REQUIRING_MEDIA: [],
    FAMILIES_REQUIRING_VIDEO: [],
    isSeedanceFamily() { return false; },
    selectedModelTier: 'STANDARD', selectedModel: 'test-video',
    selectedDuration: 4, selectedResolution: '720p', selectedRatio: '16:9',
    activeMode: 'video', selectedBitrate: 'normal', muteAudioEnabled: false,
    selectedModelName: 'Test Video',
    document: { getElementById() { return { classList: { remove() {} } }; } },
    notifyMiiPet() {}, showError() {}, updateGenerateButtonState() {},
    fetchWithTimeout(url) {
      assert.equal(url, '/api/aivideo/generate');
      requests++;
      return new Promise(resolve => resolveRequests.push(resolve));
    },
  };
  vm.runInNewContext(section('function startGenerate()', 'function formatEta(seconds)'), context);
  context.startGenerate();
  context.startGenerate();
  assert.equal(requests, 1);
  assert.equal(context.generationSubmitInFlight, true);
  resolveRequests.shift()({ status: 400, json: async () => ({ error: 'Bad input' }) });
  await new Promise(setImmediate);
  assert.equal(context.generationSubmitInFlight, false);
  context.startGenerate();
  assert.equal(requests, 2);
  resolveRequests.shift()({ status: 400, json: async () => ({ error: 'Bad input' }) });
  await new Promise(setImmediate);
});

test('history download uses the same-origin proxy and selects the video file', () => {
  let selected;
  const record = { videoUrl: 'https://storage.example/video.mp4', imageUrl: 'https://storage.example/thumbnail.webp' };
  const context = {
    DEMO_MODE: false, findHistoryRecord() { return record; },
    imageDownloadExtension() { return '.webp'; },
    downloadResult(url, filename) { selected = { url, filename }; },
  };
  vm.runInNewContext(section('function downloadHistoryItem(id)', 'function restoreFromRecord(r)'), context);
  context.downloadHistoryItem('video-1');
  assert.equal(selected.url, record.videoUrl);
  assert.match(selected.filename, /^mii-ai-\d+\.mp4$/);
  context.DEMO_MODE = true;
  context.showDemoNotice = () => {};
  selected = undefined;
  context.downloadHistoryItem('video-1');
  assert.equal(selected, undefined);
});

test('refreshing credits updates open balance displays and skips the demo', async () => {
  const values = new Map(['settingsCreditBalanceTxt', 'creditsBalanceVal', 'accBalanceVal']
    .map(id => [id, { textContent: '' }]));
  let requests = 0;
  const context = {
    DEMO_MODE: false,
    document: { getElementById: id => values.get(id) },
    formatBalance: value => `${value} CREDITS`,
    fetch(url) {
      assert.equal(url, '/api/aivideo/credits');
      requests++;
      return Promise.resolve({ ok: true, json: async () => ({ total_available: 27 }) });
    },
  };
  vm.runInNewContext(section('function fetchCreditBalance()', '// ══════════ SIDEBAR'), context);
  context.fetchCreditBalance();
  await new Promise(setImmediate);
  assert.deepEqual([...values.values()].map(el => el.textContent), Array(3).fill('27 CREDITS'));
  context.DEMO_MODE = true;
  context.fetchCreditBalance();
  assert.equal(requests, 1);
});
