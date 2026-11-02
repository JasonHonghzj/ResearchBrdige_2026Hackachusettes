// Run with: node --test tests/frontend_bridge_state.test.cjs
// Execute the production script with a small DOM and manually ordered fetches.
// The goal/cue cases also have real-engine assertions in test_bridge_api.py.+'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const records = JSON.parse(fs.readFileSync(path.join(root, 'data/bridge/snapshots/pubmed.json'), 'utf8')).records;
const source = fs.readFileSync(path.join(root, 'static/bridge.js'), 'utf8');
const end = /\}\)\(\);\s*$/;
assert.match(source, end);
// Expose closure bindings only inside this VM; production has no test hooks.
const instrumented = source.replace(end,
  'window.audit = {state, search, bridges, compare, brief, directory, exportControls};})();');
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness() {
  const elements = new Map(), calls = [], downloads = [];
  class Element {
    constructor(id) {
      this.id = id; this.value = ''; this.hidden = true; this.textContent = '';
      this.dataset = {}; this.options = []; this.listeners = new Map(); this.children = new Map();
      this.classes = new Set();
      this.classList = {
        add: name => this.classes.add(name), remove: name => this.classes.delete(name),
        toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name),
      };
    }
    set innerHTML(value) { this.html = value; this.children.clear(); }
    get innerHTML() { return this.html || ''; }
    setAttribute() {}
    addEventListener(name, fn) { this.listeners.set(name, fn); }
    querySelectorAll() { return []; }
    querySelector(selector) {
      if (!this.children.has(selector)) {
        const child = new Element(this.id + ' ' + selector);
        if (selector === 'select') child.value = 'csv';
        this.children.set(selector, child);
      }
      return this.children.get(selector);
    }
    trigger(name) { return this.listeners.get(name)?.({ preventDefault() {} }); }
    click() { if (this.download) downloads.push(this.download); }
    remove() {}
  }
  const el = id => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };
  class TestURL extends URL {
    static createObjectURL() { return 'blob:export'; }
    static revokeObjectURL() {}
  }
  const window = {};
  const context = {
    window, URL: TestURL, URLSearchParams,
    setTimeout: () => 0, clearTimeout() {},
    document: {
      getElementById: el, querySelectorAll: () => [], documentElement: {},
      createElement: () => new Element('download'), body: { append() {} },
    },
    fetch: (url, options) => new Promise((resolve, reject) => calls.push({ url, options, resolve, reject })),
  };
  vm.createContext(context);
  vm.runInContext(instrumented, context, { filename: 'static/bridge.js' });
  const api = window.audit;
  api.state.text = { all_cues: 'All cues', results: '{total} papers match; showing {shown}.',
    bridge_query: 'Query: {query}', bridge_empty: 'No papers match.' };
  api.state.meta = { scope: { corpus: '60 starter papers' } };
  return {
    ...api, el, calls, downloads,
    query: index => new URL(calls[index].url, 'http://local').searchParams,
    body: index => JSON.parse(calls[index].options.body),
    resolve(index, data) {
      assert.ok(calls[index], `request ${index} exists`);
      calls[index].resolve({ ok: true, json: async () => data, blob: async () => ({}) });
    },
    export(id) { return el(id).querySelector('button').trigger('click'); },
  };
}

function paper(pmid) {
  const record = records[pmid];
  assert.ok(record, 'fixture PMID exists in the shipped PubMed snapshot');
  return { pmid, title: record.title, journal: record.journal, score: 0.1,
    excerpt: record.sections[0]?.text || '', method_evidence: record.title,
    institutions: [], source_url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`, doi: record.doi };
}

function bridgeReply(method, cue = 'all') {
  const ids = method === 'protein'
    ? (cue === 'privacy' ? [] : ['41049045'])
    : ['40963721', '41031082', '40964651', '41726433', '41726533', '41726516'];
  return { method: { id: method, label: method }, cue: { id: cue, label: cue === 'all' ? null : cue },
    recommended_methods: [], pairs: [], bridge_query: `${method} ${cue}`,
    cues: (method === 'protein' ? ['biomarker', 'genomics'] : ['privacy', 'medication'])
      .map(id => ({ id, label: id, method_count: 1 })), count: ids.length, results: ids.map(paper) };
}

test('search shows 32 total matches while displaying 20 cards', async () => {
  const h = harness();
  h.el('b-q').value = 'study'; h.el('b-mode').value = 'tfidf';
  const pending = h.search();
  assert.equal(h.query(0).get('limit'), '20');
  h.resolve(0, { query: 'study', effective_query: 'study', expanded_query: 'study',
    lexicon_matches: [], count: 32, total_count: 32, shown_count: 20,
    results: Object.keys(records).slice(0, 20).map(paper) });
  await pending;
  assert.equal(h.el('b-search-status').textContent, '32 papers match; showing 20.');
  assert.equal(h.state.lastResults.length, 20);
  assert.equal(h.el('b-search-export').hidden, false);
});

test('an unavailable cue is re-fetched before controls and results change together', async () => {
  const h = harness();
  h.state.q = 'protein structure'; h.state.cue = 'privacy';
  h.el('b-method').value = 'auto'; h.el('b-cue').value = 'privacy';
  h.el('b-chain-b').textContent = 'Previous result';
  const pending = h.bridges();
  assert.equal(h.query(0).get('cue'), 'privacy');
  h.resolve(0, bridgeReply('protein', 'privacy'));
  await flush();
  assert.equal(h.query(1).get('cue'), 'all');
  assert.equal(h.el('b-cue').value, 'privacy');
  assert.equal(h.el('b-chain-b').textContent, 'Previous result');
  assert.equal(h.el('b-bridge-export').hidden, true);
  h.resolve(1, bridgeReply('protein'));
  await pending;
  assert.equal(h.state.cue, 'all');
  assert.equal(h.el('b-cue').value, 'all');
  assert.equal(h.el('b-chain-b').textContent, 'All cues');
  assert.match(h.el('b-bridge-results').innerHTML, /41049045/);
  assert.equal(h.el('b-bridge-export').hidden, false);
});

test('a slow old response cannot replace the newer method or its export snapshot', async () => {
  const h = harness();
  h.state.q = 'medication literacy'; h.el('b-method').value = 'llm';
  const older = h.bridges();
  h.state.q = 'protein structure'; h.el('b-method').value = 'protein';
  const newer = h.bridges();
  h.resolve(1, bridgeReply('protein')); await newer;
  h.resolve(0, bridgeReply('llm')); await older;
  assert.equal(h.el('b-chain-c').textContent, 'protein');
  assert.equal(h.el('b-chain-a').textContent, 'protein structure');
  assert.match(h.el('b-bridge-results').innerHTML, /41049045/);
  assert.doesNotMatch(h.el('b-bridge-results').innerHTML, /41726533/);
  h.state.q = 'changed'; h.state.method = 'llm'; h.state.lang = 'zh';
  const exported = h.export('b-bridge-export');
  assert.deepEqual(h.body(2), { kind: 'bridges', format: 'csv', lang: 'en',
    q: 'protein structure', mode: 'tfidf', method: 'protein', cue: 'all' });
  h.resolve(2, {}); await exported;
  assert.deepEqual(h.downloads, ['researchbridge_bridges_en.csv']);
});

test('an old fallback response is also discarded when another method wins', async () => {
  const h = harness();
  h.state.q = 'protein structure'; h.state.cue = 'privacy'; h.el('b-method').value = 'auto';
  const older = h.bridges();
  h.resolve(0, bridgeReply('protein', 'privacy')); await flush();
  assert.equal(h.query(1).get('cue'), 'all');
  h.state.q = 'medication literacy'; h.state.cue = 'all'; h.el('b-method').value = 'llm';
  const newer = h.bridges();
  h.resolve(2, bridgeReply('llm')); await newer;
  h.resolve(1, bridgeReply('protein')); await older;
  assert.equal(h.el('b-chain-c').textContent, 'llm');
  assert.match(h.el('b-bridge-results').innerHTML, /41726533/);
});

test('a failed old request cannot overwrite a newer successful status', async () => {
  const h = harness();
  h.el('b-method').value = 'llm'; const older = h.bridges();
  h.el('b-method').value = 'protein'; const newer = h.bridges();
  h.resolve(1, bridgeReply('protein')); await newer;
  const status = h.el('b-bridge-status').textContent;
  h.calls[0].reject(new Error('old failure')); await older;
  assert.equal(h.el('b-bridge-status').textContent, status);
  assert.equal(h.el('b-bridge-status').classes.has('err'), false);
});

test('export captures selected IDs, language and format for the displayed result', async () => {
  const h = harness(), ids = ['41726533'];
  h.exportControls('snapshot', 'compare', { pmids: ids });
  ids.push('41049045'); h.state.lang = 'es';
  const exported = h.export('snapshot');
  h.el('snapshot').querySelector('select').value = 'pdf';
  assert.deepEqual(h.body(0), { kind: 'compare', format: 'csv', lang: 'en', pmids: ['41726533'] });
  h.resolve(0, {}); await exported;
  assert.deepEqual(h.downloads, ['researchbridge_compare_en.csv']);
});

test('compare and brief exports use the IDs and language sent for their displayed reports', async () => {
  for (const kind of ['compare', 'brief']) {
    const h = harness();
    h.state.saved = ['41726533']; h.state.q = 'medication literacy';
    const pending = h[kind]();
    h.state.saved.push('41049045'); h.state.q = 'protein structure'; h.state.lang = 'es';
    h.resolve(0, kind === 'compare' ? { papers: [], pairs: [] } : { markdown: '# Brief\nSaved paper' });
    await pending;
    const exported = h.export(`b-${kind}-export`);
    assert.deepEqual(h.body(1).pmids, ['41726533']);
    assert.equal(h.body(1).lang, 'en');
    if (kind === 'brief') assert.equal(h.body(1).q, 'medication literacy');
    h.resolve(1, {}); await exported;
  }
});

test('directory export retains the filters that produced its displayed rows', async () => {
  const h = harness();
  h.el('b-dir-name').value = 'Harvard'; h.el('b-dir-city').value = 'Cambridge';
  const pending = h.directory();
  h.el('b-dir-name').value = 'MIT'; h.el('b-dir-city').value = 'Boston'; h.state.lang = 'zh';
  h.resolve(0, { cities: ['Cambridge'], count: 0, institutions: [] }); await pending;
  const exported = h.export('b-dir-export');
  assert.deepEqual(h.body(1), { kind: 'directory', format: 'csv', lang: 'en', name: 'Harvard', city: 'Cambridge' });
  h.resolve(1, {}); await exported;
});
